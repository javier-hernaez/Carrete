import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";

const RECENT_KEY = "carrete:albumes-recientes";

export function recentAlbums(spaceId: string): string[] {
  try {
    const all = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "{}") as Record<string, string[]>;
    return all[spaceId] ?? [];
  } catch {
    return [];
  }
}

export function rememberAlbum(spaceId: string, albumId: string) {
  try {
    const all = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "{}") as Record<string, string[]>;
    all[spaceId] = [albumId, ...(all[spaceId] ?? []).filter((id) => id !== albumId)].slice(0, 9);
    localStorage.setItem(RECENT_KEY, JSON.stringify(all));
  } catch {
    // Sin almacenamiento local: solo se pierde la lista de recientes.
  }
}

/** Álbumes por recientes primero (para los atajos 1–9 de Revisar). */
export function useAlbums(spaceId: string) {
  const query = useQuery({ queryKey: ["albums", spaceId], queryFn: () => api.albums(spaceId) });
  const recent = recentAlbums(spaceId);
  const sorted = [...(query.data ?? [])].sort((a, b) => {
    const ra = recent.indexOf(a.id);
    const rb = recent.indexOf(b.id);
    return (ra === -1 ? 99 : ra) - (rb === -1 ? 99 : rb);
  });
  return { ...query, sorted };
}
