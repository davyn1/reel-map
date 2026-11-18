# food-map

Personal Bay Area restaurant map built from saved Instagram food reels. A tracker/checklist for two people (the owner and one friend), each with their own login and log; not a public app. Being moved online (Fly.io) so it works on a phone with the PC off.

Flow: Instagram saved reels → exported by Meta's Muse AI as JSON (`data/reels*.json`) → CLI import → SQLite → FastAPI → React + Leaflet map.

Pins use Muse's own coordinates. There is no Google Places (or any external API) call; each popup has a plain "Open in Google Maps" link instead. If pins turn out to be wrong, a verification step (Google Places or OpenStreetMap Nominatim) can be added later.

After finishing a feature or changing tests, CI, or deployment, update docs/FEATURES.md to match.

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
    alerts.py        Discord alerts when Muse's uploads fail or go quiet; CLI: test / check
    sync.py          live sync: bumps app_state.version on every change to shared data (SQLAlchemy flush hook)
    demo/            public demo mode: sample_reels.json (made-up places) + reset()
    tags.py          food type tags (keyword regexes over name, captions, Muse notes)
    schemas.py       Pydantic response/request models
    routers/         auth.py (login/logout/me), imports.py (Muse upload, recent imports), places.py, reels.py (review queue), version.py (live sync)
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
    App.tsx          hash routing, account menu (avatar), counts and last import, top bar on review/add
    mapUtils.ts      teardrop pin icons (food emoji per tag, star badge), cluster bubbles, overlap spreading
    captions.ts      dishLine: reel caption → short "what to get" line for place cards
    components/VisitLog.tsx  been-here button, star rating, visit date, notes, want-to-go star, friend line
    components/TagEditor.tsx food tags + Edit: toggles, Save / Cancel / Reset to automatic
    components/PinPicker.tsx small street map: tap to place a pin, or "Use my location"
    components/BottomSheet.tsx the map's sheet: peek / half / full, drag or tap the handle
    components/Icons.tsx     the drawn icon set (no emoji or glyphs as icons)
    api.ts           fetch wrapper + types mirroring backend/app/schemas.py
    liveSync.ts      live sync: poll GET /api/version, fire a data-changed event the screens re-fetch on
    index.css        styles (CSS variables on :root)
    basemap.tsx      MinimalBasemap (stripped-down, main map) and StreetBasemap (full detail, pin pickers)
    pages/MapPage.tsx  full-screen map, top bar, food row, sheet (list / place / filters)
    pages/ReviewPage.tsx, LoginPage.tsx, AddPlacePage.tsx
  public/            manifest.webmanifest + app icons (home-screen install)
  index.html         install tags (manifest, theme-color, apple-* for iPhone)
data/                Muse exports (gitignored)
.github/workflows/   ci.yml (tests, typecheck, Docker build; then deploys the demo on main), deploy-map.yml (real map, manual), wake.yml (daily wake-up for the quiet check)
Dockerfile           one image for both Fly apps (builds the map, then the Python server)
fly.toml             the real app (volume at /data); fly.demo.toml: the public demo (no volume)
personal/            my-log.json: the personal backup (gitignored; see Personal data)
README.md            the public front page: demo link, screenshots, features, highlights, quick start
ROADMAP.md           to-do list (open items, ideas, someday, done)
docs/setup.md        accounts, importing, upload endpoint, running, hosting, backups, tests
docs/FEATURES.md     factual feature, testing, infrastructure and security reference (with file paths)
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

**One server (how the hosted app runs):** `npm run build` in `frontend/`, then `uvicorn app.main:app` alone serves the built map at `/` and the API at `/api/*` (`main.mount_frontend`, gzip on). `main.FrontendFiles` sets the cache headers: everything outside `assets/` (the page, manifest, icons) is `no-cache`, so a phone re-checks it on every load (a cheap 304) and picks up a deploy at once; Vite's content-hashed `assets/` files are cached for a year (`immutable`). Without this, the home-screen app kept showing the old app after a deploy. The Vite dev server is only for working on the frontend.

Settings come from environment variables (or `.env`), so the hosted server can point everything at a persistent volume:

| variable | default | what |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/food_map.db` | the database |
| `FOOD_MAP_EXPORTS_DIR` | `data/` | Muse exports the importer reads |
| `FOOD_MAP_PERSONAL_DIR` | `personal/` | where `my-log.json` is written |
| `FOOD_MAP_FRONTEND_DIST` | `frontend/dist/` | built map served at `/` |
| `FOOD_MAP_CORS_ORIGINS` | the Vite dev origins | comma-separated |
| `FOOD_MAP_IMPORT_TOKEN` | unset (token uploads off) | secret Muse sends as `Authorization: Bearer …` to `POST /api/import`; set it as a host secret, never commit it |
| `FOOD_MAP_ALERT_WEBHOOK` | unset (alerts off) | Discord webhook URL for upload alerts (see Upload alerts); a host secret, never commit it |
| `FOOD_MAP_QUIET_DAYS` | `7` | days without a Muse upload before a "gone quiet" alert |
| `FOOD_MAP_DEMO` | unset | `true` makes this server the public demo (see Demo); never set it on the real app |
| `FOOD_MAP_COOKIE_SECURE` | `true` | login cookie only over https; set `false` in `.env` for plain-http local use in browsers other than Chrome |

`GET /api/health` returns `{"status": "ok"}`.

`.claude/launch.json` defines `api` (uvicorn on :8000) and `web` (Vite on :5173) for the Claude browser preview. The Vite dev server proxies `/api` to :8000, so the frontend uses relative URLs.

To start over, delete `backend/food_map.db` and re-run the import.

## Data model

- **places**: id, name, lat, lng, address, is_approximate (bool), tags_override (JSON list or null: hand-picked food tags; null = automatic), removed (bool: taken off the map by hand, see Removing a place)
- **reels**: id, post_url (unique; the dedup key), posted_by, venue_raw, address_raw, city_raw, lat_raw, lng_raw, dish, muse_confidence, muse_note, place_id (nullable FK), status (`matched` / `needs_review` / `rejected`), flags (JSON list, see Reel flags), review_reason, source_file (export file name, or `manual`), added_by (username, hand-added places only)
- **reel_extra_places**: reel_id, place_id. Extra spots for multi-spot reels; `reels.place_id` stays the reel's main place.
- **visits**: id, place_id, user (= `users.username`), visited (bool), visited_date, rating (1–5), notes, favorite (bool). One row per (place_id, user). Notes and favorite don't require a visit. Before logins existed `user` was `"me"`; the first account created takes those rows over.
- **users**: id, username (unique, lowercase), display_name, password_hash (`scrypt$n$r$p$salt$hash`), created_at. Made with `python -m app.users`; there is no sign-up page.
- **import_runs** (`ImportRun`): id, created_at, source (`upload` / `cli`), filename (with "(from muse)" / "(from <username>)"), ok, error, imported, pinned, approximate, needs_review, skipped, merged. Every import, uploaded or command-line, adds one.
- **alerts_sent** (`AlertSent`): kind (`upload_failed` / `wrong_token` / `quiet`), sent_at. When each Discord alert last went out, for cooldowns.
- **app_state** (`AppState`): one row (id 1) with `version`, bumped in the same transaction by every flush that adds, changes or deletes anything except login sessions and alert bookkeeping (`sync.py`, a `before_flush`/`after_flush` hook on SQLAlchemy's `Session` class, registered by `init_db`, so requests, the CLI importer, the demo reset and tests all count). A rolled-back change doesn't bump it. Bulk `UPDATE`s skip flush events; the only one is the CLI's one-off takeover of pre-login visits.
- **sessions** (`LoginSession`): id, token_hash (SHA-256 of the cookie token; the raw token is never stored), user_id, created_at, expires_at (60 days).

Schema changes: `create_all` only creates missing tables, so a column added to an existing table must also be listed in `db._ADDED_COLUMNS`; `init_db` adds it with `ALTER TABLE` and keeps the data.

Food tags are computed, not stored (`tags.place_tags`), from keyword regexes over the place name, its reels' venue/caption, and Muse's notes (whole words only). They are deliberately broad, about 12 in all, not one per dish:
- cuisines (`tags.CUISINES`): Mexican, Korean, Chinese (incl. Taiwanese), Japanese, Thai, Vietnamese, Middle Eastern, Hawaiian, Pizza & Italian
- American (`tags.AMERICAN`): only when no cuisine above matched, so "fried chicken" at a Korean spot stays Korean
- groups that sit alongside a cuisine (`tags.GROUPS`): Seafood, Sweets & bakery (donuts, cakes, boba, coffee…)
Prefer widening an existing tag's keywords over adding a new tag. Edits re-tag every place on the next request, except places whose tags were picked by hand (`places.tags_override`), which keep their pick until reset. Hand-picked tags must come from the same fixed list (`tags.TAG_ORDER`), so the filter row stays short.

Places added by hand in the app (`POST /api/places`) get one reel with `source_file = "manual"` and `added_by`, whose `post_url` is the link they gave (an Instagram link in canonical form, so a later Muse export of that reel is skipped as known) or `manual:<random id>` without one. That keeps them like every other place: shared, backed up, filterable.

Removing a place ("Remove from map" in the popup, e.g. after unsaving its reel on Instagram) only sets `places.removed`; nothing is deleted. Its reels stay linked, so later Muse exports skip them as known (a new reel that merges into it stays hidden too), and its log and tags come back with Undo. Removed places are left out of `GET /api/places`, the stats counts and the add-a-place nearby check; adding one back by the same link un-removes it. Imports never remove anything on their own: a reel missing from a full export is ignored, so a cut-off export can't wipe the map.

One place has many reels. The Google Maps link is computed (not stored) from name + address, falling back to lat/lng.

## Personal data

`personal/my-log.json` is the backup of everything people add by hand, written by `backup.save_log_quietly` after every endpoint that changes it, and restored with `python -m app.backup restore`. Version 2: `users.<username>.places[]` (been-here, visit date, rating, notes, favorite), a shared `tags[]` (hand-picked tags), a shared `removed[]` (places taken off the map, kept hidden on restore), and `manual_places[]` (places added by hand, which no Muse export can rebuild; restore recreates them first). Version-1 files (before logins, one person) still restore, into `--user` (default: the first account).
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

- Every `/api/*` route needs a login (`auth.require_user`, set on the `places` and `reels` routers), except `GET /api/health`, `GET /api/demo`, `GET /api/auth/mode` and `POST /api/auth/login`. Anything new under `/api/` must stay behind it.
- Login sets an HttpOnly, SameSite=Lax cookie `yums_session` (Secure unless `FOOD_MAP_COOKIE_SECURE=false`), valid 60 days. Logout deletes the session server-side. Changing a password (`app.users passwd`) logs out every device.
- Passcode login: when the server has exactly one account (and isn't the demo), `GET /api/auth/mode` returns `{"passcode": true}` and the login screen shows only a "Passcode" box; `POST /api/auth/login` without a username logs into that account ("Wrong passcode." on failure, 422 "Enter a username." once there are two accounts). The real map uses this: one account shared by the owner and a friend, so friend mode has nothing to show there. A username still works too.
- Wrong passwords: 5 for one username locks it for 15 minutes (`auth.LoginThrottle`, in memory). Unknown usernames get the same "Wrong username or password." error.
- Visits are per person (the logged-in username); each place also carries `others[]`, the other person's log (only if they logged something). Hand-picked food tags and review-queue actions are shared.
- Tests patch `routers.imports.DATA_DIR` to a temp dir (autouse fixture), so uploads never land in the real `data/`.
- Tests set `FOOD_MAP_COOKIE_SECURE=false` (conftest) and log in as test users `alice` / `bob` (`tests/test_api.py`). For browser checks, use a throwaway copy of the database with test accounts, never the real one.

## API (phase 1)

Interactive docs at http://localhost:8000/docs while the server runs.

- `POST /api/auth/login` `{"username"?, "password"}` → sets the cookie, returns `{username, display_name}`; 401 wrong login, 429 locked out. No username = passcode login (single account only, else 422)
- `GET /api/auth/mode` (public) → `{"passcode": bool}`: true when there's exactly one account and this isn't the demo
- `POST /api/auth/logout` (204), `GET /api/auth/me` → `{username, display_name}` or 401
- `POST /api/import` — Muse's upload: body is the export JSON. Auth: `Authorization: Bearer <FOOD_MAP_IMPORT_TOKEN>` (503 if no token is configured, 401 if wrong) or a logged-in session. Saves the body as `data/reels-upload-<UTC time>-<random>.json` first, then runs the normal import (known reels skipped). Returns `{saved_as, imported, pinned, approximate, needs_review, pinned_needing_review, skipped, merged, flags, skipped_details}`. 400 with line/column on bad JSON (file kept as `.invalid`), 413 over 5 MB, 409 if an import is already running.
- `GET /api/imports?limit=` — recent import runs, newest first (login required)

- `POST /api/places` — add a place by hand: `{name, lat, lng, address?, link?, is_approximate?, tags?, favorite?, visited?, notes?, force?}` → the place (201). 422 outside the Bay Area / bad link (must be http(s)) / unknown tag. 409 `{message, place_id, kind}`: `same_link` (that link is already on the map) or, unless `force`, `similar_nearby` (name score ≥ 80 within 150 m).
- `GET /api/places` — every place still on the map (in import order; removed ones left out) with `others` (friend mode) and `city` (most common reel city, else parsed from address), `tags`, `visited`, `visited_date`, `rating`, `notes`, `favorite`, `google_maps_url` and its non-rejected reels (main + extra)
- `GET /api/stats` — `needs_review`, and the logged-in person's own `visited`, `favorites` (what the map's chips show)
- `GET /api/version` → `{version, build}`: `version` goes up whenever shared data changes (see `app_state`); `build` is the served app's main script (`assets/index-<hash>.js`, read from the built `index.html`, re-read only when it changes; `null` when no built map is served). `Cache-Control: no-store`. Open apps poll it every 10 s, re-fetch only when `version` moved, and offer a reload when `build` differs from the script they're running
- `POST /api/places/{id}/visit` — partial update of the visit log: any of `visited`, `visited_date`, `rating` (1–5), `notes`, `favorite`; only fields sent change, `null` clears rating/notes/date. `visited` takes the desired state rather than flipping, so a double click can't undo itself. Turning it on stamps today's date (unless one is sent); turning it off clears date and rating but keeps notes and favorite.
- `PUT /api/places/{id}/removed` `{"removed": bool}` — take a place off the map or bring it back (404 unknown place); returns the place
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

- Phone first: it's mostly used on the go. Installable to the home screen (`public/manifest.webmanifest`, "Yums Map", standalone, icons rendered from an HTML pin to PNG). Full-screen on iPhone runs under the status bar and over the home indicator, so the map's top bar pads with `env(safe-area-inset-top)` and the sheet, ＋ button and toasts add `env(safe-area-inset-bottom)` on top of their heights. Inputs are 16px under 600px (iOS zooms on smaller). Tap targets are 44px. Check layouts at 390×844; at 900px and up the sheet becomes a 420px panel on the left.
- Look ("quiet and confident", redesigned with Impeccable after a critique found it cluttered and generic): near-black neutrals, and color only where it means something. CSS variables on `:root` in `index.css`: coral `--todo` = to try, teal `--visited` = been here, gold `--fav` = want to go (the star), amber `--warn` = needs a look, red `--danger` = errors; dashed outline = approximate. Actions and links are off-white (`button.primary` is off-white with dark text). Pills (`.chip`) are only for toggle chips; everything else has small corners (`--r-sm/md/lg`). Type scale `--fs-xs` … `--fs-lg`, no uppercase. Visible `:focus-visible` ring, themed selection and scrollbars.
- Icons: one drawn set in `components/Icons.tsx` (24px grid, 1.75 stroke). Controls never use emoji or Unicode glyphs as icons; food emoji stay on pins and list rows because they're content (the kind of food).
- Basemap (`basemap.tsx`): fetches OpenFreeMap's Positron style, recolors it with the dark `PALETTE`, and keeps only background, water, freeways (motorway incl. bridges/tunnels), trunk highways, US/interstate route shields, water names, and city/town labels. Everything else (buildings, minor roads, parks, rail, airports, boundaries, POIs) is dropped. To show more or less, edit the `KEEP` set; layer ids are from the Positron style. Falls back to OSM raster tiles if the style can't load.
- Routes (hash): `#/` map, `#/review`, `#/add`, `#/place/<id>` (map opens that place, then the hash resets to `#/`). The map route is full-screen (no `.app` wrapper); review and add have a top bar with a back button, the title and the account menu.
- Account menu (`AccountMenu` in `App.tsx`, the avatar): "Logged in as …", "Sort out reels (N)" → `#/review` (only when there are any), the last import line from `GET /api/imports?limit=1` (red if it failed), the demo note and source link on the demo, and Log out. A dot on the avatar means something there wants attention (amber: reels to sort out; red: the last import failed). Closes on an outside tap or Esc.
- Add a place (`#/add`, the round ＋ button over the map): name; pin by tapping the street map or "Use my location" (needs https or localhost); approximate checkbox; "Type coordinates" folded away; want to go (on by default), been here, notes; "Link, address and food type" folded away (food tags: none = automatic). A 409 shows the server's message with "Show it" and, for a similar place nearby, "Add anyway". Rows and the place view say "by <name>" instead of "@poster"; a hand-added place without a link shows no reel link.
- Login screen (`LoginPage`) whenever `GET /api/auth/me` fails or any call returns 401 (`api.ts` fires `AUTH_REQUIRED_EVENT`).
- Map screen (`MapPage`): the map fills the screen, with three things over it.
  - Top bar (`.map-bar`): search (name, city, address, tags, notes, caption, poster; every word must match), the Filter button (a badge counts the filters on), the avatar.
  - Food-type row (`.food-row`) floating on the map's top edge: single-select chips with counts, scrolling sideways, faded at the right edge so it reads as scrollable.
  - Bottom sheet (`components/BottomSheet.tsx`): rests at peek (84px: just the summary row; the body is hidden), half or full; drag its header (the move and release are followed on the whole window, the header can't be text-selected, and it snaps to the rest nearest where the sheet is heading from its release speed, so a flick moves one step and a long swipe goes all the way), or tap the handle. It reports its height (`--sheet-h`) so the map keeps pins, the ＋ button, the toasts and the Leaflet attribution (bottom left) clear of it. Each new view starts scrolled to the top. Three views (`mode`):
    - list: "N places" (or "N of M places" + "Clear filters"), "Pick for me", a demo note on the demo, then one row per place: the food emoji in a status-colored circle, name (+ gold star if want to go), dish line (`captions.dishLine`), "city · first tag · approximate pin · ★ rating", and a round been-here toggle. Tapping a row opens the place.
    - place (`PlaceView`): back to "Places", star (want to go) in the header; name, city and tags, dish line; "Mark been here" / "Been here" and "Directions" (the Google Maps link); once visited, 1–5 stars and the visit date; notes (saved on blur with a "Saved" tick, and also when the view closes mid-note); the other person's line; food type with Edit (toggles, Save / Cancel / "Back to automatic"), the reel links ("Saved from") or "Added … by", the address and the approximate note; "Remove from map" (asks to confirm, then a "Removed … · Undo" toast).
    - filters: Show (Everything / To try / Been here N / Want to go N / Both want to go), Pins (Any / Exact address / Approximate), City, Sort the list (order saved / want to go first / top rated / recently visited), "Clear all", "Show N places". Changes apply live and refit the map.
  - Opening a place (a row, a pin, Pick for me, `#/place/<id>`) raises the sheet to half and flies the map so the pin sits in the strip between the top bar and the sheet (`FlyToSelected`), marking it selected. Tapping the bare map or Esc closes the place view.
  - "Pick for me" (`pickForMe`): random place from what's shown, preferring not-visited ones (falls back to visited if that's all that's shown), never the same place twice in a row; opens it with a "Picked for you · Pick again" line, or a "Nothing to pick" toast.
  - Pins: teardrops (`L.divIcon`) with the food emoji of the place's first tag (`mapUtils.TAG_ICONS`, 🍽️ if untagged), a drawn gold star badge on want-to-go places, and the place name as the marker's title. No numbers on pins: they read like a ranking. No Leaflet popups: the sheet is the place view. No zoom buttons on the main map (pinch or scroll).
  - Clustering (`react-leaflet-cluster`): crowded pins merge into count bubbles (coral; teal when every place inside is visited) below zoom 14 (`NO_CLUSTER_ZOOM`). The cluster plugin needs `maxZoom` on `MapContainer`, since the vector basemap doesn't set one. `removeOutsideVisibleBounds` is off: with it on, the plugin drops markers after a pan.
  - Pins with identical coordinates are fanned out ~150 m around the shared point (`spreadOverlaps`) so each is tappable.
  - Leaflet measures its container once; `FitToPins` re-measures on resize and only fits the view once the container has a real size (otherwise a map mounted hidden puts every pin on one point). It fits with padding for the top bar and food row above and the sheet below.
  - `GET /api/places` still returns import order (by id), used as the list's "order saved" sort.
  - Live sync (`liveSync.ts`): `App` runs one `useVersionPoller`, which asks `GET /api/version` every 10 s (`POLL_MS`) while the app is on screen and right away when it comes back (`visibilitychange`, window `focus`, `pageshow`; one request at a time), and nothing while hidden. When the number moved it fires `DATA_CHANGED_EVENT`; `useOnDataChanged` subscribers re-fetch: the map its places, `App` the counts and the last import, the review page its queue. Your own changes move the number too, so they cost one extra re-fetch that changes nothing on screen. `mergePlaces` keeps the old object for every unchanged place (and the old list if nothing changed). A re-fetch that was in flight when a change was made here is not shown but retried a second later (`edits` counter), since its data may be older and the poller has already moved past that version. Failures are silent (offline: keep what's shown). Filters, the map view, the open place and a half-typed note stay as they are; a place that disappears closes its view.
  - New version note (`UpdateNote` in `App.tsx`): the poller also compares `build` with the page's own main script (`runningBuild()`); when they differ (a deploy while the page stayed open, or a home-screen app resumed from the background) it fires `NEW_BUILD_EVENT` once and a "New version · Reload" pill shows under the top bar, on every screen. Never under the Vite dev server (no hashed script).
  - Marker positions keep the same array while a place hasn't moved (`positions` in `MapPage`). react-leaflet compares `position` by reference, and the cluster plugin handles a "moved" marker by taking it out and putting it back. Without this, any change to the places list (a refresh, a been-here tick) did that to every marker.
- Review page (`#/review`, "Sort out reels"): one entry per needs_review reel: the venue (or "Unnamed spot"), @poster reel link and Muse's address, plain-language flag badges (`FLAG_LABELS`: "No name", "No location", "Several spots"…; the server's description is the title), the review reason, the caption, and "More from Muse" (confidence and note) folded away; a Show filter by flag (with counts). "Fix" opens a panel:
  - New place: name, optional address, tap the mini map to drop the pin, approximate checkbox, "Type coordinates" folded away
  - A place already on the map: search places by name/address, "Use this"
  - Reels that already have a place (multi-spot) choose "Add another spot from this reel" (default) or "Replace", then "Done: keep …" resolves them
  - "Reject reel" (asks to confirm)
  - Links to the reel and a Google Maps search for Muse's venue + address to help find the spot

Testing note: the Claude browser pane does not run `requestAnimationFrame` while hidden, so Leaflet/MapLibre draw nothing (paths are `M0 0`) and map clicks convert to wrong coordinates there. For screenshots, drive headless Chrome over the DevTools protocol (real waits + `Emulation.setDeviceMetricsOverride` for phone size). Don't use `--virtual-time-budget`: it stalls MapLibre's workers and the basemap comes out blank. Plain `--window-size` can't go below ~500px wide on Windows. Test clicks and drags with CDP `Input.dispatchMouseEvent` (real pointer events and hit-testing), not `el.click()`/`dispatchEvent`: synthetic clicks hid a popup-closing bug in the old design, and real mouse drags caught the sheet losing a drag once the pointer left its header. A mouse drag that should snap to the nearest rest needs a short pause before release, like a finger; without one it reads as a flick.

## Hosting and the demo

Two Fly.io apps from the same image (`Dockerfile`; Fly builds it remotely, no Docker needed locally). On this PC, deploy with `--depot=false`: the Depot builder fails with a TLS "unknown authority" error.

CI/CD (GitHub Actions): `ci.yml` runs backend pytest (throwaway paths; the two real-export tests skip), the frontend typecheck and a Docker build (not pushed) on every push and PR, caching pip/npm/Docker layers. When all pass on a push to `main`, its `deploy-demo` job deploys the demo (`FLY_DEMO_DEPLOY_TOKEN`; skipped if unset). The real map never deploys on its own: `deploy-map.yml` is a manual "Run workflow" that deploys `main` only if that commit's CI run succeeded (`FLY_REAL_DEPLOY_TOKEN`). Both tokens are Fly deploy tokens scoped to one app. Runs on `main` aren't cancelled by newer pushes, so a deploy never stops halfway. Deploying by hand from this PC still works.
- **Real app** (`fly.toml`, `fly deploy`): database, uploads and `my-log.json` on the `yums_data` volume at `/data`. `FOOD_MAP_IMPORT_TOKEN` is a Fly secret. Accounts are made on the server: `fly ssh console`, then `cd /app/backend && python -m app.users add …` (it asks for the password, so it needs the interactive shell).
- **Public demo** (`fly.demo.toml`), `FOOD_MAP_DEMO=true`, for the resume link. Live at https://yums-map-demo.fly.dev. Deploy with `fly deploy --config fly.demo.toml --remote-only --ha=false --depot=false`. Keep it to **one machine** (`--ha=false`): each machine has its own database, so a second one would split visitors' logins and data. `app/demo`:
  - On every start (machines sleep when idle, so often) and every 24 h, `demo.reset()` drops all tables and refills them: `sample_reels.json` (made-up places in Muse's format, including pop-ups and 3 reels for the review page) through the normal importer, accounts `demo` (password public, on purpose) and `sam` (the friend; random password), and a few visits for each.
  - `GET /api/demo` (public; 404 on the real app) returns the demo login; the login page shows "Try the demo" and the title bar a "Demo · made-up places · source code" line.
  - Uploads are 403; the demo accounts are exempt from login lockout (otherwise one visitor could lock everyone out). Everything else works, and is wiped at the next reset.
  - Its database lives in `/tmp` inside the machine: never point it at real data.

## Upload alerts

Muse uploads with nobody watching, so `app/alerts.py` posts to Discord (`FOOD_MAP_ALERT_WEBHOOK`) when something goes wrong. Unset = off (local, tests, demo).
- From `POST /api/import`: a Muse upload refused or failed (empty, over 5 MB, bad JSON, not UTF-8, or any exception during the import, which is now recorded as a failed import run and returns 500) → `upload_failed`, at most once an hour; a wrong bearer token → `wrong_token`, at most once per 6 h. Uploads by a logged-in person don't alert: they see the error.
- Quiet: no successful Muse upload in `FOOD_MAP_QUIET_DAYS` (default 7, since Muse only uploads on days with new saves) → `quiet`, once per quiet stretch (again after another full stretch). Silent before Muse's first upload. Checked on server start and every 12 h while up (`main._check_quiet_periodically`); the server sleeps when idle, so `.github/workflows/wake.yml` hits `/api/health` daily. Its URL is the repo secret `YUMS_MAP_URL`, kept out of the public repo.
- Sending runs on a thread and never fails the request. Discord rejects Python's default user agent, so `_post` sets one.
- Tests turn alerts on with a fake `_post` (`tests/test_alerts.py`); never post to a real webhook from tests.
- `python -m app.alerts test` posts a test message; `check` runs the quiet check now.

## Out of scope (for now)

Public sign-up, more than a couple of users, Google Places verification.
