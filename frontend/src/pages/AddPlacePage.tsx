import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import PinPicker from "../components/PinPicker";

interface Duplicate {
  message: string;
  place_id: number | null;
  kind: "same_link" | "similar_nearby";
}

/** Add a place by hand: name, optional link/address, pin (tap the map, use my location, or type), extras. */
export default function AddPlacePage({ onAdded }: { onAdded: (placeId: number) => void }) {
  const [name, setName] = useState("");
  const [link, setLink] = useState("");
  const [address, setAddress] = useState("");
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [approx, setApprox] = useState(false);
  const [favorite, setFavorite] = useState(true); // you're adding it because you want to go
  const [visited, setVisited] = useState(false);
  const [notes, setNotes] = useState("");
  const [allTags, setAllTags] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<Duplicate | null>(null);

  useEffect(() => {
    api.tags().then(setAllTags).catch(() => setAllTags([]));
  }, []);

  const latN = Number(lat);
  const lngN = Number(lng);
  const hasPin = lat.trim() !== "" && lng.trim() !== "" && Number.isFinite(latN) && Number.isFinite(lngN);
  const valid = name.trim() !== "" && hasPin;

  async function save(force = false) {
    if (!valid) return;
    setBusy(true);
    setError(null);
    setDuplicate(null);
    try {
      const place = await api.createPlace({
        name: name.trim(),
        lat: latN,
        lng: lngN,
        address: address.trim() || null,
        link: link.trim() || null,
        is_approximate: approx,
        tags: tags.length ? tags : null, // none picked: let the app work them out from the name
        favorite,
        visited,
        notes: notes.trim() || null,
        force,
      });
      onAdded(place.id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && typeof e.detail === "object" && e.detail) {
        setDuplicate(e.detail as Duplicate);
      } else if (e instanceof ApiError && typeof e.detail === "string") {
        setError(e.detail);
      } else {
        setError(String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="add-page">
      <form
        className="add-form"
        onSubmit={(e) => {
          e.preventDefault();
          save(false);
        }}
      >
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Corner Taqueria" required autoFocus />
        </label>

        <div className="field">
          <span className="field-label">Where is it?</span>
          <span className="muted small">Tap the map, use your location, or type coordinates.</span>
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
              <input type="checkbox" checked={approx} onChange={(e) => setApprox(e.target.checked)} /> Approximate (pop-up, truck)
            </label>
          </div>
        </div>

        <label>
          Link <span className="muted small">(optional: the reel, their site, anything)</span>
          <input value={link} onChange={(e) => setLink(e.target.value)} inputMode="url" placeholder="https://www.instagram.com/reel/…" />
        </label>
        <label>
          Address <span className="muted small">(optional)</span>
          <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="123 Main St, Oakland, CA" />
        </label>

        {allTags.length > 0 && (
          <div className="field">
            <span className="field-label">
              Food type <span className="muted small">(optional; otherwise worked out from the name)</span>
            </span>
            <div className="tag-options">
              {allTags.map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`tag-chip${tags.includes(t) ? " on" : ""}`}
                  aria-pressed={tags.includes(t)}
                  onClick={() => setTags(tags.includes(t) ? tags.filter((x) => x !== t) : [...tags, t])}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="checks">
          <label className="check">
            <input type="checkbox" checked={favorite} onChange={(e) => setFavorite(e.target.checked)} /> ★ Want to go
          </label>
          <label className="check">
            <input type="checkbox" checked={visited} onChange={(e) => setVisited(e.target.checked)} /> Been here
          </label>
        </div>
        <label>
          Notes <span className="muted small">(optional)</span>
          <textarea className="visit-notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What to order, hours…" />
        </label>

        {duplicate && (
          <div className="notice warn" role="alert">
            <span>{duplicate.message}</span>
            {duplicate.place_id !== null && (
              <a href={`#/place/${duplicate.place_id}`} className="link-btn">
                Show it
              </a>
            )}
            {duplicate.kind === "similar_nearby" && (
              <button type="button" onClick={() => save(true)} disabled={busy}>
                Add anyway
              </button>
            )}
          </div>
        )}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        <button type="submit" className="primary add-submit" disabled={!valid || busy}>
          {busy ? "Adding…" : "Add to the map"}
        </button>
        {!hasPin && <span className="muted small">Place the pin to add it.</span>}
      </form>
    </main>
  );
}
