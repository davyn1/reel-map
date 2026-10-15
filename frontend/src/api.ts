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
  is_approximate: boolean;
  google_maps_url: string;
  visited: boolean;
  visited_date: string | null;
  reels: ReelBrief[];
}

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
  setVisited: (placeId: number, visited: boolean) =>
    request<Place>(`/api/places/${placeId}/visit`, {
      method: "POST",
      body: JSON.stringify({ visited }),
    }),
};
