import L from "leaflet";
import type { Place } from "./api";

// Pins sharing exact coordinates (e.g. pop-ups pinned to a city centre) are fanned out
// around the shared point by this many degrees so each one is clickable.
const SPREAD_DEG = 0.0015;

export interface Pin {
  place: Place;
  number: number;
  position: [number, number];
}

export function spreadOverlaps(items: { place: Place; number: number }[]): Pin[] {
  const groups = new Map<string, { place: Place; number: number }[]>();
  for (const item of items) {
    const key = `${item.place.lat.toFixed(5)},${item.place.lng.toFixed(5)}`;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  const pins: Pin[] = [];
  for (const group of groups.values()) {
    group.forEach(({ place, number }, i) => {
      if (group.length === 1) {
        pins.push({ place, number, position: [place.lat, place.lng] });
        return;
      }
      const angle = (2 * Math.PI * i) / group.length;
      const dLat = SPREAD_DEG * Math.sin(angle);
      const dLng = (SPREAD_DEG * Math.cos(angle)) / Math.cos((place.lat * Math.PI) / 180);
      pins.push({ place, number, position: [place.lat + dLat, place.lng + dLng] });
    });
  }
  return pins;
}

export function pinClasses(place: Place): string {
  return [place.visited ? "visited" : "todo", place.is_approximate ? "approx" : ""].join(" ").trim();
}

const iconCache = new Map<string, L.DivIcon>();

/** Numbered teardrop pin. Cached so re-renders don't rebuild every marker's DOM. */
export function pinIcon(number: number, place: Place, selected: boolean): L.DivIcon {
  const classes = `pin ${pinClasses(place)}${selected ? " selected" : ""}`;
  const key = `${number}|${classes}`;
  let icon = iconCache.get(key);
  if (!icon) {
    icon = L.divIcon({
      className: "pin-icon",
      html: `<div class="${classes}"><span>${number}</span></div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 39], // the tip sits ~7px below the rotated square
      popupAnchor: [0, -36],
    });
    iconCache.set(key, icon);
  }
  return icon;
}

/** Caption snippet without hashtags and pin emoji, for the list cards. */
export function cleanCaption(dish: string | null): string | null {
  if (!dish) return null;
  const text = dish
    .replace(/#[\p{L}\p{N}_]+/gu, "")
    .replace(/📍/gu, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return null;
  // Some posters caption in ALL CAPS; show those in sentence case like the rest.
  const letters = text.replace(/[^\p{L}]/gu, "");
  const upper = letters.replace(/[^\p{Lu}]/gu, "");
  if (letters.length > 10 && upper.length / letters.length > 0.6) {
    const lower = text.toLowerCase();
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }
  return text;
}
