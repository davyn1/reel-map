import { useCallback, useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, TileLayer, useMapEvents } from "react-leaflet";
import { api, type AttachBody, type Place, type ReviewReel } from "../api";

const BAY_AREA_CENTER: [number, number] = [37.65, -122.2];

function googleMapsSearch(query: string): string {
  return "https://www.google.com/maps/search/?" + new URLSearchParams({ api: "1", query });
}

function cleanVenue(venue: string | null): string {
  return (venue ?? "").replace(/\([^)]*\)/g, "").trim();
}

export default function ReviewPage({ onQueueChange }: { onQueueChange: () => void }) {
  const [queue, setQueue] = useState<ReviewReel[] | null>(null);
  const [places, setPlaces] = useState<Place[]>([]);
  const [flagNames, setFlagNames] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<string>("");
  const [openId, setOpenId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [q, p, f] = await Promise.all([api.reviewQueue(), api.places(), api.flags()]);
      setQueue(q);
      setPlaces(p);
      setFlagNames(f);
    } catch (e) {
      setError(String(e));
    }
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);

  const flagCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of queue ?? []) for (const f of r.flags) counts[f] = (counts[f] ?? 0) + 1;
    return counts;
  }, [queue]);
  const shown = (queue ?? []).filter((r) => !filter || r.flags.includes(filter));

  async function act(label: string, action: () => Promise<ReviewReel>) {
    setError(null);
    try {
      const reel = await action();
      setMessage(`${label}: ${cleanVenue(reel.venue_raw) || reel.post_url}`);
      if (reel.status !== "needs_review") setOpenId(null);
      await reload();
      onQueueChange();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <main className="review-page">
      <div className="review-toolbar">
        <h2>Needs review{queue ? ` (${queue.length})` : ""}</h2>
        <label>
          Flag{" "}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All</option>
            {Object.keys(flagNames)
              .filter((f) => flagCounts[f])
              .map((f) => (
                <option key={f} value={f}>
                  {f} ({flagCounts[f]})
                </option>
              ))}
          </select>
        </label>
      </div>
      {message && (
        <div className="notice" role="status">
          {message} <button onClick={() => setMessage(null)}>Dismiss</button>
        </div>
      )}
      {error && (
        <div className="error" role="alert">
          {error} <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}
      {queue && shown.length === 0 && <p className="empty">Nothing to review{filter ? " with this flag" : ""}.</p>}
      {shown.map((reel) => (
        <ReelCard
          key={reel.id}
          reel={reel}
          places={places}
          flagNames={flagNames}
          open={openId === reel.id}
          onToggle={() => setOpenId(openId === reel.id ? null : reel.id)}
          onAttach={(body) =>
            act(body.mode === "add" ? "Added spot" : "Matched", () => api.attachPlace(reel.id, body))
          }
          onResolve={() => act("Resolved", () => api.resolve(reel.id))}
          onReject={() => act("Rejected", () => api.reject(reel.id))}
        />
      ))}
    </main>
  );
}

interface CardProps {
  reel: ReviewReel;
  places: Place[];
  flagNames: Record<string, string>;
  open: boolean;
  onToggle: () => void;
  onAttach: (body: AttachBody) => Promise<void>;
  onResolve: () => Promise<void>;
  onReject: () => Promise<void>;
}

function ReelCard({ reel, places, flagNames, open, onToggle, onAttach, onResolve, onReject }: CardProps) {
  const venue = cleanVenue(reel.venue_raw);
  const searchQuery = [venue, reel.address_raw].filter(Boolean).join(", ");
  const hasPlace = reel.place !== null;

  return (
    <article className={`reel-card${open ? " open" : ""}`}>
      <header>
        <div>
          <h3>{reel.venue_raw ?? <span className="muted">(no venue)</span>}</h3>
          <div className="muted">
            <a href={reel.post_url} target="_blank" rel="noreferrer">
              {reel.posted_by ? `@${reel.posted_by}` : "Open reel"}
            </a>
            {reel.muse_confidence && <> · Muse confidence: {reel.muse_confidence}</>}
            {reel.address_raw && <> · {reel.address_raw}</>}
          </div>
        </div>
        <button onClick={onToggle}>{open ? "Close" : "Fix"}</button>
      </header>
      <div className="flags">
        {reel.flags.map((f) => (
          <span key={f} className="flag" title={flagNames[f]}>
            {f}
          </span>
        ))}
      </div>
      {reel.review_reason && <p className="reason">Why: {reel.review_reason}</p>}
      {reel.muse_note && <p className="note">Muse: {reel.muse_note}</p>}
      {reel.dish && <p className="dish">“{reel.dish}”</p>}
      {hasPlace && (
        <p className="current">
          On the map as <strong>{reel.place!.name}</strong>
          {reel.extra_places.length > 0 && <> + {reel.extra_places.map((p) => p.name).join(", ")}</>}
        </p>
      )}
      {open && (
        <FixPanel
          reel={reel}
          places={places}
          defaultName={venue}
          searchUrl={searchQuery ? googleMapsSearch(searchQuery) : null}
          onAttach={onAttach}
          onResolve={hasPlace ? onResolve : null}
          onReject={onReject}
        />
      )}
    </article>
  );
}

interface FixProps {
  reel: ReviewReel;
  places: Place[];
  defaultName: string;
  searchUrl: string | null;
  onAttach: (body: AttachBody) => Promise<void>;
  onResolve: (() => Promise<void>) | null;
  onReject: () => Promise<void>;
}

function FixPanel({ reel, places, defaultName, searchUrl, onAttach, onResolve, onReject }: FixProps) {
  const [tab, setTab] = useState<"new" | "existing">("new");
  // Multi-spot reels already have their main place: default to adding another spot.
  const [mode, setMode] = useState<"replace" | "add">(reel.place ? "add" : "replace");
  const [busy, setBusy] = useState(false);

  const run = (fn: () => Promise<void>) => async () => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fix-panel">
      <p className="muted">
        Open the reel to see which spot it is
        {searchUrl && (
          <>
            , or{" "}
            <a href={searchUrl} target="_blank" rel="noreferrer">
              search Google Maps
            </a>{" "}
            for Muse's guess
          </>
        )}
        .
      </p>
      {reel.place && (
        <fieldset className="mode">
          <label>
            <input type="radio" checked={mode === "add"} onChange={() => setMode("add")} /> Add another spot from
            this reel
          </label>
          <label>
            <input type="radio" checked={mode === "replace"} onChange={() => setMode("replace")} /> Replace{" "}
            {reel.place.name}
          </label>
        </fieldset>
      )}
      <div className="tabs">
        <button className={tab === "new" ? "active" : ""} onClick={() => setTab("new")}>
          New place
        </button>
        <button className={tab === "existing" ? "active" : ""} onClick={() => setTab("existing")}>
          Existing place
        </button>
      </div>
      {tab === "new" ? (
        <NewPlaceForm
          reel={reel}
          defaultName={mode === "add" ? "" : defaultName}
          busy={busy}
          onSave={(new_place) => run(() => onAttach({ new_place, mode }))()}
        />
      ) : (
        <ExistingPlacePicker
          places={places}
          excludeIds={[reel.place?.id, ...reel.extra_places.map((p) => p.id)]}
          busy={busy}
          onPick={(place_id) => run(() => onAttach({ place_id, mode }))()}
        />
      )}
      <div className="fix-actions">
        {onResolve && (
          <button disabled={busy} onClick={run(onResolve)}>
            Done: keep {reel.place?.name}
            {reel.extra_places.length ? ` + ${reel.extra_places.length} more` : ""}
          </button>
        )}
        <button
          className="danger"
          disabled={busy}
          onClick={() => {
            if (window.confirm("Reject this reel? It will be removed from review and the map.")) run(onReject)();
          }}
        >
          Reject reel
        </button>
      </div>
    </div>
  );
}

function NewPlaceForm({
  reel,
  defaultName,
  busy,
  onSave,
}: {
  reel: ReviewReel;
  defaultName: string;
  busy: boolean;
  onSave: (p: { name: string; lat: number; lng: number; address: string | null; is_approximate: boolean }) => void;
}) {
  const [name, setName] = useState(defaultName);
  const [address, setAddress] = useState("");
  const [lat, setLat] = useState(reel.lat_raw?.toString() ?? "");
  const [lng, setLng] = useState(reel.lng_raw?.toString() ?? "");
  const [approx, setApprox] = useState(false);
  useEffect(() => setName(defaultName), [defaultName]);

  const latN = Number(lat);
  const lngN = Number(lng);
  const hasPin = lat !== "" && lng !== "" && Number.isFinite(latN) && Number.isFinite(lngN);
  const valid = name.trim() !== "" && hasPin;

  return (
    <form
      className="new-place"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onSave({ name: name.trim(), lat: latN, lng: lngN, address: address.trim() || null, is_approximate: approx });
      }}
    >
      <label>
        Name <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Address <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="optional" />
      </label>
      <div className="pin-hint muted">Click the map to drop the pin, or type coordinates.</div>
      <PinPicker
        pin={hasPin ? [latN, lngN] : null}
        onPick={(la, ln) => {
          setLat(la.toFixed(6));
          setLng(ln.toFixed(6));
        }}
      />
      <div className="coords">
        <label>
          Lat <input value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" />
        </label>
        <label>
          Lng <input value={lng} onChange={(e) => setLng(e.target.value)} inputMode="decimal" />
        </label>
        <label className="check">
          <input type="checkbox" checked={approx} onChange={(e) => setApprox(e.target.checked)} /> Approximate
        </label>
      </div>
      <button type="submit" className="primary" disabled={!valid || busy}>
        Save place
      </button>
    </form>
  );
}

function ClickToPick({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) });
  return null;
}

function PinPicker({ pin, onPick }: { pin: [number, number] | null; onPick: (lat: number, lng: number) => void }) {
  return (
    <MapContainer center={pin ?? BAY_AREA_CENTER} zoom={pin ? 15 : 9} className="pin-picker">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ClickToPick onPick={onPick} />
      {pin && <CircleMarker center={pin} radius={8} pathOptions={{ color: "#fff", weight: 2, fillColor: "#0969da", fillOpacity: 0.95 }} />}
    </MapContainer>
  );
}

function ExistingPlacePicker({
  places,
  excludeIds,
  busy,
  onPick,
}: {
  places: Place[];
  excludeIds: (number | undefined)[];
  busy: boolean;
  onPick: (placeId: number) => void;
}) {
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const matches = places
    .filter((p) => !excludeIds.includes(p.id))
    .filter((p) => !needle || `${p.name} ${p.address ?? ""}`.toLowerCase().includes(needle))
    .slice(0, 8);
  return (
    <div className="existing">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search places on the map" autoFocus />
      <ul>
        {matches.map((p) => (
          <li key={p.id}>
            <span>
              <strong>{p.name}</strong> <span className="muted">{p.address}</span>
            </span>
            <button disabled={busy} onClick={() => onPick(p.id)}>
              Use this
            </button>
          </li>
        ))}
        {matches.length === 0 && <li className="muted">No matching places.</li>}
      </ul>
    </div>
  );
}
