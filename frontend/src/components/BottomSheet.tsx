import { useEffect, useRef, useState } from "react";

export type Snap = "peek" | "half" | "full";

/** Heights in px for each resting state, from the viewport and the space the top bar takes. */
export function snapHeights(viewport: number, topSpace: number) {
  return {
    peek: 84, // the handle and the summary row, nothing else
    half: Math.round(viewport * 0.52),
    full: Math.max(240, viewport - topSpace - 8),
  } satisfies Record<Snap, number>;
}

function useViewportHeight() {
  const [h, setH] = useState(() => window.innerHeight);
  useEffect(() => {
    const on = () => setH(window.innerHeight);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return h;
}

/**
 * The map's bottom sheet. It rests at peek (a summary row), half or full; drag its header to move it
 * (it snaps to the nearest rest, or in the direction of a quick flick), or tap the handle to open
 * and close it. The body scrolls on its own. Reports its current height so the map can keep pins
 * out from under it.
 */
export default function BottomSheet({
  snap,
  onSnap,
  topSpace,
  onHeight,
  header,
  children,
  label,
  view,
}: {
  view: string; // which content is showing; a new view starts scrolled to the top
  snap: Snap;
  onSnap: (s: Snap) => void;
  topSpace: number;
  onHeight?: (px: number) => void;
  header: React.ReactNode;
  children: React.ReactNode;
  label: string;
}) {
  const viewport = useViewportHeight();
  const heights = snapHeights(viewport, topSpace);
  const [drag, setDrag] = useState<number | null>(null); // live height while dragging
  const start = useRef<{ y: number; h: number; t: number; moved: boolean; id: number } | null>(null);
  const height = drag ?? heights[snap];
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {
    body.current?.scrollTo({ top: 0 });
  }, [view]);

  useEffect(() => {
    if (drag === null) onHeight?.(heights[snap]);
  }, [snap, heights.peek, heights.half, heights.full, drag]); // eslint-disable-line react-hooks/exhaustive-deps

  // Dragging: the move and release are followed on the whole window, since a mouse (unlike a
  // finger) leaves the header as soon as the sheet starts to move. Until the pointer has moved a
  // few pixels it's a tap, so buttons inside the header keep working; after a drag, the click
  // that would follow on whatever is under the pointer is swallowed.
  const swallowClick = useRef(false);
  function onPointerDown(e: React.PointerEvent) {
    if (e.button !== 0) return;
    const s = { y: e.clientY, h: heights[snap], t: performance.now(), moved: false, id: e.pointerId };
    start.current = s;
    let live: number | null = null;
    const samples: { y: number; t: number }[] = [{ y: e.clientY, t: performance.now() }];

    const move = (ev: PointerEvent) => {
      if (ev.pointerId !== s.id) return;
      const dy = s.y - ev.clientY;
      if (!s.moved && Math.abs(dy) < 6) return;
      s.moved = true;
      const now = performance.now();
      samples.push({ y: ev.clientY, t: now });
      while (samples.length > 2 && now - samples[0].t > 100) samples.shift();
      live = Math.min(heights.full, Math.max(heights.peek - 40, s.h + dy));
      setDrag(live);
    };
    const end = (ev: PointerEvent) => {
      if (ev.pointerId !== s.id) return;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      start.current = null;
      if (!s.moved || live === null) return;
      swallowClick.current = true;
      window.setTimeout(() => (swallowClick.current = false), 0);
      // Snap to the rest nearest where the sheet is heading: where it was let go, carried on by
      // the speed of the drag. A short flick moves one step; a long fast swipe goes all the way.
      // Speed at release (the last ~100 ms), so a drag that stops before letting go stays put.
      const now = performance.now();
      const first = samples.find((p) => now - p.t <= 100) ?? samples[samples.length - 1];
      const velocity = now - first.t > 0 ? (first.y - ev.clientY) / (now - first.t) : 0; // px/ms, up is positive
      const order: Snap[] = ["peek", "half", "full"];
      const heading = ev.type === "pointercancel" ? live : live + velocity * 220;
      let next = order.reduce((best, k) => (Math.abs(heights[k] - heading) < Math.abs(heights[best] - heading) ? k : best), "peek" as Snap);
      if (next === snap && Math.abs(velocity) > 0.6) {
        // A flick should always move: one step in its direction.
        const i = order.indexOf(snap);
        next = order[Math.min(2, Math.max(0, i + (velocity > 0 ? 1 : -1)))];
      }
      setDrag(null);
      onSnap(next);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  }

  return (
    <section
      className={`sheet${drag !== null ? " dragging" : ""}`}
      // The home-indicator strip on iPhones comes on top of each height, never out of it.
      style={{ height: `calc(${height}px + env(safe-area-inset-bottom))` }}
      aria-label={label}
      data-snap={snap}
    >
      <div
        className="sheet-head"
        onPointerDown={onPointerDown}
        onClickCapture={(e) => {
          if (swallowClick.current) {
            e.stopPropagation();
            e.preventDefault();
          }
        }}
      >
        <button
          type="button"
          className="sheet-handle"
          aria-label={snap === "peek" ? "Open the list" : "Close the list"}
          aria-expanded={snap !== "peek"}
          onClick={() => onSnap(snap === "peek" ? "half" : "peek")}
        >
          <span />
        </button>
        {header}
      </div>
      <div className="sheet-body" ref={body}>
        {children}
      </div>
    </section>
  );
}
