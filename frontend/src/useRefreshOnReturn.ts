import { useEffect, useRef } from "react";

/**
 * Calls `refresh` when the app comes back on screen: switching back to the tab or the home-screen
 * app, unlocking the phone, or returning to a page restored from the back/forward cache. That's
 * how changes made on the other phone (or by a Muse upload) show up without a reload.
 *
 * One return can fire several of these events, so it runs at most once per `minGapMs`
 * (counted from the page load or the last refresh).
 */
export function useRefreshOnReturn(refresh: () => void, minGapMs = 5000) {
  const latest = useRef(refresh);
  latest.current = refresh;

  useEffect(() => {
    let last = Date.now();
    const onReturn = () => {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - last < minGapMs) return;
      last = Date.now();
      latest.current();
    };
    document.addEventListener("visibilitychange", onReturn);
    window.addEventListener("focus", onReturn);
    window.addEventListener("pageshow", onReturn);
    return () => {
      document.removeEventListener("visibilitychange", onReturn);
      window.removeEventListener("focus", onReturn);
      window.removeEventListener("pageshow", onReturn);
    };
  }, [minGapMs]);
}
