# reel-map

A personal map of Bay Area restaurants I've saved from Instagram food reels, with a "been here" checklist.

Saved reels are exported by Meta's Muse AI as JSON, imported into SQLite, and shown on a dark, stripped-down map (land, water, freeways and city names) with a numbered pin per restaurant.

- **Map:** coral pins are places to try, teal ones are places I've been. Dashed pins are approximate (pop-ups, home cooks, or places Muse could only place in a city). Search by spot, dish or poster, filter by city or pin type, and tap a pin, or a place in the list below the map, for the address, an "Open in Google Maps" link, the reels that mention it, and a "been here" toggle.
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

## Privacy

`data/*.json` (your exports), the SQLite database and `.env` are gitignored. Only code is committed.

## More detail

[CLAUDE.md](CLAUDE.md) has the data model, import rules, flag definitions and API reference.
