import { useEffect, useState } from "react";
import type { Place } from "../api";

/** Shows a place's food tags; "Edit" switches to toggles for every tag. */
export function TagEditor({
  place,
  allTags,
  onSave,
}: {
  place: Place;
  allTags: string[];
  onSave: (tags: string[] | null) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [picked, setPicked] = useState<string[]>(place.tags);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!editing) setPicked(place.tags);
  }, [place.tags, editing]);

  async function save(tags: string[] | null) {
    setBusy(true);
    try {
      await onSave(tags);
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <div className="tag-line">
        <span>{place.tags.length ? place.tags.join(", ") : "No food type yet"}</span>
        {place.tags_edited && <span className="muted">(picked by hand)</span>}
        <button type="button" className="link-btn" onClick={() => setEditing(true)} disabled={allTags.length === 0}>
          Edit
        </button>
      </div>
    );
  }

  const changed = picked.length !== place.tags.length || picked.some((t) => !place.tags.includes(t));
  return (
    <div className="tag-editor">
      <div className="tag-options">
        {allTags.map((t) => (
          <button
            key={t}
            type="button"
            className={`chip${picked.includes(t) ? " on" : ""}`}
            aria-pressed={picked.includes(t)}
            onClick={() => setPicked(picked.includes(t) ? picked.filter((x) => x !== t) : [...picked, t])}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="tag-editor-actions">
        <button type="button" className="primary" disabled={busy || !changed} onClick={() => save(picked)}>
          Save
        </button>
        <button type="button" disabled={busy} onClick={() => setEditing(false)}>
          Cancel
        </button>
        {place.tags_edited && (
          <button type="button" className="link-btn" disabled={busy} onClick={() => save(null)}>
            Back to automatic
          </button>
        )}
      </div>
    </div>
  );
}
