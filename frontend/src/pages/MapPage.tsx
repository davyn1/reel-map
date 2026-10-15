import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import { api, type Place } from "../api";

const BAY_AREA_CENTER: [number, number] = [37.65, -122.2];
// Pins sharing exact coordinates (e.g. pop-ups pinned to a city centre) are fanned out
// around the shared point by this many degrees so each one is clickable.
const SPREAD_DEG = 0.0015;

const COLORS = { todo: "#d9480f", visited: "#2b8a3e" };

interface Pin {
  place: Place;
  position: [number, number];
}

export function spreadOverlaps(places: Place[]): Pin[] {
  const groups = new Map<string, Place[]>();
  for (const p of places) {
    const key = `${p.lat.toFixed(5)},${p.lng.toFixed(5)}`;
    groups.set(key, [...(groups.get(key) ?? []), p]);
  }
  const pins: Pin[] = [];
  for (const group of groups.values()) {
    group.forEach((place, i) => {
      if (group.length === 1) {
        pins.push({ place, position: [place.lat, place.lng] });
        return;
      }
      const angle = (2 * Math.PI * i) / group.length;
      const dLat = SPREAD_DEG * Math.sin(angle);
      const dLng = (SPREAD_DEG * Math.cos(angle)) / Math.cos((place.lat * Math.PI) / 180);
      pins.push({ place, position: [place.lat + dLat, place.lng + dLng] });
    });
  }
  return pins;
}

// Leaflet measures its container once. If the map mounts hidden or zero-sized (a background
// tab, a collapsed pane), every pin projects to one point. Re-measure on resize, and only fit
// the view once the container has a real size.
function FitToPins({ pins }: { pins: Pin[] }) {
  const map = useMap();
  const [fitted, setFitted] = useState(false);
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
    if (fitted || pins.length === 0 || size === 0) return;
    map.fitBounds(pins.map((p) => p.position) as LatLngBoundsExpression, { padding: [30, 30] });
    setFitted(true);
  }, [map, pins, fitted, size]);
  return null;
}

function shortDish(dish: string | null): string | null {
  if (!dish) return null;
  return dish.length > 90 ? dish.slice(0, 90).trimEnd() + "…" : dish;
}

function PlacePopup({ place, onVisited }: { place: Place; onVisited: (visited: boolean) => Promise<void> }) {
  const [saving, setSaving] = useState(false);
  return (
    <div className="popup">
      <h3>{place.name}</h3>
      {place.address && <div className="popup-address">{place.address}</div>}
      {place.is_approximate && (
        <div className="popup-approx">Approximate location: pop-up, home cook or city-level pin.</div>
      )}
      <a href={place.google_maps_url} target="_blank" rel="noreferrer">
        Open in Google Maps
      </a>
      <label className="popup-visited">
        <input
          type="checkbox"
          checked={place.visited}
          disabled={saving}
          onChange={async (e) => {
            setSaving(true);
            try {
              await onVisited(e.target.checked);
            } finally {
              setSaving(false);
            }
          }}
        />
        Been here{place.visited && place.visited_date ? ` (${place.visited_date})` : ""}
      </label>
      <div className="popup-reels">
        {place.reels.map((r) => (
          <div key={r.id} className="popup-reel">
            <a href={r.post_url} target="_blank" rel="noreferrer">
              {r.posted_by ? `@${r.posted_by}` : "Reel"}
            </a>
            {shortDish(r.dish) && <span> · {shortDish(r.dish)}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MapPage() {
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.places().then(setPlaces).catch((e) => setError(String(e)));
  }, []);

  const pins = useMemo(() => spreadOverlaps(places ?? []), [places]);
  const visitedCount = places?.filter((p) => p.visited).length ?? 0;

  async function setVisited(placeId: number, visited: boolean) {
    try {
      const updated = await api.setVisited(placeId, visited);
      setPlaces((prev) => prev?.map((p) => (p.id === updated.id ? updated : p)) ?? null);
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="map-page">
      <header className="map-header">
        {places && (
          <span className="counts">
            {places.length} places · {visitedCount} visited
          </span>
        )}
        <span className="legend">
          <span className="dot" style={{ background: COLORS.todo }} /> to try
          <span className="dot" style={{ background: COLORS.visited }} /> been here
          <span className="dot hollow" /> approximate
        </span>
      </header>
      {error && (
        <div className="error" role="alert">
          {error.startsWith("TypeError") || error.includes("500") || error.includes("502")
            ? "Can't reach the API. Is the backend running (uvicorn app.main:app --reload in backend/)?"
            : error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}
      <MapContainer center={BAY_AREA_CENTER} zoom={10} className="map">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitToPins pins={pins} />
        {pins.map(({ place, position }) => {
          const color = place.visited ? COLORS.visited : COLORS.todo;
          return (
            <CircleMarker
              key={place.id}
              center={position}
              radius={place.is_approximate ? 10 : 8}
              pathOptions={
                place.is_approximate
                  ? { color, weight: 2, dashArray: "4 4", fillColor: color, fillOpacity: 0.15 }
                  : { color: "#fff", weight: 2, fillColor: color, fillOpacity: 0.95 }
              }
            >
              <Popup>
                <PlacePopup place={place} onVisited={(v) => setVisited(place.id, v)} />
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
