# reel-map

A personal map of Bay Area restaurants I've saved from Instagram food reels, with a "been here" checklist.

Saved reels are exported by Meta's Muse AI as JSON, imported into SQLite, and shown on a dark, stripped-down map (land, water, freeways and city names) with a pin per restaurant showing a food icon (🌮 🍔 🍩 🦞…).

- **Map:** coral pins are places to try, teal ones are places I've been. Dashed pins are approximate (pop-ups, home cooks, or places Muse could only place in a city). Crowded areas group into count bubbles that split as you zoom. Search by spot, dish or poster, filter by city, pin type or food type (about a dozen broad ones like Korean, Mexican, American, Seafood, Sweets & bakery, worked out from the captions), and tap a pin, or a place in the list below the map, for the address, an "Open in Google Maps" link and the reels that mention it.
- **Pick for me:** can't decide? 🎲 picks a random place you haven't tried from whatever the search and filters show, flies to it and opens it. "Pick again" never repeats the last one.
- **Visit log and favorites:** mark a place "been here", then give it 1–5 stars, the date you went and a note ("get the spicy wings"). Star places you most want to try. The list can sort by favorites, top rated or most recently visited.
- **Two people, separate logs:** you and a friend each log in (no sign-up page; accounts are made from the command line). Each person's been-here, stars, notes and favorites are their own, the other person's show up in each place's popup, and "Both want to go" shows places you've both starred.
- **Review:** reels Muse couldn't place, or that cover several spots, wait here. Each shows what's missing from the export (flags like `no_venue` or `multi_spot`) and Muse's note. Fix one by dropping a pin on a small map or attaching it to an existing place, or reject it.

No API keys are needed. Pins use Muse's own coordinates, and the map tiles come from [OpenFreeMap](https://openfreemap.org).

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

## Run

Two terminals:

```bash
# backend/ : API on http://localhost:8000 (docs at /docs)
uvicorn app.main:app --reload

# frontend/ : app on http://localhost:5173
npm run dev
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

## Personal data in this repo

The repo is private, and one folder of personal data is committed on purpose: `personal/my-log.json`. It holds what can't be rebuilt from a Muse export: been-here, visit dates, ratings, notes, favorites and hand-picked tags. The app rewrites it after every change; commit it like any other file. Places are matched by reel URL, so it can be restored onto a fresh database:

```bash
# backend/ : after importing the Muse exports on a new machine
python -m app.backup restore
python -m app.backup export     # rewrite the log from the database by hand
```

Still gitignored: `data/*.json` (Muse exports), the SQLite database and `.env`.

**Rule: personal data goes only in `personal/`.** That keeps it removable in one step.

### Before making the repo public

Deleting `personal/` in a new commit isn't enough, because every earlier commit still contains it. Either:

- **Simplest:** create a new public repo from a copy of the current files without `personal/` (no history comes along), and keep this private repo as your backup; or
- **Keep the history, minus personal data:**
  ```bash
  pip install git-filter-repo
  git filter-repo --path personal --invert-paths   # rewrites every commit without personal/
  echo "personal/" >> .gitignore                   # then keep the log local only
  git remote add origin https://github.com/davyn1/reel-map.git   # filter-repo removes the remote
  git push --force origin main
  ```
  Anyone who already cloned the repo keeps the old history, so do this before sharing it.

## More detail

[CLAUDE.md](CLAUDE.md) has the data model, import rules, flag definitions and API reference.
