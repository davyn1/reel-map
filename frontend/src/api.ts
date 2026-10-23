// Types mirror backend/app/schemas.py.

export interface ReelBrief {
  id: number;
  post_url: string;
  posted_by: string | null;
  dish: string | null;
  status: string;
  added_by: string | null; // display name, for places added by hand in the app
}

export interface FriendVisit {
  username: string;
  display_name: string;
  visited: boolean;
  rating: number | null;
  notes: string | null;
  favorite: boolean;
}

export interface ImportRun {
  at: string; // ISO time, UTC
  source: "upload" | "cli";
  filename: string | null;
  ok: boolean;
  error: string | null;
  imported: number;
  pinned: number;
  approximate: number;
  needs_review: number;
  skipped: number;
  merged: number;
}

export interface Me {
  username: string;
  display_name: string;
}

/** The public demo's login (GET /api/demo); that call fails on the real app. */
export interface DemoInfo {
  username: string;
  password: string;
  source_url: string;
}

/** A place added by hand (POST /api/places). */
export interface CreatePlace {
  name: string;
  lat: number;
  lng: number;
  address?: string | null;
  link?: string | null;
  is_approximate?: boolean;
  tags?: string[] | null;
  favorite?: boolean;
  visited?: boolean;
  notes?: string | null;
  force?: boolean;
}

/** An HTTP error with the server's `detail` kept as-is (string or object, e.g. 409 duplicate info). */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(`${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
}

/** Fired when the server says the login has expired or is missing; App shows the login screen. */
export const AUTH_REQUIRED_EVENT = "auth-required";

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
  tags_edited: boolean; // picked by hand rather than worked out from captions
  visited: boolean;
  visited_date: string | null; // YYYY-MM-DD
  rating: number | null; // 1-5
  notes: string | null;
  favorite: boolean;
  others: FriendVisit[]; // the other person's log for this place (friend mode)
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
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // not JSON; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  me: () => request<Me>("/api/auth/me"),
  login: (username: string, password: string) =>
    request<Me>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  demoInfo: () => request<DemoInfo>("/api/demo"),
  places: () => request<Place[]>("/api/places"),
  createPlace: (body: CreatePlace) => request<Place>("/api/places", { method: "POST", body: JSON.stringify(body) }),
  updateVisit: (placeId: number, update: VisitUpdate) =>
    request<Place>(`/api/places/${placeId}/visit`, {
      method: "POST",
      body: JSON.stringify(update),
    }),
  stats: () => request<Stats>("/api/stats"),
  recentImports: (limit = 1) => request<ImportRun[]>(`/api/imports?limit=${limit}`),
  tags: () => request<string[]>("/api/tags"),
  /** Pick a place's tags by hand, or pass null to go back to the automatic ones. */
  setTags: (placeId: number, tags: string[] | null) =>
    request<Place>(`/api/places/${placeId}/tags`, { method: "PUT", body: JSON.stringify({ tags }) }),
  flags: () => request<Record<string, string>>("/api/flags"),
  reviewQueue: () => request<ReviewReel[]>("/api/reels/review"),
  attachPlace: (reelId: number, body: AttachBody) =>
    request<ReviewReel>(`/api/reels/${reelId}/place`, { method: "POST", body: JSON.stringify(body) }),
  resolve: (reelId: number) => request<ReviewReel>(`/api/reels/${reelId}/resolve`, { method: "POST" }),
  reject: (reelId: number) => request<ReviewReel>(`/api/reels/${reelId}/reject`, { method: "POST" }),
};
