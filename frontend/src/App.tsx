import { useCallback, useEffect, useState } from "react";
import { api, AUTH_REQUIRED_EVENT, type DemoInfo, type Me, type Stats } from "./api";
import AddPlacePage from "./pages/AddPlacePage";
import LoginPage from "./pages/LoginPage";
import MapPage from "./pages/MapPage";
import ReviewPage from "./pages/ReviewPage";

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

const TITLES: Record<Route, string> = { map: "Bay Area Yums Map", review: "Needs review", add: "Add a place" };

export default function App() {
  // undefined = still checking the login; null = logged out
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [route, setRoute] = useState<Route>(currentRoute);
  const [focusId, setFocusId] = useState<number | null>(focusFromHash);
  const [stats, setStats] = useState<Stats | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
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
  }, []);
  useEffect(() => {
    if (me) refreshStats();
  }, [me, refreshStats]);

  async function logout() {
    setMenuOpen(false);
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

  return (
    <div className="app">
      <header className="topbar">
        {route === "map" ? (
          <a className="icon-btn add-btn" href="#/add" aria-label="Add a place" title="Add a place">
            ＋
          </a>
        ) : (
          <a className="icon-btn" href="#/" aria-label="Back to map">
            ‹
          </a>
        )}
        <h1>{TITLES[route]}</h1>
        <div className="user-menu">
          <button
            className="icon-btn avatar"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label={`Account: ${me.display_name}`}
            aria-expanded={menuOpen}
          >
            {me.display_name.charAt(0).toUpperCase()}
          </button>
          {menuOpen && (
            <div className="menu" role="menu">
              <div className="menu-name">Logged in as {me.display_name}</div>
              <button role="menuitem" onClick={logout}>
                Log out
              </button>
            </div>
          )}
        </div>
      </header>
      {demo && (
        <p className="demo-banner">
          Demo · made-up places ·{" "}
          <a href={demo.source_url} target="_blank" rel="noreferrer">
            source code
          </a>
        </p>
      )}
      {route === "map" && (
        <MapPage
          key={me.username}
          stats={stats}
          onChanged={refreshStats}
          focusId={focusId}
          onFocused={() => {
            setFocusId(null);
            history.replaceState(null, "", "#/"); // so a refresh doesn't fly there again
          }}
        />
      )}
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
