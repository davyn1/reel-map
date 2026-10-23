# Bay Area Yums Map

A map of Bay Area restaurants saved from Instagram food reels, with a "been here" log for two friends. Saved reels are exported as JSON by Meta's Muse AI, checked and imported into SQLite, and shown on a dark, stripped-down map with a food-icon pin per restaurant. Built for my own use, on the phone, on the go.

**Live demo: [yums-map-demo.fly.dev](https://yums-map-demo.fly.dev)**. Click "Try the demo". It uses made-up places, and anything you change resets on its own.

<p>
  <img src="docs/screenshots/popup-desktop.png" alt="Map with a place's popup: address, food tag, Google Maps link, been-here, stars, visit date, notes, the friend's rating and the reels it was saved from" width="560">
  <img src="docs/screenshots/map-phone.png" alt="Phone view: stats, search, filters, Pick for me and the clustered map" width="190">
  <img src="docs/screenshots/review-phone.png" alt="Review page: reels the import couldn't place, with flags explaining what's missing" width="190">
</p>

## What it does

- **Map:** coral pins are places to try, teal ones are places I've been. Dashed pins are approximate (pop-ups, home cooks, or places Muse could only place in a city). Crowded areas group into count bubbles that split as you zoom. Search by spot, dish or poster, filter by city, pin type or food type (about a dozen broad ones like Korean, Mexican, American, Seafood, Sweets & bakery, worked out from the captions), and tap a pin, or a place in the list below the map, for the address, an "Open in Google Maps" link and the reels that mention it.
- **Pick for me:** can't decide? 🎲 picks a random place you haven't tried from whatever the search and filters show, flies to it and opens it. "Pick again" never repeats the last one.
- **Visit log and favorites:** mark a place "been here", then give it 1–5 stars, the date you went and a note ("get the spicy wings"). Star places you most want to try. The list can sort by favorites, top rated or most recently visited.
- **Two people, separate logs:** you and a friend each log in (no sign-up page; accounts are made from the command line). Each person's been-here, stars, notes and favorites are their own, the other person's show up in each place's popup, and "Both want to go" shows places you've both starred.
- **Add places yourself:** the ＋ button adds a place by hand: tap the map or use your location for the pin, optionally paste the reel or website. It warns if it's already on the map.
- **Review:** reels Muse couldn't place, or that cover several spots, wait here. Each shows what's missing from the export (flags like `no_venue` or `multi_spot`) and Muse's note. Fix one by dropping a pin on a small map or attaching it to an existing place, or reject it.

## How it's built

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, SQLite. One server serves both the API and the built map.
- **Frontend:** React 18 and TypeScript (Vite), with Leaflet for the map. The basemap is [OpenFreeMap](https://openfreemap.org) vector tiles drawn by MapLibre GL, restyled to a minimal dark palette: water, freeways and city names only. No API keys anywhere.
- **Import pipeline:** Muse's JSON is messy (nulls vs. empty strings, ALL-CAPS names, business names in addresses, swapped coordinates, multi-spot reels).
  - **Flags:** each reel gets flags for what's missing. Rows that can't be placed safely go to a review queue instead of the map.
  - **Dedup and merging:** duplicates are caught through normalized reel URLs. Places merge only on the same street address *and* a fuzzy name match, since food halls share addresses.
  - **Bad files:** a broken file stops the import with its line and column, and nothing is written.
- **Logins:**
  - **Passwords and sessions:** passwords are hashed with scrypt. Login sessions use HttpOnly cookies, and the database stores only a hash of each session token.
  - **Lockout:** an account is locked for 15 minutes after 5 wrong passwords.
  - **Uploads:** Muse can upload new exports with a bearer token.
- **Phone first:** it installs to the home screen (web app manifest and icons), keeps clear of the iPhone status bar, and is sized for tapping.
- **Map details:**
  - **Clustering:** crowded pins group into count bubbles.
  - **Overlaps:** pins with identical coordinates fan out so each one can be tapped.
  - **Popup fix:** buttons inside a popup no longer close it, a click-ordering bug between React and Leaflet.
- **Hosting:** one Docker image on Fly.io. The demo is the same image with `FOOD_MAP_DEMO=true`: a throwaway database rebuilt from sample data on every start and every 24 hours.
- **Tests:** 96 pytest tests cover the parser, flags, import rules, API, logins and the demo. The frontend is typechecked, and UI flows were checked with real clicks in headless Chrome.

## Requirements

- Python 3.12
- Node 20+

## Setup

```bash
# backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# frontend
cd ../frontend
npm install
```

## Logins

Make an account for each person (it asks for the password, which isn't shown as you type):

```bash
# backend/
python -m app.users add davy --name "Davy"
python -m app.users add alex --name "Alex"
python -m app.users list              # who has an account, how many devices are logged in
python -m app.users passwd davy       # change a password (logs that person out everywhere)
```

The first account you make takes over anything logged before logins existed.

## Import reels

Put Muse exports in `data/` as `reels.json`, or as several files named `reels*.json`. Then, from `backend/`:

```bash
python -m app.importer.check       # see what's missing in the export, by flag (writes nothing)
python -m app.importer.run         # import every data/reels*.json
```

Re-running the import only adds reels it hasn't seen (matched by post URL), so new exports can be dropped in next to old ones. If a file isn't valid JSON, the import stops, says which line and column, and writes nothing.

To start over, delete `backend/food_map.db` and import again.

### Uploading instead (how Muse sends exports)

The app also accepts an export over HTTP, so Muse can send its daily file directly once the app is online:

```bash
curl -X POST https://<your-app>/api/import \
     -H "Authorization: Bearer $FOOD_MAP_IMPORT_TOKEN" \
     -H "Content-Type: application/json" \
     --data-binary @reels.json
```

`FOOD_MAP_IMPORT_TOKEN` is a long random secret set on the server (and given only to Muse); without it, token uploads are off. Each upload is saved in `data/` before it's imported, reels already on the map are skipped, and the map shows when the last import happened and what it added.

## Run

Two terminals:

```bash
# backend/ : API on http://localhost:8000 (docs at /docs)
uvicorn app.main:app --reload

# frontend/ : app on http://localhost:5173
npm run dev
```

## Hosting (Fly.io)

Two apps from one `Dockerfile`, built remotely by Fly (no Docker needed locally):

- **Demo** (`fly.demo.toml`): live at [yums-map-demo.fly.dev](https://yums-map-demo.fly.dev). It runs on a single machine, so all visitors share one database and their logins work.
- **Real map** (`fly.toml`): data on a volume. Not deployed yet.

```bash
fly deploy --config fly.demo.toml --ha=false    # the demo (add --depot=false if the build fails with a certificate error)
fly deploy                                      # the real map
fly ssh console                                 # a shell on the server, then:
cd /app/backend && python -m app.users add davy --name Davy
```

## Tests

```bash
cd backend && pytest          # importer, flags and API
cd frontend && npm run typecheck
```

## To do

**Using it**
- [ ] Open it on a phone: reachable over home Wi-Fi and installable to the home screen
- [ ] Near me: sort the list by distance from where you are, with a "you are here" dot on the map
- [x] Clean up place-card wording: trim captions to the dish (they repeat the name and address and are cut off at 140 characters), and drop the "exact address" label (only say when a location is approximate)
- [x] Pick for me: one button that picks a random to-try place matching the current filters (e.g. Korean in Hayward) and flies to it
- [x] Add a place by hand in the app: name, optional link and address, pin from the map, your location or coordinates; warns about duplicates; shows "added by …"
- [ ] Live sync between the two of us: an open app picks up the other person's changes (new places, been-here, ratings) within seconds, without refreshing. Data is already shared once hosted; this is about seeing it live

**Data quality**
- [ ] Clear the review queue: 2 multi-spot reels (Butter & Crumble, Deli Board) need their other spots added, and 4 reels have no venue
- [ ] Pin sanity check: compare Muse's coordinates with OpenStreetMap's free geocoder and flag pins more than a few hundred metres from their address

**Getting new reels in**
- [ ] Import page: paste or drop a Muse export in the app and see the import summary there, without the command line
- [ ] "Copy prompt for Muse" button that asks for reels saved since the last import, in the export format
- [ ] "New" badge on places from the latest import
- [ ] Accept JSON copied from a chat (inside a code block, or wrapped as `{"reels": [...]}`), still refusing anything else with the error's line and column
- [ ] Muse handoff: have Muse push new saves somewhere the app picks up (a shared file, email or webhook). Depends on what Muse can do: run on a schedule, write outside the chat, tell which reels are new
- [ ] Watch a folder (e.g. a synced Drive folder) and import new `reels*.json` automatically

**Ideas**
- [ ] Back up the Muse exports too: keep them under `personal/` so a restore on a new machine has everything it needs (the log alone needs the places re-imported first)
- [x] Friend mode: a "me / friend" switch with separate been-here, ratings and favorites, plus a "both want to go" filter (`visits.user` already supports it)
- [ ] Food crawl planner: pick a few places, order them sensibly, and open one multi-stop Google Maps link
- [ ] Which posters to trust: each poster's average rating across the places you've tried
- [ ] Watch the reel in the app: Instagram's embed in the popup (test first; it can be unreliable)
- [ ] Year in food: a stats page with places tried by cuisine, average rating, cities explored, saved vs. visited
- [ ] "Closed" marking: hide permanently closed places without losing their history

**Someday** (bigger ideas, not planned yet)
- [ ] Trip maps beyond the Bay Area: named maps ("Bay Area", "Tokyo 2027") with a switcher, each built automatically around the restaurants saved in that area (or saved from the current map view), with per-map visits, favorites and Pick for me. Needs the Bay Area assumptions removed first: the `coords_outside_bay_area` flag, the review page's Bay Area check on new pins, the starting view and the title. Food tags may need per-region tuning (in Tokyo most places would just be "Japanese"). Pairs with Near me for "within 2 km of the hotel".

## Personal data

What can't be rebuilt from a Muse export lives in a backup file, `personal/my-log.json`: been-here, visit dates, ratings, notes, favorites, hand-picked tags and places added by hand. The app rewrites it after every change. Places are matched by reel URL, so it can be restored onto a fresh database:

```bash
# backend/ : after importing the Muse exports on a new machine
python -m app.backup restore
python -m app.backup export     # rewrite the log from the database by hand
```

None of it is in git: `personal/`, the Muse exports in `data/`, the SQLite database and `.env` are all gitignored. Copy `personal/` somewhere safe yourself.

## License

[MIT](LICENSE)

## More detail

[CLAUDE.md](CLAUDE.md) has the data model, import rules, flag definitions and API reference.
