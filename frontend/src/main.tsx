import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "leaflet/dist/leaflet.css";
import "./index.css";
import MapPage from "./pages/MapPage";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MapPage />
  </StrictMode>,
);
