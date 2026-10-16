import { useEffect, useState } from "react";
import type { Place, VisitUpdate } from "../api";

export function Stars({ rating }: { rating: number | null }) {
  if (!rating) return null;
  return (
    <span className="stars-static" aria-label={`${rating} out of 5`}>
      {"★".repeat(rating)}
      <span className="dim">{"★".repeat(5 - rating)}</span>
    </span>
  );
}

/** Click a star to rate; click the current rating again to clear it. */
export function StarInput({ value, onChange }: { value: number | null; onChange: (v: number | null) => void }) {
  const [hover, setHover] = useState<number | null>(null);
  const shown = hover ?? value ?? 0;
  return (
    <span className="stars-input" onMouseLeave={() => setHover(null)}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          className={n <= shown ? "on" : ""}
          onMouseEnter={() => setHover(n)}
          onClick={() => onChange(value === n ? null : n)}
          aria-label={`${n} star${n > 1 ? "s" : ""}`}
        >
          ★
        </button>
      ))}
    </span>
  );
}

export function FavoriteButton({ place, onUpdate }: { place: Place; onUpdate: (u: VisitUpdate) => void }) {
  return (
    <button
      type="button"
      className={`fav-btn${place.favorite ? " on" : ""}`}
      onClick={(e) => {
        e.stopPropagation();
        onUpdate({ favorite: !place.favorite });
      }}
      aria-pressed={place.favorite}
      title={place.favorite ? "Remove from favorites" : "Add to favorites"}
    >
      {place.favorite ? "★" : "☆"}
    </button>
  );
}

/** "Been here" toggle, and once visited: date, rating and notes. Notes save when the box loses focus. */
export function VisitLog({ place, onUpdate }: { place: Place; onUpdate: (u: VisitUpdate) => Promise<void> }) {
  const [notes, setNotes] = useState(place.notes ?? "");
  const [saved, setSaved] = useState(false);
  useEffect(() => setNotes(place.notes ?? ""), [place.notes]);

  async function saveNotes() {
    if ((place.notes ?? "") === notes.trim()) return;
    await onUpdate({ notes: notes.trim() || null });
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  return (
    <div className="visit-log">
      <label className="visit-toggle">
        <input type="checkbox" checked={place.visited} onChange={(e) => onUpdate({ visited: e.target.checked })} />
        Been here
      </label>
      {place.visited && (
        <div className="visit-row">
          <StarInput value={place.rating} onChange={(rating) => onUpdate({ rating })} />
          <input
            type="date"
            className="visit-date"
            value={place.visited_date ?? ""}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => onUpdate({ visited_date: e.target.value || null })}
            aria-label="Date visited"
          />
        </div>
      )}
      <textarea
        className="visit-notes"
        rows={2}
        value={notes}
        placeholder={place.visited ? "What did you get? Worth it?" : "Notes (what to order, hours…)"}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={saveNotes}
        maxLength={2000}
      />
      {saved && <span className="saved">Saved</span>}
    </div>
  );
}
