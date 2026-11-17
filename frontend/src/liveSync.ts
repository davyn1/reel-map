import { useEffect, useRef } from "react";
import { api } from "./api";

/**
 * Live sync. The server keeps a number that goes up whenever shared data changes
 * (`GET /api/version`, backend/app/sync.py). `useVersionPoller` asks for it every POLL_MS while the
 * app is on screen, and right away when it comes back (switching back to it, unlocking the phone).
 * When the number moved, it fires DATA_CHANGED_EVENT, and each screen re-fetches what it shows
 * (`useOnDataChanged`). So the other phone's changes and Muse's uploads show up within ~10 s while
 * the map is open, and nothing is fetched while the phone is locked or the app is in the background.
 */
export const DATA_CHANGED_EVENT = "data-changed";
export const POLL_MS = 10_000;

/** Run once, in App, while logged in. */
export function useVersionPoller(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    let known: number | null = null; // the first answer is the baseline: the screens just loaded
    let busy = false; // one return fires several events; one request at a time is enough
    let stopped = false;

    async function check() {
      if (busy || document.visibilityState !== "visible") return;
      busy = true;
      try {
        const { version } = await api.version();
        if (stopped) return;
        if (known !== null && version !== known) window.dispatchEvent(new Event(DATA_CHANGED_EVENT));
        known = version;
      } catch {
        // offline, or the server is waking up: try again on the next tick
      } finally {
        busy = false;
      }
    }

    check();
    const timer = window.setInterval(check, POLL_MS);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check);
    window.addEventListener("pageshow", check);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("focus", check);
      window.removeEventListener("pageshow", check);
    };
  }, [enabled]);
}

/** Calls `onChange` whenever shared data changed (see useVersionPoller). */
export function useOnDataChanged(onChange: () => void) {
  const latest = useRef(onChange);
  latest.current = onChange;
  useEffect(() => {
    const handler = () => latest.current();
    window.addEventListener(DATA_CHANGED_EVENT, handler);
    return () => window.removeEventListener(DATA_CHANGED_EVENT, handler);
  }, []);
}
