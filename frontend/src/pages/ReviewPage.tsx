import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type AttachBody, type Place, type ReviewReel, type Trip } from "../api";
import PinPicker from "../components/PinPicker";
import { tripCenter } from "../components/Trips";
import { useOnDataChanged } from "../liveSync";

// Short, plain names for the importer's flags (backend/app/importer/flags.py). The server's longer
// description stays in the title, and the card's reason line says what to do.
const FLAG_LABELS: Record<string, string> = {
  no_venue: "No name",
  no_address: "No address",
  city_only_address: "City only",
  no_street_address: "No street number",
  no_city: "No city",
  no_coords: "No location",
  coords_outside_area: "Outside the trip's area",
  coords_outside_bay_area: "Outside the Bay Area",
  no_confidence: "Muse unsure",
  multi_spot: "Several spots",
};
const flagLabel = (f: string) => FLAG_LABELS[f] ?? f.replace(/_/g, " ");

function googleMapsSearch(query: string): string {
  return "https://www.google.com/maps/search/?" + new URLSearchParams({ api: "1", query });
}

function cleanVenue(venue: string | null): string {
  return (venue ?? "").replace(/\([^)]*\)/g, "").trim();
}

export default function ReviewPage({ onQueueChange }: { onQueueChange: () => void }) {
  const [queue, setQueue] = useState<ReviewReel[] | null>(null);
  const [places, setPlaces] = useState<Place[]>([]);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [flagNames, setFlagNames] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<string>("");
  const [openId, setOpenId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async (quiet = false) => {
    try {
      // Places in every trip: "a place already on the map" offers the ones in the reel's own trip.
      const [q, p, f, t] = await Promise.all([api.reviewQueue(), api.places("all"), api.flags(), api.trips()]);
      setQueue(q);
      setPlaces(p);
      setFlagNames(f);
      setTrips(t);
    } catch (e) {
      if (!quiet) setError(String(e));
    }
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);
  // Live sync: the other phone may have sorted out some of these. An open Fix panel keeps what's
  // typed in it (it's keyed by reel), and a failed refresh just keeps the current list.
  useOnDataChanged(() => reload(true));

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
        <h2>{queue ? `${queue.length} reel${queue.length === 1 ? "" : "s"} to sort out` : "Loading…"}</h2>
        <label>
          Show{" "}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All reels</option>
            {Object.keys(flagNames)
              .filter((f) => flagCounts[f])
              .map((f) => (
                <option key={f} value={f}>
                  {flagLabel(f)} ({flagCounts[f]})
                </option>
              ))}
          </select>
        </label>
      </div>
      {message && (
        <div className="notice" role="status">
          <span>{message}</span>
          <button type="button" className="link-btn" onClick={() => setMessage(null)}>
            Dismiss
          </button>
        </div>
      )}
      {error && (
        <div className="notice error" role="alert">
          <span>{error}</span>
          <button type="button" className="link-btn" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}
      {queue && shown.length === 0 && (
        <p className="empty">{filter ? "Nothing left with this flag." : "All sorted. New reels that need a hand show up here."}</p>
      )}
      {shown.map((reel) => (
        <ReelCard
          key={reel.id}
          reel={reel}
          trip={trips.find((t) => t.id === reel.trip.id) ?? null}
          places={places.filter((p) => p.trip_id === reel.trip.id)}
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
  trip: Trip | null;
  places: Place[];
  flagNames: Record<string, string>;
  open: boolean;
  onToggle: () => void;
  onAttach: (body: AttachBody) => Promise<void>;
  onResolve: () => Promise<void>;
  onReject: () => Promise<void>;
}

function ReelCard({ reel, trip, places, flagNames, open, onToggle, onAttach, onResolve, onReject }: CardProps) {
  const venue = cleanVenue(reel.venue_raw);
  const searchQuery = [venue, reel.address_raw].filter(Boolean).join(", ");
  const hasPlace = reel.place !== null;

  return (
    <article className={`reel-card${open ? " open" : ""}`}>
      <header>
        <div>
          <h3>{venue || "Unnamed spot"}</h3>
          <p className="reel-sub">
            {!reel.trip.is_home && <span className="reel-trip">{reel.trip.name} · </span>}
            <a href={reel.post_url} target="_blank" rel="noreferrer">
              {reel.posted_by ? `@${reel.posted_by}` : "Open the reel"}
            </a>
            {reel.address_raw && <> · {reel.address_raw}</>}
          </p>
        </div>
        <button type="button" onClick={onToggle} aria-expanded={open}>
          {open ? "Close" : "Fix"}
        </button>
      </header>
      <div className="flags">
        {reel.flags.map((f) => (
          <span key={f} className="flag" title={flagNames[f]}>
            {flagLabel(f)}
          </span>
        ))}
      </div>
      {reel.review_reason && <p className="reason">{reel.review_reason}</p>}
      {reel.dish && <p className="dish">“{reel.dish}”</p>}
      {(reel.muse_note || reel.muse_confidence) && (
        <details className="more">
          <summary>More from Muse</summary>
          {reel.muse_confidence && <p>Confidence: {reel.muse_confidence}</p>}
          {reel.muse_note && <p>{reel.muse_note}</p>}
        </details>
      )}
      {hasPlace && (
        <p className="current">
          On the map as <strong>{reel.place!.name}</strong>
          {reel.extra_places.length > 0 && <> + {reel.extra_places.map((p) => p.name).join(", ")}</>}
        </p>
      )}
      {open && (
        <FixPanel
          reel={reel}
          center={trip ? tripCenter(trip) : [37.65, -122.2]}
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
  center: [number, number];
  places: Place[];
  defaultName: string;
  searchUrl: string | null;
  onAttach: (body: AttachBody) => Promise<void>;
  onResolve: (() => Promise<void>) | null;
  onReject: () => Promise<void>;
}

function FixPanel({ reel, center, places, defaultName, searchUrl, onAttach, onResolve, onReject }: FixProps) {
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
      <div className="chip-row" role="group" aria-label="Where it goes">
        <button type="button" className={`chip${tab === "new" ? " on" : ""}`} aria-pressed={tab === "new"} onClick={() => setTab("new")}>
          New place
        </button>
        <button
          type="button"
          className={`chip${tab === "existing" ? " on" : ""}`}
          aria-pressed={tab === "existing"}
          onClick={() => setTab("existing")}
        >
          A place already on the map
        </button>
      </div>
      {tab === "new" ? (
        <NewPlaceForm
          reel={reel}
          center={center}
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
          <button type="button" disabled={busy} onClick={run(onResolve)}>
            Done: keep {reel.place?.name}
            {reel.extra_places.length ? ` + ${reel.extra_places.length} more` : ""}
          </button>
        )}
        <button
          type="button"
          className="link-btn danger"
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
  center,
  defaultName,
  busy,
  onSave,
}: {
  reel: ReviewReel;
  center: [number, number];
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
        Address <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Optional" />
      </label>
      <div className="pin-hint muted">Tap the map to drop the pin.</div>
      <PinPicker
        center={center}
        pin={hasPin ? [latN, lngN] : null}
        onPick={(la, ln) => {
          setLat(la.toFixed(6));
          setLng(ln.toFixed(6));
        }}
      />
      <label className="check">
        <input type="checkbox" checked={approx} onChange={(e) => setApprox(e.target.checked)} /> Approximate spot (pop-up,
        truck, city-level)
      </label>
      <details className="more">
        <summary>Type coordinates</summary>
        <div className="coords">
          <label>
            Latitude <input value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" />
          </label>
          <label>
            Longitude <input value={lng} onChange={(e) => setLng(e.target.value)} inputMode="decimal" />
          </label>
        </div>
      </details>
      <button type="submit" className="primary" disabled={!valid || busy}>
        Save place
      </button>
    </form>
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
            <button type="button" disabled={busy} onClick={() => onPick(p.id)}>
              Use this
            </button>
          </li>
        ))}
        {matches.length === 0 && <li className="muted">No matching places.</li>}
      </ul>
    </div>
  );
}
