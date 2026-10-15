import { useCallback, useEffect, useState } from "react";
import { api, type Stats } from "./api";
import MapPage from "./pages/MapPage";
import ReviewPage from "./pages/ReviewPage";

type Route = "map" | "review";

function currentRoute(): Route {
  return window.location.hash === "#/review" ? "review" : "map";
}

export default function App() {
  const [route, setRoute] = useState<Route>(currentRoute);
  const [stats, setStats] = useState<Stats | null>(null);

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
  useEffect(refreshStats, [refreshStats]);

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
        <span className="icon-btn placeholder" />
      </header>
      {route === "map" ? (
        <MapPage stats={stats} onChanged={refreshStats} />
      ) : (
        <ReviewPage onQueueChange={refreshStats} />
      )}
    </div>
  );
}
