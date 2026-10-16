import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, Popup, useMap } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import type { LatLngBoundsExpression, Marker as LeafletMarker, MarkerClusterGroup as LeafletClusterGroup } from "leaflet";
import { api, type Place, type Stats, type VisitUpdate } from "../api";
import { MinimalBasemap } from "../basemap";
import { FavoriteButton, Stars, VisitLog } from "../components/VisitLog";
import { cleanCaption, clusterIcon, pinClasses, pinIcon, spreadOverlaps, type Pin } from "../mapUtils";

const BAY_AREA_CENTER: [number, number] = [37.65, -122.2];
// Zoomed in this far, every pin shows on its own.
const NO_CLUSTER_ZOOM = 14;

type PinType = "all" | "todo" | "visited" | "favorites" | "approx" | "exact";
const PIN_TYPES: [PinType, string][] = [
  ["all", "All pin types"],
  ["todo", "To try"],
  ["visited", "Been here"],
  ["favorites", "Favorites"],
  ["exact", "Exact address"],
  ["approx", "Approximate"],
];

type SortKey = "number" | "rating" | "recent" | "favorites";
const SORTS: [SortKey, string][] = [
  ["number", "Pin number"],
  ["favorites", "Favorites first"],
  ["rating", "Top rated"],
  ["recent", "Recently visited"],
];

function matchesType(place: Place, type: PinType): boolean {
  switch (type) {
    case "todo": return !place.visited;
    case "visited": return place.visited;
    case "favorites": return place.favorite;
    case "approx": return place.is_approximate;
    case "exact": return !place.is_approximate;
    default: return true;
  }
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

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

// Leaflet measures its container once. If the map mounts hidden or zero-sized (a background
// tab, a collapsed pane), every pin projects to one point. Re-measure on resize, and only fit
// the view once the container has a real size. Refits whenever `fitKey` changes (filters).
function FitToPins({ pins, fitKey }: { pins: Pin[]; fitKey: string }) {
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
    map.fitBounds(pins.map((p) => p.position) as LatLngBoundsExpression, { padding: [40, 40], maxZoom: 14 });
    setFitted(fitKey);
  }, [map, pins, fitted, fitKey, size]);
  return null;
}

/** Flies to a pin chosen from the list, opening its cluster if needed, then its popup. */
function FlyToSelected({
  target,
  markers,
  cluster,
}: {
  target: { pin: Pin; nonce: number } | null;
  markers: Map<number, LeafletMarker>;
  cluster: React.RefObject<LeafletClusterGroup>;
}) {
  const map = useMap();
  useEffect(() => {
    if (!target) return;
    const marker = markers.get(target.pin.place.id);
    map.flyTo(target.pin.position, Math.max(map.getZoom(), NO_CLUSTER_ZOOM), { duration: 0.6 });
    map.once("moveend", () => {
      if (marker && cluster.current) cluster.current.zoomToShowLayer(marker, () => marker.openPopup());
      else marker?.openPopup();
    });
  }, [map, target, markers, cluster]);
  return null;
}

function PlacePopup({ place, onUpdate }: { place: Place; onUpdate: (u: VisitUpdate) => Promise<void> }) {
  return (
    <div className="popup">
      <div className="popup-head">
        <h3>{place.name}</h3>
        <FavoriteButton place={place} onUpdate={onUpdate} />
      </div>
      {place.address && <div className="popup-address">{place.address}</div>}
      {place.tags.length > 0 && <div className="popup-tags">{place.tags.join(" · ")}</div>}
      {place.is_approximate && (
        <div className="popup-approx">Approximate location: pop-up, home cook or city-level pin.</div>
      )}
      <a href={place.google_maps_url} target="_blank" rel="noreferrer">
        Open in Google Maps
      </a>
      <VisitLog place={place} onUpdate={onUpdate} />
      <div className="popup-reels">
        {place.reels.map((r) => (
          <div key={r.id} className="popup-reel">
            <a href={r.post_url} target="_blank" rel="noreferrer">
              {r.posted_by ? `@${r.posted_by}` : "Reel"}
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}

function SearchIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

export default function MapPage({ stats, onChanged }: { stats: Stats | null; onChanged: () => void }) {
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [city, setCity] = useState("");
  const [tag, setTag] = useState("");
  const [pinType, setPinType] = useState<PinType>("all");
  const [sort, setSort] = useState<SortKey>("number");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [flyTarget, setFlyTarget] = useState<{ pin: Pin; nonce: number } | null>(null);
  const markers = useRef(new Map<number, LeafletMarker>()).current;
  const cluster = useRef<LeafletClusterGroup>(null);

  useEffect(() => {
    api.places().then(setPlaces).catch((e) => setError(String(e)));
  }, []);

  // Numbers follow import order and stay put while filtering, so "#12" always means the same place.
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
          matchesType(place, pinType) &&
          matchesQuery(place, q),
      ),
    [numbered, city, tag, pinType, q],
  );
  const pins = useMemo(() => spreadOverlaps(shown), [shown]);
  const listed = useMemo(() => sortBy(shown, sort), [shown, sort]);

  async function update(placeId: number, change: VisitUpdate) {
    try {
      const updated = await api.updateVisit(placeId, change);
      setPlaces((prev) => prev?.map((p) => (p.id === updated.id ? updated : p)) ?? null);
      onChanged();
    } catch (e) {
      setError(String(e));
    }
  }

  function focus(placeId: number) {
    setSelectedId(placeId);
    const pin = pins.find((p) => p.place.id === placeId);
    if (pin) {
      setFlyTarget({ pin, nonce: Date.now() });
      document.querySelector(".map-card")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  return (
    <>
      <div className="chips">
        <span className="chip">
          <b>{stats?.reels_saved ?? "–"}</b> reels saved
        </span>
        <span className="chip">
          <b>{stats?.on_map ?? places?.length ?? "–"}</b> on the map
        </span>
        <span className="chip">
          <b>{stats?.cities ?? cities.length}</b> cities
        </span>
        <button className="chip" onClick={() => setPinType(pinType === "visited" ? "all" : "visited")}>
          <b>{stats?.visited ?? 0}</b> been there
        </button>
        <button className="chip" onClick={() => setPinType(pinType === "favorites" ? "all" : "favorites")}>
          <b>{stats?.favorites ?? 0}</b> favorites
        </button>
        {stats && stats.needs_review > 0 && (
          <a className="chip" href="#/review">
            <b>{stats.needs_review}</b> waiting for review
          </a>
        )}
      </div>

      <div className="search">
        <SearchIcon />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search a spot, dish, or poster"
          aria-label="Search places"
        />
      </div>

      <div className="filters">
        <label>
          City
          <select value={city} onChange={(e) => setCity(e.target.value)}>
            <option value="">All cities</option>
            {cities.map(([name, n]) => (
              <option key={name} value={name}>
                {name} ({n})
              </option>
            ))}
          </select>
        </label>
        <label>
          Pins
          <select value={pinType} onChange={(e) => setPinType(e.target.value as PinType)}>
            {PIN_TYPES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="tag-chips" role="group" aria-label="Food type">
        <button className={`tag-chip${tag === "" ? " on" : ""}`} onClick={() => setTag("")}>
          All food
        </button>
        {tags.map(([name, n]) => (
          <button key={name} className={`tag-chip${tag === name ? " on" : ""}`} onClick={() => setTag(tag === name ? "" : name)}>
            {name} <span>{n}</span>
          </button>
        ))}
      </div>

      <div className="legend">
        <span>
          <i className="todo" /> To try
        </span>
        <span>
          <i className="visited" /> Been here
        </span>
        <span>
          <i className="approx" /> Approximate location
        </span>
        <span>
          <b className="legend-star">★</b> Favorite
        </span>
      </div>

      {error && (
        <div className="error" role="alert">
          {error.startsWith("TypeError") || error.includes("500") || error.includes("502")
            ? "Can't reach the API. Is the backend running (uvicorn app.main:app --reload in backend/)?"
            : error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      <div className="map-card">
        {/* maxZoom is required by the cluster plugin; the vector basemap doesn't set one like tile layers do */}
        <MapContainer center={BAY_AREA_CENTER} zoom={10} minZoom={7} maxZoom={18}>
          <MinimalBasemap />
          <FitToPins pins={pins} fitKey={`${city}|${tag}|${pinType}`} />
          <FlyToSelected target={flyTarget} markers={markers} cluster={cluster} />
          <MarkerClusterGroup
            ref={cluster}
            iconCreateFunction={clusterIcon}
            maxClusterRadius={45}
            disableClusteringAtZoom={NO_CLUSTER_ZOOM}
            showCoverageOnHover={false}
            spiderfyOnMaxZoom
            chunkedLoading
          >
            {pins.map((pin) => (
              <Marker
                key={pin.place.id}
                position={pin.position}
                icon={pinIcon(pin.number, pin.place, pin.place.id === selectedId)}
                zIndexOffset={pin.place.id === selectedId ? 1000 : 0}
                eventHandlers={{ click: () => setSelectedId(pin.place.id) }}
                ref={(m) => {
                  if (m) markers.set(pin.place.id, m);
                  else markers.delete(pin.place.id);
                }}
              >
                <Popup>
                  <PlacePopup place={pin.place} onUpdate={(u) => update(pin.place.id, u)} />
                </Popup>
              </Marker>
            ))}
          </MarkerClusterGroup>
        </MapContainer>
      </div>

      <div className="list-head">
        <h2>
          <b>On the map</b>{" "}
          <span className="muted">
            — showing {shown.length} of {places?.length ?? 0}
          </span>
        </h2>
        <label>
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            {SORTS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {places && shown.length === 0 && <p className="empty">No places match. Try clearing the search or filters.</p>}
      {listed.map(({ place, number }) => {
        const first = place.reels[0];
        const caption = cleanCaption(first?.dish ?? null);
        const more = place.reels.length - 1;
        return (
          <div
            key={place.id}
            role="button"
            tabIndex={0}
            className={`place-card${place.id === selectedId ? " selected" : ""}`}
            onClick={() => focus(place.id)}
            onKeyDown={(e) => e.key === "Enter" && focus(place.id)}
          >
            <span className={`num ${pinClasses(place)}`}>{number}</span>
            <div className="body">
              <h3>{place.name}</h3>
              {caption && <p className="dish">{caption}</p>}
              {place.tags.length > 0 && (
                <div className="card-tags">
                  {place.tags.map((t) => (
                    <span key={t}>{t}</span>
                  ))}
                </div>
              )}
              {place.visited && (
                <div className="visit-summary">
                  <Stars rating={place.rating} />
                  {place.visited_date && <span>Visited {formatDate(place.visited_date)}</span>}
                </div>
              )}
              {place.notes && <p className="card-notes">“{place.notes}”</p>}
              <div className="meta">
                <span className={`dot ${place.visited ? "visited" : ""}`} />
                {place.city && <span>{place.city}</span>}
                <span>{place.is_approximate ? "approximate" : "exact address"}</span>
                {first?.posted_by && (
                  <span>
                    saved by @{first.posted_by}
                    {more > 0 ? ` +${more}` : ""}
                  </span>
                )}
              </div>
            </div>
            <div className="card-actions">
              <FavoriteButton place={place} onUpdate={(u) => update(place.id, u)} />
              <button
                className={`been${place.visited ? " on" : ""}`}
                onClick={(e) => {
                  e.stopPropagation();
                  update(place.id, { visited: !place.visited });
                }}
                aria-pressed={place.visited}
              >
                {place.visited ? "Been ✓" : "Been here?"}
              </button>
            </div>
          </div>
        );
      })}
    </>
  );
}

function countBy(places: Place[], keys: (p: Place) => string[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const p of places) for (const k of keys(p)) counts.set(k, (counts.get(k) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}
