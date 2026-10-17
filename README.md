# reel-map

A personal map of Bay Area restaurants I've saved from Instagram food reels, with a "been here" checklist.

Saved reels are exported by Meta's Muse AI as JSON, imported into SQLite, and shown on a dark, stripped-down map (land, water, freeways and city names) with a pin per restaurant showing a food icon (🌮 🍔 🍩 🦞…).

- **Map:** coral pins are places to try, teal ones are places I've been. Dashed pins are approximate (pop-ups, home cooks, or places Muse could only place in a city). Crowded areas group into count bubbles that split as you zoom. Search by spot, dish or poster, filter by city, pin type or food type (about a dozen broad ones like Korean, Mexican, American, Seafood, Sweets & bakery, worked out from the captions), and tap a pin, or a place in the list below the map, for the address, an "Open in Google Maps" link and the reels that mention it.
- **Visit log and favorites:** mark a place "been here", then give it 1–5 stars, the date you went and a note ("get the spicy wings"). Star places you most want to try. The list can sort by favorites, top rated or most recently visited.
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
- [ ] Clean up place-card wording: trim captions to the dish (they repeat the name and address and are cut off at 140 characters), and drop the "exact address" label (only say when a location is approximate)

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

## Privacy

`data/*.json` (your exports), the SQLite database and `.env` are gitignored. Only code is committed.

## More detail

[CLAUDE.md](CLAUDE.md) has the data model, import rules, flag definitions and API reference.
