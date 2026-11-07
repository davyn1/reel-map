# Roadmap

## Using it

- [ ] Install it on both phones: the real map is hosted now, so add it to the home screen and check the layout on a real device (iPhone status bar, tap sizes)
- [ ] Near me: sort the list by distance from where you are, with a "you are here" dot on the map
- [ ] Live sync between the two of us: an open app picks up the other person's changes (new places, been-here, ratings, new imports) within seconds, without refreshing. The data is already shared; this is about seeing it live

## Data quality

- [ ] Clear the review queue (12 reels): 2 multi-spot reels (Butter & Crumble, Deli Board) need their other spots added, 8 have no location (5 of those no venue either), and 2 came in with a confidence Muse shouldn't send (`name`, `address`)
- [ ] Pin sanity check: compare Muse's coordinates with OpenStreetMap's free geocoder and flag pins more than a few hundred metres from their address

## Getting new reels in

- [ ] Import page, as a fallback to Muse's automatic upload: paste or drop an export in the app (including JSON copied from a chat, in a code block or wrapped as `{"reels": [...]}`) and see the import summary there, still refusing anything else with the error's line and column
- [ ] "New" badge on places from the latest import

## Keeping it running

- [ ] Off-server backups: a nightly copy of the database and Muse's uploads somewhere outside Fly, plus a "download my data" button. Right now Fly's daily volume snapshots (kept 5 days) are the only backup
- [ ] Muse upload alerts: notice when an end-of-day upload fails or stops arriving (the map's "Last import" line turns red on a failure, but nobody may look)

## Ideas

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
- [x] Logins: username and password per person (no sign-up page), session cookies, lockout after 5 wrong passwords
- [x] Upload endpoint: `POST /api/import` takes a Muse export with a secret token, and the map shows when the last import happened and what it added
- [x] Ready to host: one server for the API and the map, settings from environment variables, a Dockerfile and Fly.io configs
- [x] Public demo at [yums-map-demo.fly.dev](https://yums-map-demo.fly.dev): made-up places, a "Try the demo" button, resets on its own
- [x] Repo made public: personal data kept out of git, README with the demo and screenshots, MIT license
- [x] Food type tags (about a dozen broad ones) with hand editing, food-icon pins, clustering, visit log with stars, dates and notes, and favorites
- [x] Stat chips trimmed to the ones you can tap, colored like the pins they filter
- [x] Muse handoff: Muse sends its end-of-day export straight to the hosted app's upload endpoint, which imports it automatically (no Drive folder or PC needed)
- [x] Real map hosted on Fly.io, with one shared account and a passcode-only login
- [x] Remove from map: take a place off the map (e.g. after unsaving its reel), with Undo; later imports don't bring it back and its log is kept
