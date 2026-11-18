import { useEffect, useRef, useState } from "react";
import type { FriendVisit, Place, VisitUpdate } from "../api";
import { CheckIcon, StarIcon } from "./Icons";

/** "★ 4" in gold: a compact rating for list rows and friend lines. */
export function Rating({ value }: { value: number | null }) {
  if (!value) return null;
  return (
    <span className="rating" aria-label={`rated ${value} out of 5`}>
      <StarIcon size={13} filled />
      {value}
    </span>
  );
}

/** Tap a star to rate; tap the current rating again to clear it. */
export function StarInput({ value, onChange }: { value: number | null; onChange: (v: number | null) => void }) {
  return (
    <span className="stars-input" role="group" aria-label="Rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          className={n <= (value ?? 0) ? "on" : ""}
          onClick={() => onChange(value === n ? null : n)}
          aria-label={`${n} star${n > 1 ? "s" : ""}`}
          aria-pressed={value === n}
        >
          <StarIcon size={24} filled={n <= (value ?? 0)} />
        </button>
      ))}
    </span>
  );
}

export function FavoriteButton({ place, onUpdate }: { place: Place; onUpdate: (u: VisitUpdate) => void }) {
  return (
    <button
      type="button"
      className={`icon-btn fav-btn${place.favorite ? " on" : ""}`}
      onClick={(e) => {
        e.stopPropagation();
        onUpdate({ favorite: !place.favorite });
      }}
      aria-pressed={place.favorite}
      aria-label={place.favorite ? "Want to go (tap to remove)" : "Want to go"}
      title={place.favorite ? "Remove from want to go" : "Want to go"}
    >
      <StarIcon size={22} filled={place.favorite} />
    </button>
  );
}

/** The big "Been here" toggle in the place view. Turning it on stamps today's date (server side). */
export function BeenButton({ place, onUpdate }: { place: Place; onUpdate: (u: VisitUpdate) => void }) {
  return (
    <button
      type="button"
      className={`been-btn${place.visited ? " on" : ""}`}
      aria-pressed={place.visited}
      onClick={() => onUpdate({ visited: !place.visited })}
    >
      <CheckIcon size={18} />
      {place.visited ? "Been here" : "Mark been here"}
    </button>
  );
}

/**
 * Once visited: rating and date. Always: notes, saved when the box loses focus and also when the
 * view closes mid-note (on a phone the sheet can close before the box ever blurs).
 */
export function VisitDetails({ place, onUpdate }: { place: Place; onUpdate: (u: VisitUpdate) => Promise<void> }) {
  const [notes, setNotes] = useState(place.notes ?? "");
  const [saved, setSaved] = useState(false);
  useEffect(() => setNotes(place.notes ?? ""), [place.notes]);

  // Latest values for the save-on-close below, without re-running it on every keystroke.
  const latest = useRef({ notes, stored: place.notes ?? "", onUpdate });
  latest.current = { notes, stored: place.notes ?? "", onUpdate };
  useEffect(
    () => () => {
      const { notes: n, stored, onUpdate: save } = latest.current;
      if (n.trim() !== stored) save({ notes: n.trim() || null });
    },
    [],
  );

  async function saveNotes() {
    if ((place.notes ?? "") === notes.trim()) return;
    await onUpdate({ notes: notes.trim() || null });
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  }

  return (
    <div className="visit-details">
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
      <label className="notes-field">
        <span className="field-label">
          Notes
          {saved && (
            <span className="saved" role="status">
              <CheckIcon size={14} /> Saved
            </span>
          )}
        </span>
        <textarea
          className="visit-notes"
          rows={2}
          value={notes}
          placeholder={place.visited ? "What did you get? Worth it?" : "What to order, hours…"}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={saveNotes}
          maxLength={2000}
        />
      </label>
    </div>
  );
}

/** "Sam wants to go · been, ★ 4 · “get the wings”" for each other person who logged this place. */
export function FriendLines({ others }: { others: FriendVisit[] }) {
  if (others.length === 0) return null;
  return (
    <div className="friend-lines">
      {others.map((o) => (
        <p key={o.username} className="friend-line">
          <b>{o.display_name}</b>{" "}
          {[o.favorite ? "wants to go" : null, o.visited ? "has been" : null].filter(Boolean).join(" · ")}
          {o.visited && o.rating ? (
            <>
              {" "}
              <Rating value={o.rating} />
            </>
          ) : null}
          {o.notes && <span className="friend-notes"> “{o.notes}”</span>}
        </p>
      ))}
    </div>
  );
}
