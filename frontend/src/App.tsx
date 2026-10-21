import { useCallback, useEffect, useState } from "react";
import { api, AUTH_REQUIRED_EVENT, type Me, type Stats } from "./api";
import LoginPage from "./pages/LoginPage";
import MapPage from "./pages/MapPage";
import ReviewPage from "./pages/ReviewPage";

type Route = "map" | "review";

function currentRoute(): Route {
  return window.location.hash === "#/review" ? "review" : "map";
}

export default function App() {
  // undefined = still checking the login; null = logged out
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [route, setRoute] = useState<Route>(currentRoute);
  const [stats, setStats] = useState<Stats | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
    // Any API call that comes back 401 (expired or revoked login) drops back to the login screen.
    const onAuthRequired = () => setMe(null);
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, []);

  useEffect(() => {
    const onHash = () => {
      setRoute(currentRoute());
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
        <LoginPage onLogin={setMe} />
      </div>
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        {route === "review" ? (
          <a className="icon-btn" href="#/" aria-label="Back to map">
            ‹
          </a>
        ) : (
          <span className="icon-btn placeholder" />
        )}
        <h1>{route === "review" ? "Needs review" : "Bay Area Yums Map"}</h1>
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
      {route === "map" ? (
        <MapPage key={me.username} stats={stats} onChanged={refreshStats} />
      ) : (
        <ReviewPage onQueueChange={refreshStats} />
      )}
    </div>
  );
}
