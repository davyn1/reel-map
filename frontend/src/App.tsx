import { useCallback, useEffect, useRef, useState } from "react";
import { api, AUTH_REQUIRED_EVENT, type DemoInfo, type ImportRun, type Me, type Stats } from "./api";
import { ChevronLeftIcon } from "./components/Icons";
import AddPlacePage from "./pages/AddPlacePage";
import LoginPage from "./pages/LoginPage";
import MapPage from "./pages/MapPage";
import ReviewPage from "./pages/ReviewPage";
import { useNewBuild, useOnDataChanged, useVersionPoller } from "./liveSync";

/** "New version · Reload": shown when the server has a newer build than this page is running, e.g. a
 * home-screen app resumed from the background after a deploy. The page itself is never cached
 * (main.FrontendFiles), so a reload always gets the new one. */
function UpdateNote() {
  const available = useNewBuild();
  if (!available) return null;
  return (
    <div className="update-note" role="status">
      <span>New version</span>
      <button type="button" className="link-btn" onClick={() => window.location.reload()}>
        Reload
      </button>
    </div>
  );
}

type Route = "map" | "review" | "add";

function currentRoute(): Route {
  const hash = window.location.hash;
  if (hash === "#/review") return "review";
  if (hash === "#/add") return "add";
  return "map";
}

/** "#/place/12" → 12: the map flies to that place (after adding one, or "Show it" on a duplicate). */
function focusFromHash(): number | null {
  const m = window.location.hash.match(/^#\/place\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

const TITLES: Record<Exclude<Route, "map">, string> = { review: "Sort out reels", add: "Add a place" };

/** "Nov 18, 9:02 PM · 3 new" or the failure, for the account menu. */
function importLine(run: ImportRun): string {
  const when = new Date(run.at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  if (!run.ok) return `Last import failed (${when}): ${run.error ?? "unknown error"}`;
  return `Last import ${when} · ${run.imported === 0 ? "nothing new" : `${run.imported} new`}`;
}

/** The avatar and its menu: who's logged in, the review queue, the last import, demo info, log out.
 * A dot on the avatar says something there wants attention (reels to sort out, a failed import). */
function AccountMenu({
  me,
  stats,
  lastImport,
  demo,
  onLogout,
}: {
  me: Me;
  stats: Stats | null;
  lastImport: ImportRun | null;
  demo: DemoInfo | null;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("pointerdown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);

  const review = stats?.needs_review ?? 0;
  const failed = lastImport ? !lastImport.ok : false;
  return (
    <div className="user-menu" ref={root}>
      <button
        type="button"
        className="icon-btn avatar"
        onClick={() => setOpen(!open)}
        aria-label={`Account: ${me.display_name}${review ? `, ${review} reels to sort out` : ""}`}
        aria-expanded={open}
      >
        {me.display_name.charAt(0).toUpperCase()}
        {(review > 0 || failed) && <span className={`avatar-dot${failed ? " failed" : ""}`} />}
      </button>
      {open && (
        <div className="menu" role="menu">
          <p className="menu-name">Logged in as {me.display_name}</p>
          {review > 0 && (
            <a role="menuitem" className="menu-item" href="#/review" onClick={() => setOpen(false)}>
              Sort out reels <span className="menu-count">{review}</span>
            </a>
          )}
          {lastImport && <p className={`menu-note${failed ? " failed" : ""}`}>{importLine(lastImport)}</p>}
          {demo && (
            <p className="menu-note">
              Demo with made-up places ·{" "}
              <a href={demo.source_url} target="_blank" rel="noreferrer">
                Source code
              </a>
            </p>
          )}
          <button type="button" role="menuitem" className="menu-item" onClick={onLogout}>
            Log out
          </button>
        </div>
      )}
    </div>
  );
}

export default function App() {
  // undefined = still checking the login; null = logged out
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [route, setRoute] = useState<Route>(currentRoute);
  const [focusId, setFocusId] = useState<number | null>(focusFromHash);
  const [stats, setStats] = useState<Stats | null>(null);
  const [lastImport, setLastImport] = useState<ImportRun | null>(null);
  const [demo, setDemo] = useState<DemoInfo | null>(null);

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
    api.demoInfo().then(setDemo).catch(() => setDemo(null)); // 404 on the real app
    // Any API call that comes back 401 (expired or revoked login) drops back to the login screen.
    const onAuthRequired = () => setMe(null);
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, []);

  useEffect(() => {
    const onHash = () => {
      setRoute(currentRoute());
      setFocusId(focusFromHash());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const refreshStats = useCallback(() => {
    api.stats().then(setStats).catch(() => setStats(null));
    api.recentImports(1).then((runs) => setLastImport(runs[0] ?? null)).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (me) refreshStats();
  }, [me, refreshStats]);
  // Live sync: one poller for the whole app; the counts and import status refresh when shared data changed.
  useVersionPoller(!!me);
  useOnDataChanged(() => {
    if (me) refreshStats();
  });

  async function logout() {
    await api.logout().catch(() => undefined);
    setMe(null);
    setStats(null);
  }

  if (me === undefined) return <div className="app" />;
  if (me === null) {
    return (
      <div className="app">
        <LoginPage onLogin={setMe} demo={demo} />
      </div>
    );
  }

  const account = <AccountMenu me={me} stats={stats} lastImport={lastImport} demo={demo} onLogout={logout} />;

  if (route === "map") {
    return (
      <>
        <UpdateNote />
        <MapPage
        key={me.username}
        stats={stats}
        onChanged={refreshStats}
        focusId={focusId}
        account={account}
        demo={!!demo}
        onFocused={() => {
          setFocusId(null);
          history.replaceState(null, "", "#/"); // so a refresh doesn't fly there again
        }}
        />
      </>
    );
  }

  return (
    <div className="app">
      <UpdateNote />
      <header className="topbar">
        <a className="icon-btn" href="#/" aria-label="Back to the map">
          <ChevronLeftIcon size={22} />
        </a>
        <h1>{TITLES[route]}</h1>
        {account}
      </header>
      {route === "review" && <ReviewPage onQueueChange={refreshStats} />}
      {route === "add" && (
        <AddPlacePage
          onAdded={(id) => {
            refreshStats();
            window.location.hash = `#/place/${id}`;
          }}
        />
      )}
    </div>
  );
}
