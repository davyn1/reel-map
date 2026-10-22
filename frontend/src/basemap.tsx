// A stripped-down dark vector basemap: land, water, freeways and main highways (with route
// shields), and city/town names. Built from OpenFreeMap's free "Positron" style (no API key)
// by keeping only the layers below. Falls back to plain OSM raster tiles if it can't load.

import { useEffect, useState } from "react";
import { TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "maplibre-gl/dist/maplibre-gl.css";
import "@maplibre/maplibre-gl-leaflet";
import type { LayerSpecification, StyleSpecification } from "maplibre-gl";

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank">OpenFreeMap</a> ' +
  '<a href="https://www.openmaptiles.org/" target="_blank">&copy; OpenMapTiles</a> ' +
  'Data from <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>';

const KEEP = new Set([
  "background",
  "water",
  // freeways (motorway class), including bridges and tunnels
  "highway_motorway_subtle",
  "tunnel_motorway_casing",
  "tunnel_motorway_inner",
  "highway_motorway_casing",
  "highway_motorway_inner",
  "highway_motorway_bridge_casing",
  "highway_motorway_bridge_inner",
  // route shields: I-880, US-101, CA-24 ...
  "highway-shield-us-interstate",
  "road_shield_us",
  // names
  "water_name_point_label",
  "label_town",
  "label_city",
  "label_city_capital",
]);

// Dark palette: slate land, blue bay, quiet grey roads, bold white city names.
const PALETTE = {
  land: "#3a4047",
  water: "#2c4d85",
  waterLabel: "#9fb6dc",
  freewayCasing: "#2f343a",
  freeway: "#69727d",
  trunk: "#545c66", // trunk roads (expressways like CA-1, CA-24 segments)
  cityText: "#ffffff",
  townText: "#d5d9de",
  textHalo: "rgba(20, 22, 26, 0.85)",
};

// Earlier minzooms than Positron's defaults, so shields show at the whole-Bay-Area view.
const MINZOOM: Record<string, number> = {
  "highway-shield-us-interstate": 8,
  road_shield_us: 9,
  label_town: 8,
};

type Tunable = LayerSpecification & { paint?: Record<string, unknown>; layout?: Record<string, unknown> };

function tune(layer: LayerSpecification): LayerSpecification {
  const out = { ...layer } as Tunable;
  const paint = (extra: Record<string, unknown>) => (out.paint = { ...out.paint, ...extra });
  if (MINZOOM[layer.id] !== undefined) out.minzoom = MINZOOM[layer.id];

  if (layer.id === "background") paint({ "background-color": PALETTE.land });
  if (layer.id === "water") paint({ "fill-color": PALETTE.water });
  if (layer.id === "water_name_point_label")
    paint({ "text-color": PALETTE.waterLabel, "text-halo-color": "rgba(0,0,0,0)" });

  if (layer.id.includes("motorway")) {
    if (layer.id.endsWith("casing")) paint({ "line-color": PALETTE.freewayCasing });
    else paint({ "line-color": PALETTE.freeway });
  }

  if (layer.id.startsWith("label_city")) {
    paint({ "text-color": PALETTE.cityText, "text-halo-color": PALETTE.textHalo, "text-halo-width": 1.5 });
    out.layout = { ...out.layout, "text-size": ["interpolate", ["linear"], ["zoom"], 7, 13, 10, 18, 13, 24] };
  }
  if (layer.id === "label_town") {
    paint({ "text-color": PALETTE.townText, "text-halo-color": PALETTE.textHalo, "text-halo-width": 1.5 });
    out.layout = { ...out.layout, "text-size": ["interpolate", ["linear"], ["zoom"], 8, 12, 12, 17] };
  }
  return out;
}

// Trunk roads aren't in Positron's freeway layers; draw them as thin plain lines under the freeways.
const TRUNK_LAYER: LayerSpecification = {
  id: "trunk",
  type: "line",
  source: "openmaptiles",
  "source-layer": "transportation",
  minzoom: 8,
  filter: ["all", ["==", ["get", "class"], "trunk"], ["!=", ["get", "brunnel"], "tunnel"]],
  layout: { "line-cap": "round", "line-join": "round" },
  paint: { "line-color": PALETTE.trunk, "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 8, 0.8, 12, 2, 16, 6] },
};

export async function minimalStyle(): Promise<StyleSpecification> {
  const res = await fetch(STYLE_URL);
  if (!res.ok) throw new Error(`basemap style: HTTP ${res.status}`);
  const style = (await res.json()) as StyleSpecification;
  const layers = style.layers.filter((l) => KEEP.has(l.id)).map(tune);
  const firstFreeway = layers.findIndex((l) => l.id.includes("motorway"));
  layers.splice(firstFreeway === -1 ? layers.length : firstFreeway, 0, TRUNK_LAYER);
  return { ...style, layers };
}

let stylePromise: Promise<StyleSpecification> | null = null;

function VectorLayer({ style }: { style: StyleSpecification }) {
  const map = useMap();
  useEffect(() => {
    const layer = L.maplibreGL({ style, attributionControl: false });
    layer.addTo(map);
    map.attributionControl?.addAttribution(ATTRIBUTION);
    return () => {
      map.attributionControl?.removeAttribution(ATTRIBUTION);
      layer.remove();
    };
  }, [map, style]);
  return null;
}

export function MinimalBasemap() {
  const [style, setStyle] = useState<StyleSpecification | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    stylePromise ??= minimalStyle();
    stylePromise.then(setStyle).catch((e) => {
      console.warn("Falling back to OSM raster tiles:", e);
      stylePromise = null;
      setFailed(true);
    });
  }, []);

  if (failed) {
    return (
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
    );
  }
  return style ? <VectorLayer style={style} /> : null;
}

const STREET_STYLE_URL = "https://tiles.openfreemap.org/styles/dark";
let streetStylePromise: Promise<StyleSpecification> | null = null;

/**
 * Full-detail dark street map (OpenFreeMap "dark", no API key) for placing pins, where streets
 * and labels matter. Same OSM raster fallback as the main map.
 */
export function StreetBasemap() {
  const [style, setStyle] = useState<StyleSpecification | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    streetStylePromise ??= fetch(STREET_STYLE_URL).then((r) => {
      if (!r.ok) throw new Error(`street style: HTTP ${r.status}`);
      return r.json() as Promise<StyleSpecification>;
    });
    streetStylePromise.then(setStyle).catch((e) => {
      console.warn("Falling back to OSM raster tiles:", e);
      streetStylePromise = null;
      setFailed(true);
    });
  }, []);

  if (failed) {
    return (
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
    );
  }
  return style ? <VectorLayer style={style} /> : null;
}
