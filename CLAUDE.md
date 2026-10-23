# food-map

Personal Bay Area restaurant map built from saved Instagram food reels. A tracker/checklist for two people (the owner and one friend), each with their own login and log; not a public app. Being moved online (Fly.io) so it works on a phone with the PC off.

Flow: Instagram saved reels → exported by Meta's Muse AI as JSON (`data/reels*.json`) → CLI import → SQLite → FastAPI → React + Leaflet map.

Pins use Muse's own coordinates. There is no Google Places (or any external API) call; each popup has a plain "Open in Google Maps" link instead. If pins turn out to be wrong, a verification step (Google Places or OpenStreetMap Nominatim) can be added later.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0, SQLite (`backend/food_map.db`)
- Frontend: React (Vite) + Leaflet (react-leaflet). Main map basemap: OpenFreeMap vector tiles rendered by MapLibre GL inside Leaflet (`@maplibre/maplibre-gl-leaflet`), no API key. Pin pickers (add-a-place, review page): OpenFreeMap's full `dark` style (`basemap.StreetBasemap`), since placing a pin needs streets. CARTO's tiles now require an API key, so don't use them.
- `.env`, `data/*.json`, `personal/` and the SQLite file are gitignored. The repo is public, so no personal data or secrets go in it

## Folder layout

```
backend/
  app/
    main.py          FastAPI app, CORS for the Vite dev server
    config.py        paths, DATABASE_URL
    db.py            engine/session, create tables, add new columns to existing DBs
    models.py        places, reels, visits
    maps_link.py     "Open in Google Maps" URL builder
    backup.py        personal/my-log.json: export after every change, restore onto a fresh DB
    auth.py          password hashing (scrypt), session cookies, require_user, login lockout
    users.py         CLI: add / passwd / list / remove accounts (no sign-up page)
    demo/            public demo mode: sample_reels.json (made-up places) + reset()
    tags.py          food type tags (keyword regexes over name, captions, Muse notes)
    schemas.py       Pydantic response/request models
    routers/         auth.py (login/logout/me), imports.py (Muse upload, recent imports), places.py, reels.py (review queue)
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
    App.tsx          title bar (back button on review) + hash routing (#/ map, #/review) + stats
    mapUtils.ts      teardrop pin icons (food emoji per tag), cluster bubbles, overlap spreading
    captions.ts      dishLine: reel caption → short "what to get" line for place cards
    components/VisitLog.tsx  been-here toggle, star rating, visit date, notes, favorite button
    components/TagEditor.tsx food tags + Edit: toggles, Save / Cancel / Reset to automatic
    components/PinPicker.tsx small street map: tap to place a pin, or "📍 Use my location"
    api.ts           fetch wrapper + types mirroring backend/app/schemas.py
    index.css        styles (CSS variables on :root)
    basemap.tsx      MinimalBasemap (stripped-down, main map) and StreetBasemap (full detail, pin pickers)
    pages/MapPage.tsx, ReviewPage.tsx, LoginPage.tsx, AddPlacePage.tsx
  public/            manifest.webmanifest + app icons (home-screen install)
  index.html         install tags (manifest, theme-color, apple-* for iPhone)
data/                Muse exports (gitignored)
Dockerfile           one image for both Fly apps (builds the map, then the Python server)
fly.toml             the real app (volume at /data); fly.demo.toml: the public demo (no volume)
personal/            my-log.json: the personal backup (gitignored; see Personal data)
README.md            the public front page: demo link, screenshots, features, highlights, quick start
ROADMAP.md           to-do list (open items, ideas, someday, done)
docs/setup.md        accounts, importing, upload endpoint, running, hosting, backups, tests
docs/screenshots/    README screenshots, taken from the demo (made-up data only)
LICENSE              MIT
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
python -m app.users add davy --name "Davy"   # make a login (asks for the password); first one takes over pre-login visits
python -m app.users list
uvicorn app.main:app --reload              # API on :8000

# frontend (from frontend/)
npm install
npm run dev                                # Vite on :5173, proxies /api to :8000

# tests (from backend/)
pytest

# typecheck (from frontend/)
npm run typecheck
```

**One server (how the hosted app runs):** `npm run build` in `frontend/`, then `uvicorn app.main:app` alone serves the built map at `/` and the API at `/api/*` (`main.mount_frontend`, gzip on). The Vite dev server is only for working on the frontend.

Settings come from environment variables (or `.env`), so the hosted server can point everything at a persistent volume:

| variable | default | what |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/food_map.db` | the database |
| `FOOD_MAP_EXPORTS_DIR` | `data/` | Muse exports the importer reads |
| `FOOD_MAP_PERSONAL_DIR` | `personal/` | where `my-log.json` is written |
| `FOOD_MAP_FRONTEND_DIST` | `frontend/dist/` | built map served at `/` |
| `FOOD_MAP_CORS_ORIGINS` | the Vite dev origins | comma-separated |
| `FOOD_MAP_IMPORT_TOKEN` | unset (token uploads off) | secret Muse sends as `Authorization: Bearer …` to `POST /api/import`; set it as a host secret, never commit it |
| `FOOD_MAP_DEMO` | unset | `true` makes this server the public demo (see Demo); never set it on the real app |
| `FOOD_MAP_COOKIE_SECURE` | `true` | login cookie only over https; set `false` in `.env` for plain-http local use in browsers other than Chrome |

`GET /api/health` returns `{"status": "ok"}`.

`.claude/launch.json` defines `api` (uvicorn on :8000) and `web` (Vite on :5173) for the Claude browser preview. The Vite dev server proxies `/api` to :8000, so the frontend uses relative URLs.

To start over, delete `backend/food_map.db` and re-run the import.

## Data model

- **places**: id, name, lat, lng, address, is_approximate (bool), tags_override (JSON list or null: hand-picked food tags; null = automatic)
- **reels**: id, post_url (unique; the dedup key), posted_by, venue_raw, address_raw, city_raw, lat_raw, lng_raw, dish, muse_confidence, muse_note, place_id (nullable FK), status (`matched` / `needs_review` / `rejected`), flags (JSON list, see Reel flags), review_reason, source_file (export file name, or `manual`), added_by (username, hand-added places only)
- **reel_extra_places**: reel_id, place_id. Extra spots for multi-spot reels; `reels.place_id` stays the reel's main place.
- **visits**: id, place_id, user (= `users.username`), visited (bool), visited_date, rating (1–5), notes, favorite (bool). One row per (place_id, user). Notes and favorite don't require a visit. Before logins existed `user` was `"me"`; the first account created takes those rows over.
- **users**: id, username (unique, lowercase), display_name, password_hash (`scrypt$n$r$p$salt$hash`), created_at. Made with `python -m app.users`; there is no sign-up page.
- **import_runs** (`ImportRun`): id, created_at, source (`upload` / `cli`), filename (with "(from muse)" / "(from <username>)"), ok, error, imported, pinned, approximate, needs_review, skipped, merged. Every import, uploaded or command-line, adds one.
- **sessions** (`LoginSession`): id, token_hash (SHA-256 of the cookie token; the raw token is never stored), user_id, created_at, expires_at (60 days).

Schema changes: `create_all` only creates missing tables, so a column added to an existing table must also be listed in `db._ADDED_COLUMNS`; `init_db` adds it with `ALTER TABLE` and keeps the data.

Food tags are computed, not stored (`tags.place_tags`), from keyword regexes over the place name, its reels' venue/caption, and Muse's notes (whole words only). They are deliberately broad, about 12 in all, not one per dish:
- cuisines (`tags.CUISINES`): Mexican, Korean, Chinese (incl. Taiwanese), Japanese, Thai, Vietnamese, Middle Eastern, Hawaiian, Pizza & Italian
- American (`tags.AMERICAN`): only when no cuisine above matched, so "fried chicken" at a Korean spot stays Korean
- groups that sit alongside a cuisine (`tags.GROUPS`): Seafood, Sweets & bakery (donuts, cakes, boba, coffee…)
Prefer widening an existing tag's keywords over adding a new tag. Edits re-tag every place on the next request, except places whose tags were picked by hand (`places.tags_override`), which keep their pick until reset. Hand-picked tags must come from the same fixed list (`tags.TAG_ORDER`), so the filter row stays short.

Places added by hand in the app (`POST /api/places`) get one reel with `source_file = "manual"` and `added_by`, whose `post_url` is the link they gave (an Instagram link in canonical form, so a later Muse export of that reel is skipped as known) or `manual:<random id>` without one. That keeps them like every other place: shared, backed up, filterable.

One place has many reels. The Google Maps link is computed (not stored) from name + address, falling back to lat/lng.

## Personal data

`personal/my-log.json` is the backup of everything people add by hand, written by `backup.save_log_quietly` after every endpoint that changes it, and restored with `python -m app.backup restore`. Version 2: `users.<username>.places[]` (been-here, visit date, rating, notes, favorite), a shared `tags[]` (hand-picked tags), and `manual_places[]` (places added by hand, which no Muse export can rebuild; restore recreates them first). Version-1 files (before logins, one person) still restore, into `--user` (default: the first account).
- **Personal data goes under `personal/` (gitignored), nowhere else.** The repo is public: never commit real exports, the database, the log, real names or screenshots of the real map. README screenshots come from the demo.
- Earlier commits contain only an empty `my-log.json`, so the history is clean.
- Places are keyed by their reels' post URLs, never database IDs, so a restore works after a fresh import.
- Output is sorted with no timestamps, and the file is only rewritten when its content changes, so diffs show only real edits.
- New per-place personal fields must be added to `backup._entry` and `backup.restore_log`, or they won't be backed up.
- Tests patch `backup.LOG_PATH` to a temp dir (autouse fixture in `tests/conftest.py`); never let a test write the real file.

## Export format (Muse)

JSON array of objects with keys: venue, address, city, lat, lng, post_url, posted_by, dish, confidence, note.

- Missing values may be `null` or `""`: treat both as unknown. Strip whitespace on every string.
- Tolerate missing or extra keys. A row without post_url is skipped and counted.
- Top level is a JSON array, or `{"reels": [...]}` (accepted explicitly; nothing else is).
- `post_url` is normalized on import (`parse.normalize_post_url`) to `https://www.instagram.com/reel/<id>/`: `/p/`, `/reels/`, `/tv/`, a username prefix and any query string (`?igsh=`) all map to the same reel, since `post_url` is the dedup key.
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
- confidence `low`, or a `city_only_address` at any confidence → place with `is_approximate = true` at Muse's coordinates (typically pop-ups, home cooks, or places Muse could only pin to a city). Approximate places dedupe on normalized venue name + city (two reels of one pop-up share a place; two different pop-ups pinned to Oakland do not; one pop-up in two cities is two places).
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

## Logins and friend mode

- Every `/api/*` route needs a login (`auth.require_user`, set on the `places` and `reels` routers), except `GET /api/health`, `GET /api/demo` and `POST /api/auth/login`. Anything new under `/api/` must stay behind it.
- Login sets an HttpOnly, SameSite=Lax cookie `yums_session` (Secure unless `FOOD_MAP_COOKIE_SECURE=false`), valid 60 days. Logout deletes the session server-side. Changing a password (`app.users passwd`) logs out every device.
- Wrong passwords: 5 for one username locks it for 15 minutes (`auth.LoginThrottle`, in memory). Unknown usernames get the same "Wrong username or password." error.
- Visits are per person (the logged-in username); each place also carries `others[]`, the other person's log (only if they logged something). Hand-picked food tags and review-queue actions are shared.
- Tests patch `routers.imports.DATA_DIR` to a temp dir (autouse fixture), so uploads never land in the real `data/`.
- Tests set `FOOD_MAP_COOKIE_SECURE=false` (conftest) and log in as test users `alice` / `bob` (`tests/test_api.py`). For browser checks, use a throwaway copy of the database with test accounts, never the real one.

## API (phase 1)

Interactive docs at http://localhost:8000/docs while the server runs.

- `POST /api/auth/login` `{"username", "password"}` → sets the cookie, returns `{username, display_name}`; 401 wrong login, 429 locked out
- `POST /api/auth/logout` (204), `GET /api/auth/me` → `{username, display_name}` or 401
- `POST /api/import` — Muse's upload: body is the export JSON. Auth: `Authorization: Bearer <FOOD_MAP_IMPORT_TOKEN>` (503 if no token is configured, 401 if wrong) or a logged-in session. Saves the body as `data/reels-upload-<UTC time>-<random>.json` first, then runs the normal import (known reels skipped). Returns `{saved_as, imported, pinned, approximate, needs_review, pinned_needing_review, skipped, merged, flags, skipped_details}`. 400 with line/column on bad JSON (file kept as `.invalid`), 413 over 5 MB, 409 if an import is already running.
- `GET /api/imports?limit=` — recent import runs, newest first (login required)

- `POST /api/places` — add a place by hand: `{name, lat, lng, address?, link?, is_approximate?, tags?, favorite?, visited?, notes?, force?}` → the place (201). 422 outside the Bay Area / bad link (must be http(s)) / unknown tag. 409 `{message, place_id, kind}`: `same_link` (that link is already on the map) or, unless `force`, `similar_nearby` (name score ≥ 80 within 150 m).
- `GET /api/places` — every place (in import order) with `others` (friend mode) and `city` (most common reel city, else parsed from address), `tags`, `visited`, `visited_date`, `rating`, `notes`, `favorite`, `google_maps_url` and its non-rejected reels (main + extra)
- `GET /api/stats` — `reels_saved` (non-rejected), `on_map` (places), `cities`, `needs_review`, and the logged-in person's own `visited`, `favorites`
- `POST /api/places/{id}/visit` — partial update of the visit log: any of `visited`, `visited_date`, `rating` (1–5), `notes`, `favorite`; only fields sent change, `null` clears rating/notes/date. `visited` takes the desired state rather than flipping, so a double click can't undo itself. Turning it on stamps today's date (unless one is sent); turning it off clears date and rating but keeps notes and favorite.
- `GET /api/tags` — every food tag, in display order
- `PUT /api/places/{id}/tags` `{"tags": [...]}` — pick a place's tags by hand (any subset of `GET /api/tags`, deduped and sorted; 422 on unknown tags), or `{"tags": null}` to go back to automatic. Places carry `tags_edited`.
- `GET /api/flags` — flag code → description, for badges
- `GET /api/reels/review?flag=` — reels with status `needs_review`, optionally filtered by flag (422 on unknown flag)
- `POST /api/reels/{id}/place` `{"place_id": n}` or `{"new_place": {name, lat, lng, address?, is_approximate?}}`, plus `mode`:
  - `"replace"` (default): set the reel's main place, status `matched`
  - `"add"`: link an extra spot (multi-spot reels); reel stays in review
  - new places must be inside the Bay Area box (catches swapped lat/lng)
- `POST /api/reels/{id}/resolve` — keep the reel's place(s) and mark it `matched` (e.g. multi-spot reel with all spots added)
- `POST /api/reels/{id}/reject` — status `rejected`, unlinks its places

A place left with no reels is deleted, unless you've logged it (visited, favorite or notes).

## Frontend (phase 1)

- Phone first: it's mostly used on the go. Installable to the home screen (`public/manifest.webmanifest`, "Yums Map", standalone, icons rendered from an HTML pin to PNG). Full-screen on iPhone runs under the status bar, so `.app` pads with `env(safe-area-inset-*)`. Under 600px: inputs are 16px (iOS zooms on smaller), bigger tap targets, full-width Pick for me. Check layouts at 390×844.
- Look: dark theme modelled on a Muse-drafted mockup ("Bay Area Yums Map"). Colors are CSS variables on `:root` in `index.css`: coral `--todo` = to try, teal `--visited` = been here, dashed outline = approximate.
- Basemap (`basemap.tsx`): fetches OpenFreeMap's Positron style, recolors it with the dark `PALETTE`, and keeps only background, water, freeways (motorway incl. bridges/tunnels), trunk highways, US/interstate route shields, water names, and city/town labels. Everything else (buildings, minor roads, parks, rail, airports, boundaries, POIs) is dropped. To show more or less, edit the `KEEP` set; layer ids are from the Positron style. Falls back to OSM raster tiles if the style can't load.
- Routes (hash): `#/` map, `#/review`, `#/add`, `#/place/<id>` (map flies to that place, then the hash resets to `#/`).
- Add a place (`#/add`, the ＋ in the title bar on the map): name; pin by tapping the street map, "📍 Use my location" (needs https or localhost) or typed coordinates; optional link, address, food tags (none = automatic), ★ want to go (on by default), been here, notes. A 409 shows the server's message with "Show it" and, for a similar place nearby, "Add anyway". Cards and popups say "added by <name>" instead of "saved from @…"; a hand-added place without a link shows no reel link.
- Login screen (`LoginPage`) whenever `GET /api/auth/me` fails or any call returns 401 (`api.ts` fires `AUTH_REQUIRED_EVENT`). Title bar: avatar with your initial → "Logged in as …" / Log out.
- Map page, top to bottom:
  - stat chips from `GET /api/stats` (reels saved, on the map, cities; "been there" and "favorites" toggle the matching pin filter; waiting for review → `#/review`)
  - "🎲 Pick for me" (end of the filter row, `pickForMe`): random place from what's shown, preferring not-visited ones (falls back to visited if that's all that's shown), never the same place twice in a row; flies to it via `focus` and shows a "Picked … · Pick again · Dismiss" note above the map, or "Nothing to pick" when no places are shown
  - "Last import <when> · N new (M to review)" line under the chips, from `GET /api/imports?limit=1` (red if it failed)
  - search (name, city, address, tags, notes, caption, poster; every word must match), City and Pins filters (to try / been here / favorites / both want to go (you and the other person both starred it) / exact / approximate), and a horizontally scrolling row of food-tag chips (single select, with counts); changing a filter refits the map
  - legend, then the map card: teardrop pins (`L.divIcon`) showing a food emoji for the place's first tag (`mapUtils.TAG_ICONS`, 🍽️ if untagged), ★ badge on favorites. No numbers on pins: they read like a ranking. Only cluster bubbles show a count. `GET /api/places` still returns import order (by id), used as the list's "Default" order.
  - clustering (`react-leaflet-cluster`): crowded pins merge into count bubbles (coral; teal when every place inside is visited) below zoom 14 (`NO_CLUSTER_ZOOM`). The cluster plugin needs `maxZoom` on `MapContainer`, since the vector basemap doesn't set one. `removeOutsideVisibleBounds` is off: with it on, the plugin drops markers after a pan, and removing a marker closes its popup.
  - the popup root stops click propagation: React handles popup clicks first (at the portal container), so a button that swaps itself out (Edit, Save tags, Cancel) is gone from the DOM by the time Leaflet checks whether the click came from the popup, and Leaflet would close it as a map click.
  - popup height is capped in CSS (`.popup`), not with Leaflet's `maxHeight`: Leaflet measures before React fills the popup. When the popup grows (tag editor opens, "Been here" adds the rating row) it calls `marker.getPopup().update()` so Leaflet re-pans to fit it in the map card.
  - popup: name + favorite star, address, food tags with "Edit" (toggles for all tags, Save / Cancel / "Reset to automatic"; "edited" badge when hand-picked), approximate note, "Open in Google Maps", visit log (been-here toggle; once visited, 1–5 stars and visit date; notes box that saves on blur), the other person's line ("Tess: ★ wants to go · been ★★★★ “notes”"), reel links
  - list of matching places, sortable by default (import order) / favorites first / top rated / recently visited: the same food emoji in a status-colored circle, name, dish line (`captions.dishLine`: the caption cut at the first sign of location (📍, "in Hayward, CA", the place's own name, a street address, an @handle) or the end of the first sentence, dangling words and edge emoji dropped, ALL CAPS → sentence case, "…" only if Muse's 140-char snippet cut it mid-sentence), tags, stars + visit date, notes, the other person's line (no notes), city, "approximate location" (only on approximate places), "saved from @poster +N", favorite star and "Been here?" toggle. Clicking a card flies to its pin (opening its cluster) and opens the popup.
  - Pins with identical coordinates are fanned out ~150 m around the shared point (`spreadOverlaps`) so each is clickable.
  - Leaflet measures its container once; `FitToPins` re-measures on resize and only fits the view once the container has a real size (otherwise a map mounted hidden puts every pin on one point).
- Review page (`#/review`): one card per needs_review reel with venue, @poster reel link, Muse confidence/address/note, caption, flag badges (hover for description) and review_reason; filter by flag (with counts). "Fix" opens a panel:
  - New place: name, optional address, click the mini map to drop the pin (or type lat/lng), approximate checkbox
  - Existing place: search places on the map by name/address, "Use this"
  - Reels that already have a place (multi-spot) choose "Add another spot from this reel" (default) or "Replace", then "Done: keep …" resolves them
  - "Reject reel" (asks to confirm)
  - Links to the reel and a Google Maps search for Muse's venue + address to help find the spot

Testing note: the Claude browser pane does not run `requestAnimationFrame` while hidden, so Leaflet/MapLibre draw nothing (paths are `M0 0`) and map clicks convert to wrong coordinates there. For screenshots, drive headless Chrome over the DevTools protocol (real waits + `Emulation.setDeviceMetricsOverride` for phone size). Don't use `--virtual-time-budget`: it stalls MapLibre's workers and the basemap comes out blank. Plain `--window-size` can't go below ~500px wide on Windows. Test clicks with CDP `Input.dispatchMouseEvent` (real pointer events and hit-testing), not `el.click()`/`dispatchEvent`: synthetic clicks hid the popup-closing bug where a button that removes itself on click looked like a map click to Leaflet.

## Hosting and the demo

Two Fly.io apps from the same image (`Dockerfile`; Fly builds it remotely, no Docker needed locally). On this PC, deploy with `--depot=false`: the Depot builder fails with a TLS "unknown authority" error.
- **Real app** (`fly.toml`, `fly deploy`): database, uploads and `my-log.json` on the `yums_data` volume at `/data`. `FOOD_MAP_IMPORT_TOKEN` is a Fly secret. Accounts are made on the server: `fly ssh console`, then `cd /app/backend && python -m app.users add …` (it asks for the password, so it needs the interactive shell).
- **Public demo** (`fly.demo.toml`), `FOOD_MAP_DEMO=true`, for the resume link. Live at https://yums-map-demo.fly.dev. Deploy with `fly deploy --config fly.demo.toml --remote-only --ha=false --depot=false`. Keep it to **one machine** (`--ha=false`): each machine has its own database, so a second one would split visitors' logins and data. `app/demo`:
  - On every start (machines sleep when idle, so often) and every 24 h, `demo.reset()` drops all tables and refills them: `sample_reels.json` (made-up places in Muse's format, including pop-ups and 3 reels for the review page) through the normal importer, accounts `demo` (password public, on purpose) and `sam` (the friend; random password), and a few visits for each.
  - `GET /api/demo` (public; 404 on the real app) returns the demo login; the login page shows "Try the demo" and the title bar a "Demo · made-up places · source code" line.
  - Uploads are 403; the demo accounts are exempt from login lockout (otherwise one visitor could lock everyone out). Everything else works, and is wiped at the next reset.
  - Its database lives in `/tmp` inside the machine: never point it at real data.

## Out of scope (for now)

Public sign-up, more than a couple of users, Google Places verification.
