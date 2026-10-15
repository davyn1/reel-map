# food-map

Personal Bay Area restaurant map built from saved Instagram food reels. A tracker/checklist for one user (maybe one friend), not a public app.

Flow: Instagram saved reels → exported by Meta's Muse AI as JSON (`data/reels*.json`) → CLI import → SQLite → FastAPI → React + Leaflet map.

Pins use Muse's own coordinates. There is no Google Places (or any external API) call; each popup has a plain "Open in Google Maps" link instead. If pins turn out to be wrong, a verification step (Google Places or OpenStreetMap Nominatim) can be added later.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0, SQLite (`backend/food_map.db`)
- Frontend: React (Vite) + Leaflet (react-leaflet) with OpenStreetMap tiles
- `.env`, `data/*.json` and the SQLite file are gitignored

## Folder layout

```
backend/
  app/
    main.py          FastAPI app, CORS for the Vite dev server
    config.py        paths, DATABASE_URL
    db.py            engine/session, create tables
    models.py        places, reels, visits
    maps_link.py     "Open in Google Maps" URL builder
    schemas.py       Pydantic response/request models
    routers/         places.py, reels.py (review queue)
    importer/
      parse.py       load export files; "" and null -> None
      flags.py       per-reel flags
      matching.py    name similarity, address normalization, display name/address
      check.py       CLI: list reels by flag
      run.py         CLI: import + summary
  tests/
  requirements.txt
frontend/
  src/
    main.tsx         entry; imports Leaflet CSS
    api.ts           fetch wrapper + types mirroring backend/app/schemas.py
    index.css        styles (CSS variables on :root)
    pages/MapPage.tsx, ReviewPage.tsx
data/                Muse exports (gitignored)
```

## How to run

```bash
# backend (from backend/)
python -m venv .venv && .venv/Scripts/activate   # Windows; use bin/activate elsewhere
pip install -r requirements.txt
python -m app.importer.run                 # imports every data/reels*.json
python -m app.importer.run ../data/reels.json   # or one file
python -m app.importer.check               # list reels by flag; no DB writes
python -m app.importer.check --flag no_street_address
uvicorn app.main:app --reload              # API on :8000

# frontend (from frontend/)
npm install
npm run dev                                # Vite on :5173, proxies /api to :8000

# tests (from backend/)
pytest

# typecheck (from frontend/)
npm run typecheck
```

`.claude/launch.json` defines `api` (uvicorn on :8000) and `web` (Vite on :5173) for the Claude browser preview. The Vite dev server proxies `/api` to :8000, so the frontend uses relative URLs.

To start over, delete `backend/food_map.db` and re-run the import.

## Data model

- **places**: id, name, lat, lng, address, is_approximate (bool)
- **reels**: id, post_url (unique; the dedup key), posted_by, venue_raw, address_raw, city_raw, lat_raw, lng_raw, dish, muse_confidence, muse_note, place_id (nullable FK), status (`matched` / `needs_review` / `rejected`), flags (JSON list, see Reel flags), review_reason, source_file
- **reel_extra_places**: reel_id, place_id. Extra spots for multi-spot reels; `reels.place_id` stays the reel's main place.
- **visits**: id, place_id, user, visited (bool), visited_date, rating, notes. One row per (place_id, user). Single-user for now: `user` is `"me"`.

One place has many reels. The Google Maps link is computed (not stored) from name + address, falling back to lat/lng.

## Export format (Muse)

JSON array of objects with keys: venue, address, city, lat, lng, post_url, posted_by, dish, confidence, note.

- Missing values may be `null` or `""`: treat both as unknown. Strip whitespace on every string.
- Tolerate missing or extra keys. A row without post_url is skipped and counted.
- If a file fails to parse, report file, line and column (from `JSONDecodeError`) and stop. Never guess or partially repair. With several files, all are parsed before anything is written.
- confidence: `high` | `medium` | `low` | `none`.
- `dish` is a caption snippet cut at 140 chars; it can contain emoji and curly quotes (’).
- `venue` is sometimes ALL CAPS (copied from captions); place names are tidied to "Claire’s Crunch Cake".
- `address` often has a business-name prefix (`"Matzip, 33592 Alvarado Niles Rd, ..."`), ZIP+4, and `", United States"`. Place addresses drop the prefix and country.
- `venue` can carry annotations like `"Butter & Crumble (multi-spot reel)"`; stripped from place names.
- `note` is free text, sometimes several notes joined with `" | "`. Mixes cuisine hints, verification notes and location caveats.
- City-only addresses (`"Oakland, CA, United States"`) mean the pin is a city centroid; several different venues can share identical coordinates.

## Import rules

- `post_url` is unique. Re-importing only adds new reels; existing post_urls are skipped (counted as skipped), never updated or duplicated.
- Blocking flags (`no_venue`, `no_coords`, `coords_outside_bay_area`, `no_confidence`) or confidence `none` → reel `needs_review`, no place. `review_reason` says why.
- confidence `low`, or a `city_only_address` at any confidence → place with `is_approximate = true` at Muse's coordinates. Approximate places dedupe on normalized venue name + city (two reels of one pop-up share a place; two different pop-ups pinned to Oakland do not; one pop-up in two cities is two places).
- confidence `high` / `medium` with a street address → place at Muse's coordinates, `is_approximate = false`.
- Never dedupe places by name alone (names vary: "Stans Donuts" vs "Stan's Doughnut" at one address). Non-approximate places merge only on the same normalized street address **and** name score ≥ 80 (`matching.MIN_MERGE_NAME_SCORE`). Address alone never merges (food halls and malls share addresses).
- Multi-spot reels: import the pinned place normally, but set the reel to `needs_review` so other spots can be added.
- After each import print: imported, pinned, approximate, needs review (and how many of those are still on the map), skipped, merged into existing places, count per flag.

## Reel flags

Each reel gets a list of flags describing what is missing or questionable in its JSON row, stored in `reels.flags`. Computed from the row alone in `importer/flags.py`.

| flag | meaning | effect on import |
|---|---|---|
| `no_venue` | venue empty/null | needs_review, no place |
| `no_address` | address empty/null | none by itself |
| `city_only_address` | address is just "City, CA[, United States]" | approximate place |
| `no_street_address` | address has no street number (landmark, intersection, ZIP only) | none; pin may be rough |
| `no_city` | city empty/null | none |
| `no_coords` | lat or lng empty/null/non-numeric | needs_review, no place |
| `coords_outside_bay_area` | outside lat 36.8–38.9, lng −123.6 to −121.2 (also catches swapped lat/lng) | needs_review, no place |
| `no_confidence` | confidence empty or not high/medium/low/none | needs_review, no place |
| `multi_spot` | note or venue says the reel covers several spots | place imported, reel needs_review |

Where to see flags:
- `python -m app.importer.check [file] [--flag FLAG]`: count per flag, then the reels under each flag (venue, post_url).
- Import summary: count per flag.
- Review page: each reel shows its flags as badges, with a filter by flag.

## API (phase 1)

Interactive docs at http://localhost:8000/docs while the server runs.

- `GET /api/places` — every place with `visited`, `visited_date`, `google_maps_url` and its non-rejected reels (main + extra)
- `POST /api/places/{id}/visit` `{"visited": bool}` — set "been here". Takes the desired state rather than flipping, so a double click can't undo itself. Sets `visited_date` to today when turned on, clears it when turned off.
- `GET /api/flags` — flag code → description, for badges
- `GET /api/reels/review?flag=` — reels with status `needs_review`, optionally filtered by flag (422 on unknown flag)
- `POST /api/reels/{id}/place` `{"place_id": n}` or `{"new_place": {name, lat, lng, address?, is_approximate?}}`, plus `mode`:
  - `"replace"` (default): set the reel's main place, status `matched`
  - `"add"`: link an extra spot (multi-spot reels); reel stays in review
  - new places must be inside the Bay Area box (catches swapped lat/lng)
- `POST /api/reels/{id}/resolve` — keep the reel's place(s) and mark it `matched` (e.g. multi-spot reel with all spots added)
- `POST /api/reels/{id}/reject` — status `rejected`, unlinks its places

A place left with no reels is deleted, unless it's marked visited.

## Frontend (phase 1)

- Map page: one circle marker per place. Orange = to try, green = been here; approximate places are larger, dashed and translucent, and the popup says the location is approximate. Popup: name, address, "Open in Google Maps" link, "been here" checkbox (with date), reel links (@poster + dish snippet). Header shows place/visited counts and a legend.
  - Pins with identical coordinates are fanned out ~150 m around the shared point (`spreadOverlaps`) so each is clickable.
  - Leaflet measures its container once; `FitToPins` re-measures on resize and only fits the view once the container has a real size (otherwise a map mounted hidden puts every pin on one point).
- Review page: needs_review reels with Muse's venue/note, the reel link, flag badges and review_reason; filter by flag; attach to an existing place, enter a place (name, address, click the map for the pin), add extra spots to multi-spot reels then resolve, or reject.

## Out of scope (for now)

Auth, multiple users, deployment, filters, Google Places verification.
