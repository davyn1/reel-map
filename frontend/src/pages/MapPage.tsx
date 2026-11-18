import { useEffect, useMemo, useRef, useState } from "react";
import { AttributionControl, MapContainer, Marker, useMap, useMapEvents } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import L from "leaflet";
import type { LatLngBoundsExpression, Marker as LeafletMarker, MarkerClusterGroup as LeafletClusterGroup } from "leaflet";
import { api, type Place, type Stats, type VisitUpdate } from "../api";
import { MinimalBasemap } from "../basemap";
import BottomSheet, { snapHeights, type Snap } from "../components/BottomSheet";
import { CheckIcon, ChevronLeftIcon, DiceIcon, DirectionsIcon, FilterIcon, PlusIcon, SearchIcon, StarIcon } from "../components/Icons";
import { TagEditor } from "../components/TagEditor";
import { BeenButton, FavoriteButton, FriendLines, Rating, VisitDetails } from "../components/VisitLog";
import { dishLine } from "../captions";
import { clusterIcon, pinClasses, pinIcon, placeIcon, spreadOverlaps, type Pin } from "../mapUtils";
import { useOnDataChanged } from "../liveSync";

const BAY_AREA_CENTER: [number, number] = [37.65, -122.2];
// Zoomed in this far, every pin shows on its own.
const NO_CLUSTER_ZOOM = 14;
// The food-type row floats this tall over the map's top edge.
const CHIP_ROW = 52;

type Status = "all" | "todo" | "visited" | "favorites" | "both";
type Accuracy = "any" | "exact" | "approx";
type SortKey = "number" | "rating" | "recent" | "favorites";
type Mode = "list" | "place" | "filters";

const SORTS: [SortKey, string][] = [
  ["number", "Order saved"],
  ["favorites", "Want to go first"],
  ["rating", "Top rated"],
  ["recent", "Recently visited"],
];

function matchesStatus(place: Place, status: Status): boolean {
  switch (status) {
    case "todo": return !place.visited;
    case "visited": return place.visited;
    case "favorites": return place.favorite;
    case "both": return place.favorite && place.others.some((o) => o.favorite);
    default: return true;
  }
}

function matchesAccuracy(place: Place, accuracy: Accuracy): boolean {
  if (accuracy === "exact") return !place.is_approximate;
  if (accuracy === "approx") return place.is_approximate;
  return true;
}

function matchesQuery(place: Place, q: string): boolean {
  if (!q) return true;
  const haystack = [
    place.name,
    place.city,
    place.address,
    place.notes,
    ...place.tags,
    ...place.reels.flatMap((r) => [r.dish, r.posted_by]),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return q.split(/\s+/).every((word) => haystack.includes(word));
}

type Numbered = { place: Place; number: number };

function sortBy(items: Numbered[], key: SortKey): Numbered[] {
  const out = [...items];
  if (key === "favorites") out.sort((a, b) => Number(b.place.favorite) - Number(a.place.favorite) || a.number - b.number);
  if (key === "rating") out.sort((a, b) => (b.place.rating ?? 0) - (a.place.rating ?? 0) || a.number - b.number);
  if (key === "recent")
    out.sort((a, b) => (b.place.visited_date ?? "").localeCompare(a.place.visited_date ?? "") || a.number - b.number);
  return out;
}

/** The fresh list, reusing the old object for every place that didn't change. Returns `prev` itself
 * when nothing changed at all, so a refresh with no news doesn't re-render the map or the list. */
function mergePlaces(prev: Place[] | null, fresh: Place[]): Place[] {
  if (!prev) return fresh;
  const old = new Map(prev.map((p) => [p.id, p]));
  let changed = prev.length !== fresh.length;
  const merged = fresh.map((p, i) => {
    const before = old.get(p.id);
    if (before && JSON.stringify(before) === JSON.stringify(p)) {
      if (prev[i] !== before) changed = true;
      return before;
    }
    changed = true;
    return p;
  });
  return changed ? merged : prev;
}

// Leaflet measures its container once. If the map mounts hidden or zero-sized (a background
// tab, a collapsed pane), every pin projects to one point. Re-measure on resize, and only fit
// the view once the container has a real size. Refits whenever `fitKey` changes (filters),
// keeping pins out from under the top bar and the sheet.
function FitToPins({ pins, fitKey, top, bottom }: { pins: Pin[]; fitKey: string; top: number; bottom: number }) {
  const map = useMap();
  const [fitted, setFitted] = useState<string | null>(null);
  const [size, setSize] = useState(0);

  useEffect(() => {
    const observer = new ResizeObserver(() => {
      map.invalidateSize();
      setSize(map.getSize().x * map.getSize().y);
    });
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);

  useEffect(() => {
    if (fitted === fitKey || pins.length === 0 || size === 0) return;
    map.fitBounds(pins.map((p) => p.position) as LatLngBoundsExpression, {
      paddingTopLeft: [32, top + 16],
      paddingBottomRight: [32, bottom + 16],
      maxZoom: 14,
    });
    setFitted(fitKey);
  }, [map, pins, fitted, fitKey, size, top, bottom]);
  return null;
}

/** Flies to a chosen place, centering it in the strip of map left between the top bar and the
 * sheet, and opens its cluster if it's still inside one. */
function FlyToSelected({
  target,
  markers,
  cluster,
}: {
  target: { pin: Pin; nonce: number; top: number; bottom: number } | null;
  markers: Map<number, LeafletMarker>;
  cluster: React.RefObject<LeafletClusterGroup>;
}) {
  const map = useMap();
  useEffect(() => {
    if (!target) return;
    const zoom = Math.max(map.getZoom(), NO_CLUSTER_ZOOM);
    const shift = (target.bottom - target.top) / 2;
    const center = map.unproject(map.project(target.pin.position, zoom).add(L.point(0, shift)), zoom);
    map.flyTo(center, zoom, { duration: 0.5 });
    const marker = markers.get(target.pin.place.id);
    map.once("moveend", () => {
      if (marker && cluster.current) cluster.current.zoomToShowLayer(marker, () => undefined);
    });
  }, [map, target, markers, cluster]);
  return null;
}

/** A tap on the bare map closes the place view. */
function MapTap({ onTap }: { onTap: () => void }) {
  useMapEvents({ click: onTap });
  return null;
}

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: [T, string, number?][];
  onChange: (v: T) => void;
}) {
  return (
    <fieldset className="filter-group">
      <legend>{label}</legend>
      <div className="chip-row wrap">
        {options.map(([v, text, count]) => (
          <button key={v} type="button" className={`chip${value === v ? " on" : ""}`} aria-pressed={value === v} onClick={() => onChange(v)}>
            {text}
            {count !== undefined && <span className="chip-count">{count}</span>}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function PlaceView({
  place,
  allTags,
  picked,
  onPickAgain,
  onUpdate,
  onTags,
  onRemove,
}: {
  place: Place;
  allTags: string[];
  picked: { fallback: boolean } | null;
  onPickAgain: () => void;
  onUpdate: (u: VisitUpdate) => Promise<void>;
  onTags: (tags: string[] | null) => Promise<void>;
  onRemove: () => void;
}) {
  const caption = dishLine(place.reels[0]?.dish ?? null, { name: place.name, city: place.city });
  const meta = [place.city, place.tags.join(", ")].filter(Boolean).join(" · ");
  return (
    <div className="place-view">
      {picked && (
        <p className="picked" role="status">
          <DiceIcon size={16} />
          <span>
            Picked for you{picked.fallback ? " (you've been to everything shown)" : ""}
          </span>
          <button type="button" className="link-btn" onClick={onPickAgain}>
            Pick again
          </button>
        </p>
      )}
      <div className="place-heading">
        <h2 className="place-name">{place.name}</h2>
        {meta && <p className="place-meta">{meta}</p>}
        {caption && <p className="place-dish">{caption}</p>}
      </div>

      <div className="place-actions">
        <BeenButton place={place} onUpdate={onUpdate} />
        <a className="btn" href={place.google_maps_url} target="_blank" rel="noreferrer">
          <DirectionsIcon size={18} />
          Directions
        </a>
      </div>
      <VisitDetails place={place} onUpdate={onUpdate} />
      <FriendLines others={place.others} />

      <dl className="place-facts">
        <dt>Food type</dt>
        <dd>
          <TagEditor place={place} allTags={allTags} onSave={onTags} />
        </dd>
        <dt>{place.reels.some((r) => r.added_by) ? "Added" : "Saved from"}</dt>
        <dd className="reel-links">
          {place.reels.map((r) => {
            const isLink = /^https?:\/\//i.test(r.post_url); // hand-added places without a link use "manual:<id>"
            const label = r.posted_by ? `@${r.posted_by}` : /instagram\.com/i.test(r.post_url) ? "Reel" : "Link";
            return (
              <span key={r.id}>
                {isLink && (
                  <a href={r.post_url} target="_blank" rel="noreferrer">
                    {label}
                  </a>
                )}
                {r.added_by && (
                  <span className="muted">
                    {isLink ? " · " : ""}by {r.added_by}
                  </span>
                )}
              </span>
            );
          })}
        </dd>
        {(place.address || place.is_approximate) && (
          <>
            <dt>Where</dt>
            <dd>
              {place.address && <span>{place.address}</span>}
              {place.is_approximate && (
                <span className="muted approx-note">Approximate pin: a pop-up, home cook or city-level spot.</span>
              )}
            </dd>
          </>
        )}
      </dl>

      <button type="button" className="link-btn danger remove-btn" onClick={onRemove}>
        Remove from map
      </button>
    </div>
  );
}

export default function MapPage({
  stats,
  onChanged,
  focusId = null,
  onFocused,
  account,
  demo,
}: {
  stats: Stats | null;
  onChanged: () => void;
  focusId?: number | null; // fly to this place once the map has loaded
  onFocused?: () => void;
  account: React.ReactNode; // the avatar button and its menu, from App
  demo: boolean;
}) {
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [city, setCity] = useState("");
  const [tag, setTag] = useState("");
  const [status, setStatus] = useState<Status>("all");
  const [accuracy, setAccuracy] = useState<Accuracy>("any");
  const [sort, setSort] = useState<SortKey>("number");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("list");
  const [snap, setSnap] = useState<Snap>("peek");
  const [sheetHeight, setSheetHeight] = useState(84);
  const [topBar, setTopBar] = useState(64);
  const [flyTarget, setFlyTarget] = useState<{ pin: Pin; nonce: number; top: number; bottom: number } | null>(null);
  const markers = useRef(new Map<number, LeafletMarker>()).current;
  const [pick, setPick] = useState<{ id: number; fallback: boolean } | null>(null);
  const [nothingToPick, setNothingToPick] = useState(false);
  const [removed, setRemoved] = useState<Place | null>(null); // last place taken off the map, for Undo
  // Last place unmarked as been here, with what that cleared, for Undo.
  const [unvisited, setUnvisited] = useState<{ id: number; name: string; visited_date: string | null; rating: number | null } | null>(null);
  const lastPick = useRef<number | null>(null);
  const cluster = useRef<LeafletClusterGroup>(null);
  const header = useRef<HTMLElement>(null);

  useEffect(() => {
    api.places().then(setPlaces).catch((e) => setError(String(e)));
    api.tags().then(setAllTags).catch(() => setAllTags([]));
  }, []);

  useEffect(() => {
    const el = header.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setTopBar(el.getBoundingClientRect().height));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Counts changes made on this screen, so a refresh that was already on its way can't undo one.
  const edits = useRef(0);

  // Live sync: shared data changed (the other phone, a Muse upload, or a change made here). Filters,
  // the map view, the open place and a half-typed note stay as they are; only changed places are
  // swapped in.
  function refresh() {
    const before = edits.current;
    api
      .places()
      .then((fresh) => {
        if (edits.current !== before) {
          // A change made here landed meanwhile, so this list may be older than what's shown. Try
          // again shortly instead of showing it: the version poller has already moved past this change.
          window.setTimeout(refresh, 1000);
          return;
        }
        setPlaces((prev) => mergePlaces(prev, fresh));
        setError(null);
      })
      .catch(() => undefined); // offline or asleep: keep showing what's there
  }
  useOnDataChanged(refresh);

  // Import order, kept as the default list order and as the tiebreak for other sorts. Not shown.
  const numbered = useMemo(() => (places ?? []).map((place, i) => ({ place, number: i + 1 })), [places]);
  const cities = useMemo(() => countBy(places ?? [], (p) => (p.city ? [p.city] : [])), [places]);
  const tags = useMemo(
    () => countBy(places ?? [], (p) => p.tags).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])),
    [places],
  );
  const q = query.trim().toLowerCase();
  const shown = useMemo(
    () =>
      numbered.filter(
        ({ place }) =>
          (!city || place.city === city) &&
          (!tag || place.tags.includes(tag)) &&
          matchesStatus(place, status) &&
          matchesAccuracy(place, accuracy) &&
          matchesQuery(place, q),
      ),
    [numbered, city, tag, status, accuracy, q],
  );
  // Each marker keeps the same position array while its place hasn't moved. react-leaflet compares
  // positions by reference, and a "moved" marker is taken out of its cluster and put back. Any change
  // to the places list (a refresh, a been-here tick) would otherwise do that to every marker.
  const positions = useRef(new Map<number, Pin["position"]>()).current;
  const pins = useMemo(
    () =>
      spreadOverlaps(shown).map((pin) => {
        const prev = positions.get(pin.place.id);
        if (prev && prev[0] === pin.position[0] && prev[1] === pin.position[1]) return { ...pin, position: prev };
        positions.set(pin.place.id, pin.position);
        return pin;
      }),
    [shown, positions],
  );
  const listed = useMemo(() => sortBy(shown, sort), [shown, sort]);
  const selected = places?.find((p) => p.id === selectedId) ?? null;
  const filterCount = Number(status !== "all") + Number(accuracy !== "any") + Number(city !== "") + Number(sort !== "number");
  const narrowed = shown.length !== (places?.length ?? 0);

  // A place that vanished (removed here or on the other phone) closes its view.
  useEffect(() => {
    if (mode === "place" && places && !selected) {
      setMode("list");
      setSelectedId(null);
    }
  }, [mode, places, selected]);

  function replace(updated: Place) {
    setPlaces((prev) => prev?.map((p) => (p.id === updated.id ? updated : p)) ?? null);
  }

  async function update(placeId: number, change: VisitUpdate) {
    edits.current++;
    // Unmarking "been here" clears the date and rating on the server; keep them for Undo.
    const before = places?.find((p) => p.id === placeId);
    try {
      replace(await api.updateVisit(placeId, change));
      if (change.visited === false && before?.visited) {
        setUnvisited({ id: before.id, name: before.name, visited_date: before.visited_date, rating: before.rating });
      } else if (change.visited === true) {
        setUnvisited((u) => (u?.id === placeId ? null : u));
      }
      onChanged();
    } catch (e) {
      setError(String(e));
    }
  }

  async function setTags(placeId: number, tags: string[] | null) {
    edits.current++;
    try {
      replace(await api.setTags(placeId, tags));
    } catch (e) {
      setError(String(e));
    }
  }

  /** Take a place off the map, e.g. after unsaving its reel. Hidden, not deleted: Undo brings it back. */
  async function remove(place: Place) {
    const ok = window.confirm(
      `Remove "${place.name}" from the map?

Later Muse imports won't add it back. Its log and tags are kept, and you can undo right after.`,
    );
    if (!ok) return;
    edits.current++;
    try {
      await api.setRemoved(place.id, true);
      setPlaces((prev) => prev?.filter((p) => p.id !== place.id) ?? null);
      if (selectedId === place.id) {
        setSelectedId(null);
        setMode("list");
      }
      setRemoved(place);
      onChanged();
    } catch (e) {
      setError(String(e));
    }
  }

  async function undoRemove() {
    if (!removed) return;
    edits.current++;
    try {
      const back = await api.setRemoved(removed.id, false);
      setPlaces((prev) => (prev ? [...prev, back].sort((a, b) => a.id - b.id) : prev));
      setRemoved(null);
      onChanged();
    } catch (e) {
      setError(String(e));
    }
  }

  /** Open a place: the sheet shows it, and the map flies to it above the sheet. */
  function focus(placeId: number, picked: { fallback: boolean } | null = null) {
    setSelectedId(placeId);
    setMode("place");
    const nextSnap: Snap = snap === "full" ? "half" : snap === "peek" ? "half" : snap;
    setSnap(nextSnap);
    setPick(picked ? { id: placeId, ...picked } : null);
    const pin = pins.find((p) => p.place.id === placeId);
    if (pin) {
      const bottom = snapHeights(window.innerHeight, topBar)[nextSnap];
      setFlyTarget({ pin, nonce: Date.now(), top: topBar + CHIP_ROW, bottom });
    }
  }

  function backToList() {
    setMode("list");
    setSelectedId(null);
    setPick(null);
  }

  function clearFilters() {
    setQuery("");
    setCity("");
    setTag("");
    setStatus("all");
    setAccuracy("any");
    setSort("number");
  }

  // Fly to a place named in the URL (#/place/12) once places and pins are ready.
  useEffect(() => {
    if (focusId === null || !places) return;
    if (pins.some((p) => p.place.id === focusId)) {
      focus(focusId);
    } else {
      // filtered out (or gone): clear filters so it can be shown
      clearFilters();
      if (!places.some((p) => p.id === focusId)) onFocused?.();
      return;
    }
    onFocused?.();
  }, [focusId, places, pins]); // eslint-disable-line react-hooks/exhaustive-deps

  // Esc closes the place view or the filters.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && mode !== "list") backToList();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode]);

  /** Random place from what's shown (search + filters), preferring ones you haven't been to;
   * never the same place twice in a row. */
  function pickForMe() {
    const toTry = shown.filter(({ place }) => !place.visited);
    const fallback = toTry.length === 0;
    const pool = (fallback ? shown : toTry).filter(({ place }) => place.id !== lastPick.current || shown.length === 1);
    if (pool.length === 0) {
      setNothingToPick(true);
      return;
    }
    const { place } = pool[Math.floor(Math.random() * pool.length)];
    lastPick.current = place.id;
    setNothingToPick(false);
    focus(place.id, { fallback });
  }

  const countLabel = places === null ? "Loading…" : narrowed ? `${shown.length} of ${places.length} places` : `${places.length} places`;

  let sheetHeader: React.ReactNode;
  let sheetBody: React.ReactNode;
  if (mode === "place" && selected) {
    sheetHeader = (
      <div className="sheet-bar">
        <button type="button" className="back-btn" onClick={backToList}>
          <ChevronLeftIcon size={20} />
          Places
        </button>
        <FavoriteButton place={selected} onUpdate={(u) => update(selected.id, u)} />
      </div>
    );
    sheetBody = (
      <PlaceView
        key={selected.id}
        place={selected}
        allTags={allTags}
        picked={pick && pick.id === selected.id ? { fallback: pick.fallback } : null}
        onPickAgain={pickForMe}
        onUpdate={(u) => update(selected.id, u)}
        onTags={(t) => setTags(selected.id, t)}
        onRemove={() => remove(selected)}
      />
    );
  } else if (mode === "filters") {
    sheetHeader = (
      <div className="sheet-bar">
        <h2 className="sheet-title">Filters</h2>
        <button type="button" className="link-btn" onClick={() => setMode("list")}>
          Done
        </button>
      </div>
    );
    sheetBody = (
      <div className="filters-view">
        <Segmented<Status>
          label="Show"
          value={status}
          onChange={setStatus}
          options={[
            ["all", "Everything"],
            ["todo", "To try"],
            ["visited", "Been here", stats?.visited],
            ["favorites", "Want to go", stats?.favorites],
            ["both", "Both want to go"],
          ]}
        />
        <Segmented<Accuracy>
          label="Pins"
          value={accuracy}
          onChange={setAccuracy}
          options={[
            ["any", "Any"],
            ["exact", "Exact address"],
            ["approx", "Approximate"],
          ]}
        />
        <label className="filter-group">
          <span className="legend-like">City</span>
          <select value={city} onChange={(e) => setCity(e.target.value)}>
            <option value="">All cities</option>
            {cities.map(([name, n]) => (
              <option key={name} value={name}>
                {name} ({n})
              </option>
            ))}
          </select>
        </label>
        <label className="filter-group">
          <span className="legend-like">Sort the list</span>
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            {SORTS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <div className="filters-actions">
          <button type="button" className="link-btn" onClick={clearFilters} disabled={filterCount === 0 && !q && !tag}>
            Clear all
          </button>
          <button
            type="button"
            className="primary"
            onClick={() => {
              setMode("list");
              setSnap("half");
            }}
          >
            Show {shown.length} {shown.length === 1 ? "place" : "places"}
          </button>
        </div>
      </div>
    );
  } else {
    sheetHeader = (
      <div className="sheet-bar">
        <div className="sheet-count">
          <h2 className="sheet-title">{countLabel}</h2>
          {narrowed && (
            <button type="button" className="link-btn" onClick={clearFilters}>
              Clear filters
            </button>
          )}
        </div>
        <button type="button" className="pick-btn" onClick={pickForMe} title="A random place from what's shown, preferring ones you haven't tried">
          <DiceIcon size={18} />
          Pick for me
        </button>
      </div>
    );
    sheetBody = (
      <>
        {demo && <p className="demo-note">Demo with made-up places. Changes reset later.</p>}
        {places && shown.length === 0 && (
          <div className="empty">
            <p>No places match.</p>
            <button type="button" onClick={clearFilters}>
              Clear search and filters
            </button>
          </div>
        )}
        <ul className="place-list">
          {listed.map(({ place }) => {
            const caption = dishLine(place.reels[0]?.dish ?? null, { name: place.name, city: place.city });
            const meta = [place.city, place.tags[0], place.is_approximate ? "approximate pin" : null].filter(Boolean).join(" · ");
            return (
              <li key={place.id} className={`place-row${place.id === selectedId ? " selected" : ""}`}>
                <button type="button" className="row-main" onClick={() => focus(place.id)}>
                  <span className={`place-icon ${pinClasses(place)}`} aria-hidden="true">
                    {placeIcon(place)}
                  </span>
                  <span className="row-text">
                    <span className="row-name">
                      {place.name}
                      {place.favorite && <StarIcon size={14} filled className="row-fav" />}
                    </span>
                    {caption && <span className="row-dish">{caption}</span>}
                    <span className="row-meta">
                      {meta}
                      {place.visited && place.rating ? (
                        <>
                          {meta ? " · " : ""}
                          <Rating value={place.rating} />
                        </>
                      ) : null}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  className={`been-toggle${place.visited ? " on" : ""}`}
                  aria-pressed={place.visited}
                  aria-label={place.visited ? `Been to ${place.name}` : `Mark ${place.name} as been here`}
                  title={place.visited ? "Been here" : "Mark been here"}
                  onClick={() => update(place.id, { visited: !place.visited })}
                >
                  <span className="tick">
                    <CheckIcon size={18} />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </>
    );
  }

  const toastBottom = sheetHeight + 12;

  return (
    <div className="map-screen" style={{ "--sheet-h": `${sheetHeight}px` } as React.CSSProperties}>
      <header className="map-bar" ref={header}>
        <div className="search">
          <SearchIcon size={18} />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search places or dishes"
            aria-label="Search places"
          />
        </div>
        <button
          type="button"
          className={`icon-btn filter-btn${filterCount ? " on" : ""}`}
          aria-label={filterCount ? `Filters (${filterCount} on)` : "Filters"}
          aria-expanded={mode === "filters"}
          onClick={() => {
            if (mode === "filters") setMode("list");
            else {
              setMode("filters");
              setSnap("half");
            }
          }}
        >
          <FilterIcon size={20} />
          {filterCount > 0 && <span className="badge">{filterCount}</span>}
        </button>
        {account}
      </header>

      <div className="food-row" style={{ top: topBar }} role="group" aria-label="Food type">
        <button type="button" className={`chip${tag === "" ? " on" : ""}`} aria-pressed={tag === ""} onClick={() => setTag("")}>
          All food
        </button>
        {tags.map(([name, n]) => (
          <button
            key={name}
            type="button"
            className={`chip${tag === name ? " on" : ""}`}
            aria-pressed={tag === name}
            onClick={() => setTag(tag === name ? "" : name)}
          >
            {name}
            <span className="chip-count">{n}</span>
          </button>
        ))}
      </div>

      <div className="map-fill">
        {/* maxZoom is required by the cluster plugin; the vector basemap doesn't set one like tile layers do */}
        <MapContainer center={BAY_AREA_CENTER} zoom={10} minZoom={7} maxZoom={18} zoomControl={false} attributionControl={false}>
          {/* Bottom left, riding just above the sheet; the add button owns the bottom right. */}
          <AttributionControl position="bottomleft" />
          <MinimalBasemap />
          <FitToPins pins={pins} fitKey={`${city}|${tag}|${status}|${accuracy}`} top={topBar + CHIP_ROW} bottom={sheetHeight} />
          <FlyToSelected target={flyTarget} markers={markers} cluster={cluster} />
          <MapTap
            onTap={() => {
              if (mode === "place") {
                backToList();
                setSnap("peek");
              }
            }}
          />
          <MarkerClusterGroup
            ref={cluster}
            iconCreateFunction={clusterIcon}
            maxClusterRadius={45}
            disableClusteringAtZoom={NO_CLUSTER_ZOOM}
            showCoverageOnHover={false}
            // Off: after a pan the plugin drops markers it thinks are off-screen. Only useful for
            // thousands of markers.
            removeOutsideVisibleBounds={false}
            spiderfyOnMaxZoom
            chunkedLoading
          >
            {pins.map((pin) => (
              <Marker
                key={pin.place.id}
                position={pin.position}
                icon={pinIcon(pin.place, pin.place.id === selectedId)}
                zIndexOffset={pin.place.id === selectedId ? 1000 : 0}
                title={pin.place.name}
                eventHandlers={{ click: () => focus(pin.place.id) }}
                ref={(m) => {
                  if (m) markers.set(pin.place.id, m);
                  else markers.delete(pin.place.id);
                }}
              />
            ))}
          </MarkerClusterGroup>
        </MapContainer>
      </div>

      {snap !== "full" && (
        <a
          className="fab"
          href="#/add"
          aria-label="Add a place"
          title="Add a place"
          style={{ bottom: `calc(${sheetHeight + 16}px + env(safe-area-inset-bottom))` }}
        >
          <PlusIcon size={24} />
        </a>
      )}

      <div className="toasts" style={{ bottom: `calc(${toastBottom}px + env(safe-area-inset-bottom))` }}>
        {nothingToPick && (
          <div className="toast" role="status">
            <span>Nothing to pick: no places match the search and filters.</span>
            <button type="button" className="link-btn" onClick={() => setNothingToPick(false)}>
              OK
            </button>
          </div>
        )}
        {unvisited && (
          <div className="toast" role="status">
            <span>
              Unmarked <b>{unvisited.name}</b>
            </span>
            <button
              type="button"
              className="link-btn"
              onClick={() => {
                const u = unvisited;
                setUnvisited(null);
                update(u.id, { visited: true, visited_date: u.visited_date, rating: u.rating });
              }}
            >
              Undo
            </button>
            <button type="button" className="link-btn quiet" onClick={() => setUnvisited(null)}>
              Dismiss
            </button>
          </div>
        )}
        {removed && (
          <div className="toast" role="status">
            <span>
              Removed <b>{removed.name}</b>
            </span>
            <button type="button" className="link-btn" onClick={undoRemove}>
              Undo
            </button>
            <button type="button" className="link-btn quiet" onClick={() => setRemoved(null)}>
              Dismiss
            </button>
          </div>
        )}
        {error && (
          <div className="toast error" role="alert">
            <span>
              {error.startsWith("TypeError") || error.includes("500") || error.includes("502")
                ? "Can't reach the server. Check your connection and try again."
                : error}
            </span>
            <button type="button" className="link-btn" onClick={() => setError(null)}>
              Dismiss
            </button>
          </div>
        )}
      </div>

      <BottomSheet
        snap={snap}
        onSnap={setSnap}
        topSpace={topBar}
        onHeight={setSheetHeight}
        header={sheetHeader}
        label={mode === "place" && selected ? selected.name : mode === "filters" ? "Filters" : "Places"}
        view={mode === "place" ? `place-${selectedId}` : mode}
      >
        {sheetBody}
      </BottomSheet>
    </div>
  );
}

function countBy(places: Place[], keys: (p: Place) => string[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const p of places) for (const k of keys(p)) counts.set(k, (counts.get(k) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}
