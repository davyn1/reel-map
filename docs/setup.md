# Setup and operations

Everything needed to run, fill, deploy and back up the map. For the data model, import rules and API, see [CLAUDE.md](../CLAUDE.md).

## Requirements

- Python 3.12
- Node 20+

## Install

```bash
# backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# frontend
cd ../frontend
npm install
```

## Accounts

There's no sign-up page. Make an account for each person from `backend/` (it asks for the password, which isn't shown as you type):

```bash
python -m app.users add davy --name "Davy"
python -m app.users add alex --name "Alex"
python -m app.users list              # who has an account, how many devices are logged in
python -m app.users passwd davy       # change a password (logs that person out everywhere)
```

The first account you make takes over anything logged before logins existed.

With exactly one account (say, one shared by two friends), the login screen asks only for a **passcode**: that account's password. Add a second account and the username box comes back.

## Importing reels

Put Muse exports in `data/` as `reels.json`, or as several files named `reels*.json`. Then, from `backend/`:

```bash
python -m app.importer.check       # see what's missing in the export, by flag (writes nothing)
python -m app.importer.run         # import every data/reels*.json
```

Re-running the import only adds reels it hasn't seen (matched by post URL), so new exports can be dropped in next to old ones. If a file isn't valid JSON, the import stops, says which line and column, and writes nothing.

To start over, delete `backend/food_map.db` and import again.

### Upload endpoint

The app also accepts an export over HTTP, so an automated sender can post new exports once the app is online. Whether Muse can do this on its own is still open (see [ROADMAP.md](../ROADMAP.md)); for now it works with any client holding the token:

```bash
curl -X POST https://<your-app>/api/import \
     -H "Authorization: Bearer $FOOD_MAP_IMPORT_TOKEN" \
     -H "Content-Type: application/json" \
     --data-binary @reels.json
```

`FOOD_MAP_IMPORT_TOKEN` is a long random secret set on the server; without it, token uploads are off. Each upload is saved in `data/` before it's imported, reels already on the map are skipped, and the map shows when the last import happened and what it added.

### Upload alerts (Discord)

With `FOOD_MAP_ALERT_WEBHOOK` set to a Discord webhook URL (a server secret), the app posts to that channel when:

- a Muse upload is refused or fails to import (bad JSON, empty, too big, an error on the server),
- an upload comes with the wrong token,
- Muse hasn't uploaded for `FOOD_MAP_QUIET_DAYS` days (default 7; Muse only uploads on days something new was saved).

Each kind posts at most once per cooldown, so a repeating problem doesn't spam the channel. Test the webhook from a shell on the server with `python -m app.alerts test`.

The server sleeps when idle, so the quiet check needs something to wake it: `.github/workflows/wake.yml` calls it once a day. Set the map's address as the repository secret `YUMS_MAP_URL` (it's kept out of the public files). Without that secret the job does nothing.

## Running locally

Two terminals, from the repo root:

```bash
# API on http://localhost:8000 (docs at /docs)
cd backend
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uvicorn app.main:app --reload

# app on http://localhost:5173 (second terminal)
cd frontend
npm run dev
```

## Hosting (Fly.io)

Two apps from one `Dockerfile`, built remotely by Fly (no Docker needed locally):

- **Demo** (`fly.demo.toml`): live at [yums-map-demo.fly.dev](https://yums-map-demo.fly.dev). Runs with `FOOD_MAP_DEMO=true` on a single machine, so all visitors share one database and their logins work. The database is rebuilt from sample data on every start and every 24 hours.
- **Real map** (`fly.toml`): deployed, login only, with its data on a 1 GB volume that Fly snapshots daily (kept 5 days).

**Deploys happen from GitHub Actions:**
- The demo deploys itself after CI passes on every push to `main` (the `deploy-demo` job in `.github/workflows/ci.yml`).
- The real map deploys only when you ask: Actions tab → **Deploy the real map** → Run workflow (`.github/workflows/deploy-map.yml`). It only deploys `main`, and only a commit whose CI run passed.

Each uses a Fly deploy token limited to its own app, stored as a repository secret. Create them once, piping each straight into GitHub so the token never shows on screen:

```bash
fly tokens create deploy -a yums-map-demo | gh secret set FLY_DEMO_DEPLOY_TOKEN -R davyn1/reel-map
fly tokens create deploy -a yums-map | gh secret set FLY_REAL_DEPLOY_TOKEN -R davyn1/reel-map
```

Deploying by hand still works:

```bash
fly deploy --config fly.demo.toml --ha=false    # the demo (add --depot=false if the build fails with a certificate error)
fly deploy                                      # the real map
fly ssh console                                 # a shell on the server, then:
cd /app/backend && python -m app.users add davy --name Davy
```

## Personal data and backups

What can't be rebuilt from a Muse export lives in `personal/my-log.json`: been-here, visit dates, ratings, notes, favorites, hand-picked tags and places added by hand. The app rewrites it after every change. Places are matched by reel URL, so it can be restored onto a fresh database:

```bash
# backend/ : after importing the Muse exports on a new machine
python -m app.backup restore
python -m app.backup export     # rewrite the log from the database by hand
```

None of it is in git: `personal/`, the Muse exports in `data/`, the SQLite database and `.env` are all gitignored. Copy `personal/` somewhere safe yourself.

## Tests

```bash
cd backend && pytest          # importer, flags and API
cd frontend && npm run typecheck
```
