# Features

## Summary

A map of Bay Area restaurants built from saved Instagram food reels. Meta's Muse AI exports the saved reels as JSON. The app imports them into SQLite and shows them on a phone-friendly map with a shared "been here" log.

## Tech stack

- **Backend:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, SQLite, Uvicorn, RapidFuzz (name matching). Pins come from Muse's own coordinates, so the backend calls no geocoding API (`backend/requirements.txt`).
- **Frontend:** TypeScript 5.6, React 18, Vite 5, Leaflet 1.9 with react-leaflet and react-leaflet-cluster, MapLibre GL 4.7 (`frontend/package.json`).
- **Map tiles:** OpenFreeMap vector tiles, no API key. OpenStreetMap raster tiles are the fallback.
- **Hosting:** Fly.io: two apps built from one Docker image.
- **CI/CD:** GitHub Actions.
- **Alerts:** Discord webhook (optional).

## Features

| Feature | Files |
|---|---|
| Import Muse exports from the command line, with per-reel flags and a summary | `backend/app/importer/run.py`, `parse.py`, `flags.py`, `check.py` |
| Duplicate handling: reel URLs normalized to one form; places merge only on the same street address and a name score ≥ 80 | `backend/app/importer/parse.py`, `backend/app/importer/matching.py` |
| Upload endpoint for Muse (`POST /api/import`), with a history of import runs | `backend/app/routers/imports.py` |
| Map with clustered pins, food-type icons, and fanned-out pins that share coordinates | `frontend/src/pages/MapPage.tsx`, `frontend/src/mapUtils.ts`, `frontend/src/basemap.tsx` |
| Search and filters (city, pin status, food tag), list sorting, "Pick for me" | `frontend/src/pages/MapPage.tsx` |
| Food tags computed from keywords, with hand editing | `backend/app/tags.py`, `frontend/src/components/TagEditor.tsx` |
| Visit log: been here, 1–5 rating, visit date, notes, favorite; the other person's log shown alongside | `backend/app/routers/places.py`, `frontend/src/components/VisitLog.tsx` |
| Add a place by hand (tap the map, your location or coordinates), with duplicate warnings | `backend/app/routers/places.py`, `frontend/src/pages/AddPlacePage.tsx`, `frontend/src/components/PinPicker.tsx` |
| Remove a place from the map, with Undo; later imports don't bring it back | `backend/app/routers/places.py`, `frontend/src/pages/MapPage.tsx` |
| Refresh on return: switching back to the app re-fetches places, the stat chips, the last-import line and the review queue (at most once per 5 s), keeping filters, the map view, an open popup and a half-typed note | `frontend/src/useRefreshOnReturn.ts`, `frontend/src/pages/MapPage.tsx`, `frontend/src/App.tsx`, `frontend/src/pages/ReviewPage.tsx` |
| Review queue for reels that couldn't be placed: fix, add extra spots, or reject | `backend/app/routers/reels.py`, `frontend/src/pages/ReviewPage.tsx` |
| "Open in Google Maps" link per place | `backend/app/maps_link.py` |
| Logins, plus a passcode-only login when there's a single account | `backend/app/auth.py`, `backend/app/routers/auth.py`, `backend/app/users.py`, `frontend/src/pages/LoginPage.tsx` |
| JSON backup of hand-entered data, written after every change, with a restore command | `backend/app/backup.py` |
| Discord alerts when a Muse upload fails, uses a wrong token, or stops arriving | `backend/app/alerts.py`, `.github/workflows/wake.yml` |
| Public demo mode with made-up data that resets itself | `backend/app/demo/` |
| Installable to a phone's home screen | `frontend/public/manifest.webmanifest`, `frontend/index.html` |
| Schema changes applied to existing databases without losing data | `backend/app/db.py` |

## Testing

- **115 backend tests** (pytest), 112 test functions in 11 files under `backend/tests/`. Locally all 115 pass. In CI 113 pass and 2 skip: the two skipped tests read a real Muse export, which isn't in the repo.
- **What they cover:**
  - export parsing and reel flags
  - import rules and merging
  - the upload endpoint
  - the API
  - logins, lockout and passcode login
  - hand-added places
  - removing places
  - food tags and schema migration
  - backup and restore
  - demo reset
  - alerts (with a fake sender)
- **Frontend:** `npm run typecheck` (`tsc`). There are no frontend unit tests; UI changes are checked with scripted headless-Chrome runs against a throwaway demo server (not part of CI).
- **Isolation:** tests use temporary paths for the backup file and uploads (`backend/tests/conftest.py`), and CI points the database and data folders at a throwaway directory.
- **How they run:** `pytest` in `backend/` locally, and in CI on every push and pull request (`.github/workflows/ci.yml`).

## Infrastructure

- **Container:** `Dockerfile` has two stages. `node:20-slim` builds the frontend, then `python:3.12-slim` runs Uvicorn on port 8080 and serves both the API and the built frontend.
- **Hosting:** Fly.io, region `sjc`, one `shared-cpu-1x` machine with 256 MB per app. Machines stop when idle and start on the next request. Each machine is health-checked at `/api/health` every 30 s with a 5 s timeout.
  - Real app (`fly.toml`): SQLite database, uploads and backup on the `yums_data` volume at `/data`.
  - Demo app (`fly.demo.toml`): `FOOD_MAP_DEMO=true`, database in `/tmp`, no volume.
- **CI** (`.github/workflows/ci.yml`), on every push and pull request:
  - backend tests
  - frontend typecheck
  - Docker image build (not pushed)
  - pip, npm and Docker layers cached
- **Deploys:**
  - Demo: automatic. CI's `deploy-demo` job runs after all checks pass on a push to `main`.
  - Real app: manual. "Deploy the real map" (`.github/workflows/deploy-map.yml`) is started by hand, deploys only `main`, and only if CI passed for that commit.
  - Both use Fly deploy tokens, each scoped to one app.
- **Scheduled:** `.github/workflows/wake.yml` requests `/api/health` daily (16:23 UTC), so the sleeping server runs its "Muse has gone quiet" check.

## Reliability and security

**Passwords** (`backend/app/auth.py`, `backend/app/users.py`):
- scrypt (n=2^15, r=8, p=1) with a 16-byte random salt per user.
- Constant-time comparison.
- Minimum length 8.

**Sessions** (`backend/app/auth.py`, `backend/app/routers/auth.py`):
- A random 32-byte token in an HttpOnly, SameSite=Lax cookie, Secure by default.
- Only the token's SHA-256 is stored.
- Sessions expire after 60 days and are deleted server-side on logout. A password change ends all sessions.

**Lockout** (`backend/app/auth.py`):
- 5 wrong passwords for one username lock it for 15 minutes.
- Unknown usernames get the same error message as wrong passwords.

**Access control:**
- Every `/api/*` route needs a login, except health, demo info, login mode and login.
- Uploads accept a bearer token, compared in constant time, or a logged-in session.
- Uploads return 503 when no token is configured (`backend/app/routers/imports.py`).

**Input validation** (`backend/app/schemas.py`, `backend/app/routers/places.py`):
- Pydantic models enforce limits: names ≤ 120 characters, addresses ≤ 300, links ≤ 500 (http/https only), notes ≤ 2000, ratings 1–5.
- Food tags must come from the fixed list.
- New pins must fall inside the Bay Area box: lat 36.8–38.9, lng −123.6 to −121.2.

**Upload handling** (`backend/app/routers/imports.py`):
- Bodies over 5 MB are refused.
- Bad JSON is refused with its line and column, and the file is kept as `.invalid`.
- One import runs at a time; another gets 409.
- Any exception is recorded as a failed import run and returns 500.

**Data safety:**
- Imports never update or delete existing reels. The command-line import parses every file before writing anything (`backend/app/importer/run.py`).
- Removing a place only hides it.
- The JSON backup is written after every change (`backend/app/backup.py`).
- Fly keeps daily volume snapshots for 5 days.

**Alerts** (`backend/app/alerts.py`):
- Sent on a background thread with a 10 s timeout; a failed alert never fails the request.
- Cooldowns: 1 h for failed uploads, 6 h for wrong tokens, once per quiet stretch for "gone quiet" (7 days without an upload by default).

**Secrets:**
- The upload token, alert webhook and deploy tokens are Fly or GitHub secrets, never in the repo.
- `.env`, the database, Muse exports and `personal/` are gitignored (`.gitignore`).
- Without the secrets, CI deploys skip (the demo) or stop (the real map).

**Demo** (`backend/app/demo/__init__.py`):
- Rebuilt from sample data on every start and every 24 hours.
- Uploads are refused (403).
- The demo accounts are exempt from lockout, so one visitor can't lock others out.

## Numbers

| What | Value | Source |
|---|---|---|
| Backend tests | 115 (113 pass + 2 skip in CI) | `pytest`, CI run 42995107168 |
| Upload size limit | 5 MB | `backend/app/routers/imports.py` |
| Session length | 60 days | `backend/app/auth.py` |
| Lockout | 5 failures → 15 minutes | `backend/app/auth.py` |
| Minimum password length | 8 | `backend/app/users.py` |
| Merge threshold (name score) | 80 | `backend/app/importer/matching.py` |
| Duplicate check radius for hand-added places | 150 m | `backend/app/routers/places.py` |
| Demo reset interval | 24 h | `backend/app/demo/__init__.py` |
| Quiet check interval / quiet threshold | 12 h / 7 days | `backend/app/main.py`, `backend/app/alerts.py` |
| Alert HTTP timeout | 10 s | `backend/app/alerts.py` |
| Fly health check | every 30 s, 5 s timeout | `fly.toml`, `fly.demo.toml` |
| Refresh on return: minimum gap between refreshes | 5 s | `frontend/src/useRefreshOnReturn.ts` |

## Status

- **Deployed:** yes, on Fly.io. Demo: https://yums-map-demo.fly.dev. The real app is private, behind a login.
- **Collaborators:** one maintainer (GitHub `davyn1`). The real app is used by two people.
- **Last updated:** 2026-11-13
