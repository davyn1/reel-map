import { useEffect, useRef, useState } from "react";
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
export const NEW_BUILD_EVENT = "new-build";
export const POLL_MS = 10_000;

/** The app build this page is running: its main script, e.g. "assets/index-C9333xIF.js" (Vite names it
 * after its contents). None under the Vite dev server, which serves /src/main.tsx instead. */
export function runningBuild(): string | null {
  for (const s of document.querySelectorAll<HTMLScriptElement>("script[type=module][src]")) {
    const m = new URL(s.src, location.href).pathname.match(/assets\/index-[\w-]+\.js$/);
    if (m) return m[0];
  }
  return null;
}

/** Run once, in App, while logged in. */
export function useVersionPoller(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    let known: number | null = null; // the first answer is the baseline: the screens just loaded
    let busy = false; // one return fires several events; one request at a time is enough
    let stopped = false;
    const mine = runningBuild();
    let announced = false;

    async function check() {
      if (busy || document.visibilityState !== "visible") return;
      busy = true;
      try {
        const { version, build } = await api.version();
        if (stopped) return;
        if (known !== null && version !== known) window.dispatchEvent(new Event(DATA_CHANGED_EVENT));
        known = version;
        // A deploy happened while this page stayed open (or an app was resumed from the background):
        // offer a reload, once.
        if (!announced && build && mine && build !== mine) {
          announced = true;
          window.dispatchEvent(new Event(NEW_BUILD_EVENT));
        }
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

/** True once the server is handing out a newer build than the one running here. */
export function useNewBuild(): boolean {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    const on = () => setAvailable(true);
    window.addEventListener(NEW_BUILD_EVENT, on);
    return () => window.removeEventListener(NEW_BUILD_EVENT, on);
  }, []);
  return available;
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
