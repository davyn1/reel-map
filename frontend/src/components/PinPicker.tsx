import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, useMap, useMapEvents } from "react-leaflet";
import { StreetBasemap } from "../basemap";

const BAY_AREA_CENTER: [number, number] = [37.65, -122.2];

function ClickToPick({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) });
  return null;
}

/** Moves the map to a pin set from outside (typed coordinates, "use my location"). */
function FollowPin({ pin, nonce }: { pin: [number, number] | null; nonce: number }) {
  const map = useMap();
  useEffect(() => {
    if (pin && nonce) map.flyTo(pin, Math.max(map.getZoom(), 16), { duration: 0.5 });
  }, [map, nonce]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

/**
 * Small street map for placing a pin: tap the map, or use the phone's location.
 * Full street detail (unlike the stripped-down main map), since placing a pin needs streets.
 */
export default function PinPicker({
  pin,
  onPick,
}: {
  pin: [number, number] | null;
  onPick: (lat: number, lng: number) => void;
}) {
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);
  const [follow, setFollow] = useState(0);

  function useMyLocation() {
    if (!("geolocation" in navigator)) {
      setLocError("This browser can't share your location.");
      return;
    }
    setLocating(true);
    setLocError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        onPick(pos.coords.latitude, pos.coords.longitude);
        setFollow(Date.now());
      },
      (err) => {
        setLocating(false);
        setLocError(
          err.code === err.PERMISSION_DENIED
            ? "Location is blocked for this site. Allow it in the browser's site settings, or tap the map."
            : "Couldn't get your location. Tap the map instead.",
        );
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    );
  }

  return (
    <div className="pin-picker-wrap">
      <MapContainer center={pin ?? BAY_AREA_CENTER} zoom={pin ? 15 : 9} maxZoom={19} className="pin-picker">
        <StreetBasemap />
        <ClickToPick onPick={onPick} />
        <FollowPin pin={pin} nonce={follow} />
        {pin && (
          <CircleMarker center={pin} radius={8} pathOptions={{ color: "#fff", weight: 2, fillColor: "#2ec4a6", fillOpacity: 0.95 }} />
        )}
      </MapContainer>
      <div className="pin-picker-actions">
        <button type="button" onClick={useMyLocation} disabled={locating}>
          {locating ? "Finding you…" : "📍 Use my location"}
        </button>
        {locError && <span className="loc-error">{locError}</span>}
      </div>
    </div>
  );
}
