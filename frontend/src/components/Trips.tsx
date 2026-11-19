import { useState } from "react";
import { api, ApiError, type ImportResult, type Trip } from "../api";
import { CheckIcon, SearchIcon } from "./Icons";

/** The middle of a trip's area, for opening a map on it. */
export function tripCenter(trip: Trip): [number, number] {
  return [(trip.south + trip.north) / 2, (trip.west + trip.east) / 2];
}

/** A trip's area as Leaflet bounds ([south, west], [north, east]). */
export function tripBounds(trip: Trip): [[number, number], [number, number]] {
  return [
    [trip.south, trip.west],
    [trip.north, trip.east],
  ];
}

function message(e: unknown): string {
  if (e instanceof ApiError) return typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail);
  return "Can't reach the server. Check your connection and try again.";
}

/** The trips view in the sheet: every map, the current one ticked; tap one to switch. */
export function TripsList({
  trips,
  currentId,
  onSwitch,
  onImport,
  onChanged,
}: {
  trips: Trip[];
  currentId: number;
  onSwitch: (trip: Trip) => void;
  onImport: (trip: Trip) => void;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<number | null>(null);

  async function rename(trip: Trip) {
    const name = window.prompt("Rename the trip", trip.name)?.trim();
    if (!name || name === trip.name) return;
    try {
      await api.renameTrip(trip.id, name);
      onChanged();
    } catch (e) {
      setError(message(e));
    }
  }

  async function remove(trip: Trip) {
    if (!window.confirm(`Delete "${trip.name}"? It's empty, so nothing else is lost.`)) return;
    try {
      await api.deleteTrip(trip.id);
      onChanged();
    } catch (e) {
      setError(message(e));
    }
  }

  async function copy(trip: Trip) {
    try {
      await navigator.clipboard.writeText(museAddress(trip));
      setCopied(trip.id);
      window.setTimeout(() => setCopied(null), 1800);
    } catch {
      setError("Couldn't copy; select the address and copy it by hand.");
    }
  }

  return (
    <div className="trips-view">
      {error && (
        <p className="notice error" role="alert">
          <span>{error}</span>
          <button type="button" className="link-btn" onClick={() => setError(null)}>
            Dismiss
          </button>
        </p>
      )}
      <ul className="trip-list">
        {trips.map((trip) => (
          <li key={trip.id} className={`trip-row${trip.id === currentId ? " current" : ""}`}>
            <button type="button" className="trip-main" onClick={() => onSwitch(trip)} aria-current={trip.id === currentId}>
              <span className="trip-text">
                <span className="trip-name">{trip.name}</span>
                <span className="trip-meta">
                  {trip.places} {trip.places === 1 ? "place" : "places"}
                  {trip.is_home ? " · home" : ""}
                </span>
              </span>
              {trip.id === currentId && <CheckIcon size={20} className="trip-check" />}
            </button>
            {!trip.is_home && (
              <div className="trip-actions">
                <button type="button" className="link-btn" onClick={() => onImport(trip)}>
                  Import a Muse file
                </button>
                <button type="button" className="link-btn" onClick={() => rename(trip)}>
                  Rename
                </button>
                {trip.places === 0 && (
                  <button type="button" className="link-btn danger" onClick={() => remove(trip)}>
                    Delete
                  </button>
                )}
                <details className="more muse-address">
                  <summary>Muse upload address</summary>
                  <code>{museAddress(trip)}</code>
                  <button type="button" className="link-btn" onClick={() => copy(trip)}>
                    {copied === trip.id ? "Copied" : "Copy"}
                  </button>
                </details>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Where Muse sends a trip's collection (same token as the Bay Area uploads). */
function museAddress(trip: Trip): string {
  return `${location.origin}/api/import?trip=${trip.slug}`;
}

interface Found {
  label: string;
  name: string;
  box: { south: number; west: number; north: number; east: number };
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/**
 * Find a city with OpenStreetMap's free search (Nominatim; no key, a few searches at most, as its
 * usage policy asks). A city's official boundary can be huge (Tokyo's includes islands 1,000 km
 * away), so the trip's area is a box around the city's centre: big enough for the city and its
 * surroundings, never a whole country.
 */
async function findCity(q: string): Promise<Found[]> {
  const params = new URLSearchParams({ q, format: "jsonv2", limit: "5", "accept-language": "en" });
  const res = await fetch(`https://nominatim.openstreetmap.org/search?${params}`);
  if (!res.ok) throw new Error(`search failed (${res.status})`);
  const rows: { display_name: string; name?: string; lat: string; lon: string; boundingbox: string[] }[] = await res.json();
  return rows.map((r) => {
    const lat = Number(r.lat);
    const lng = Number(r.lon);
    const [s, n, w, e] = r.boundingbox.map(Number);
    const halfLat = clamp(((n - s) / 2) * 1.15, 0.12, 0.6);
    const halfLng = clamp(((e - w) / 2) * 1.15, 0.15, 0.8);
    return {
      label: r.display_name,
      name: r.name || r.display_name.split(",")[0],
      box: { south: lat - halfLat, north: lat + halfLat, west: lng - halfLng, east: lng + halfLng },
    };
  });
}

/** New trip: type a city to set the area, name it (the city's name to start with), create. */
export function NewTripForm({ onCreated }: { onCreated: (trip: Trip) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Found[] | null>(null);
  const [picked, setPicked] = useState<Found | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    setPicked(null);
    try {
      const found = await findCity(query.trim());
      setResults(found);
      if (found.length === 1) pick(found[0]);
    } catch {
      setError("The city search isn't answering. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  function pick(found: Found) {
    setPicked(found);
    if (!name.trim()) setName(found.name);
  }

  async function create() {
    if (!picked || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      onCreated(await api.createTrip({ name: name.trim(), ...picked.box }));
    } catch (e) {
      setError(message(e));
      setBusy(false);
    }
  }

  return (
    <div className="new-trip">
      <form className="city-search" onSubmit={search}>
        <label className="field">
          <span className="field-label">Where are you going?</span>
          <span className="search">
            <SearchIcon size={18} />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="A city, e.g. Tokyo"
              autoComplete="off"
              aria-label="City"
            />
          </span>
        </label>
        <button type="submit" disabled={busy || !query.trim()}>
          Find
        </button>
      </form>

      {results && results.length === 0 && <p className="muted small">Nothing found. Try the city's English name.</p>}
      {results && results.length > 0 && (
        <ul className="city-results" aria-label="Places found">
          {results.map((r) => (
            <li key={r.label}>
              <button
                type="button"
                className={`city-result${picked === r ? " on" : ""}`}
                aria-pressed={picked === r}
                onClick={() => pick(r)}
              >
                <span>{r.label}</span>
                {picked === r && <CheckIcon size={18} />}
              </button>
            </li>
          ))}
        </ul>
      )}

      {picked && (
        <label className="field">
          <span className="field-label">Trip name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
        </label>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <button type="button" className="primary" disabled={busy || !picked || !name.trim()} onClick={create}>
        Create trip
      </button>
      <p className="muted small">City search by OpenStreetMap.</p>
    </div>
  );
}

/**
 * Import a Muse export into a trip: pick the file (or paste its JSON). Same import as Muse's own
 * uploads: reels already on any map are skipped, pins outside the trip go to "Sort out reels".
 */
export function ImportForm({ trip, onImported }: { trip: Trip; onImported: () => void }) {
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function readFile(file: File | undefined) {
    if (!file) return;
    setText(await file.text());
    setFileName(file.name);
    setResult(null);
    setError(null);
  }

  async function run() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.importExport(trip.slug, text));
      setText("");
      setFileName(null);
      onImported();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="import-view">
      <p className="muted small">
        Ask Muse to export the collection for this trip, then pick the file it gives you, or paste its text.
      </p>
      <label className="btn file-btn">
        Choose a file
        <input type="file" accept=".json,application/json,text/plain" onChange={(e) => readFile(e.target.files?.[0])} />
      </label>
      {fileName && <p className="small">{fileName}</p>}
      <label className="field">
        <span className="field-label">Or paste it</span>
        <textarea
          rows={4}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setFileName(null);
          }}
          placeholder='[{"venue": "…", "post_url": "…"}]'
          spellCheck={false}
        />
      </label>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <p className="notice" role="status">
          {result.imported === 0
            ? `Nothing new: ${result.skipped} already on a map.`
            : `Added ${result.pinned + result.approximate} ${result.pinned + result.approximate === 1 ? "place" : "places"}` +
              (result.needs_review ? `, ${result.needs_review} to sort out` : "") +
              (result.skipped ? `, ${result.skipped} already there` : "") +
              "."}
        </p>
      )}
      <button type="button" className="primary" disabled={busy || !text.trim()} onClick={run}>
        {busy ? "Importing…" : `Import into ${trip.name}`}
      </button>
    </div>
  );
}
