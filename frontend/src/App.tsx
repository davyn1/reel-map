import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import MapPage from "./pages/MapPage";
import ReviewPage from "./pages/ReviewPage";

type Route = "map" | "review";

function currentRoute(): Route {
  return window.location.hash === "#/review" ? "review" : "map";
}

export default function App() {
  const [route, setRoute] = useState<Route>(currentRoute);
  const [reviewCount, setReviewCount] = useState<number | null>(null);

  useEffect(() => {
    const onHash = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const refreshCount = useCallback(() => {
    api.reviewQueue().then((q) => setReviewCount(q.length)).catch(() => setReviewCount(null));
  }, []);
  useEffect(refreshCount, [refreshCount]);

  return (
    <div className="app">
      <nav className="topbar">
        <span className="title">Food Map</span>
        <a href="#/" className={route === "map" ? "active" : ""}>
          Map
        </a>
        <a href="#/review" className={route === "review" ? "active" : ""}>
          Review{reviewCount ? <span className="badge">{reviewCount}</span> : null}
        </a>
      </nav>
      {route === "map" ? <MapPage /> : <ReviewPage onQueueChange={refreshCount} />}
    </div>
  );
}
