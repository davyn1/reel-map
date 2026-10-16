// Types mirror backend/app/schemas.py.

export interface ReelBrief {
  id: number;
  post_url: string;
  posted_by: string | null;
  dish: string | null;
  status: string;
}

export interface Place {
  id: number;
  name: string;
  lat: number;
  lng: number;
  address: string | null;
  city: string | null;
  is_approximate: boolean;
  google_maps_url: string;
  tags: string[];
  visited: boolean;
  visited_date: string | null; // YYYY-MM-DD
  rating: number | null; // 1-5
  notes: string | null;
  favorite: boolean;
  reels: ReelBrief[];
}

export interface Stats {
  reels_saved: number;
  on_map: number;
  cities: number;
  needs_review: number;
  visited: number;
  favorites: number;
}

/** Partial visit-log update: only the fields given change; null clears rating/notes/date. */
export interface VisitUpdate {
  visited?: boolean;
  visited_date?: string | null;
  rating?: number | null;
  notes?: string | null;
  favorite?: boolean;
}

export interface PlaceBrief {
  id: number;
  name: string;
  address: string | null;
  is_approximate: boolean;
}

export interface ReviewReel {
  id: number;
  post_url: string;
  posted_by: string | null;
  venue_raw: string | null;
  address_raw: string | null;
  city_raw: string | null;
  lat_raw: number | null;
  lng_raw: number | null;
  dish: string | null;
  muse_confidence: string | null;
  muse_note: string | null;
  status: string;
  flags: string[];
  review_reason: string | null;
  place: PlaceBrief | null;
  extra_places: PlaceBrief[];
}

export interface NewPlace {
  name: string;
  lat: number;
  lng: number;
  address?: string | null;
  is_approximate?: boolean;
}

export type AttachBody = ({ place_id: number } | { new_place: NewPlace }) & { mode?: "replace" | "add" };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // not JSON; keep statusText
    }
    throw new Error(`${res.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  return res.json();
}

export const api = {
  places: () => request<Place[]>("/api/places"),
  updateVisit: (placeId: number, update: VisitUpdate) =>
    request<Place>(`/api/places/${placeId}/visit`, {
      method: "POST",
      body: JSON.stringify(update),
    }),
  stats: () => request<Stats>("/api/stats"),
  flags: () => request<Record<string, string>>("/api/flags"),
  reviewQueue: () => request<ReviewReel[]>("/api/reels/review"),
  attachPlace: (reelId: number, body: AttachBody) =>
    request<ReviewReel>(`/api/reels/${reelId}/place`, { method: "POST", body: JSON.stringify(body) }),
  resolve: (reelId: number) => request<ReviewReel>(`/api/reels/${reelId}/resolve`, { method: "POST" }),
  reject: (reelId: number) => request<ReviewReel>(`/api/reels/${reelId}/reject`, { method: "POST" }),
};
