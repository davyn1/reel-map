# Roadmap

## Using it

- [ ] Open it on a phone: reachable over home Wi-Fi and installable to the home screen
- [ ] Near me: sort the list by distance from where you are, with a "you are here" dot on the map
- [ ] Live sync between the two of us: an open app picks up the other person's changes (new places, been-here, ratings) within seconds, without refreshing. Data is already shared once hosted; this is about seeing it live

## Data quality

- [ ] Clear the review queue: 2 multi-spot reels (Butter & Crumble, Deli Board) need their other spots added, and 4 reels have no venue
- [ ] Pin sanity check: compare Muse's coordinates with OpenStreetMap's free geocoder and flag pins more than a few hundred metres from their address

## Getting new reels in

- [ ] Import page: paste or drop a Muse export in the app and see the import summary there, without the command line
- [ ] "Copy prompt for Muse" button that asks for reels saved since the last import, in the export format
- [ ] "New" badge on places from the latest import
- [ ] Accept JSON copied from a chat (inside a code block, or wrapped as `{"reels": [...]}`), still refusing anything else with the error's line and column
- [ ] Muse handoff: have Muse push new saves somewhere the app picks up (a shared file, email or webhook). Depends on what Muse can do: run on a schedule, write outside the chat, tell which reels are new
- [ ] Watch a folder (e.g. a synced Drive folder) and import new `reels*.json` automatically

## Ideas

- [ ] Back up the Muse exports too: keep them under `personal/` so a restore on a new machine has everything it needs (the log alone needs the places re-imported first)
- [ ] Food crawl planner: pick a few places, order them sensibly, and open one multi-stop Google Maps link
- [ ] Which posters to trust: each poster's average rating across the places you've tried
- [ ] Watch the reel in the app: Instagram's embed in the popup (test first; it can be unreliable)
- [ ] Year in food: a stats page with places tried by cuisine, average rating, cities explored, saved vs. visited
- [ ] "Closed" marking: hide permanently closed places without losing their history

## Someday

- [ ] Trip maps beyond the Bay Area: named maps ("Bay Area", "Tokyo 2027") with a switcher, each built automatically around the restaurants saved in that area (or saved from the current map view), with per-map visits, favorites and Pick for me. Needs the Bay Area assumptions removed first: the `coords_outside_bay_area` flag, the review page's Bay Area check on new pins, the starting view and the title. Food tags may need per-region tuning (in Tokyo most places would just be "Japanese"). Pairs with Near me for "within 2 km of the hotel".

## Done

- [x] Clean up place-card wording: trim captions to the dish, and only label a location when it's approximate
- [x] Pick for me: one button that picks a random to-try place matching the current filters and flies to it
- [x] Add a place by hand: name, optional link and address, pin from the map, your location or coordinates; warns about duplicates; shows "added by …"
- [x] Friend mode: separate been-here, ratings and favorites per person, plus a "Both want to go" filter
