/** Filtros de la línea temporal, guardados en la URL para que «atrás» y los enlaces funcionen. */

export interface PhotoFilters {
  estado: "" | "pendiente" | "vale" | "descartada" | "todas";
  fav: boolean;
  tipo: "" | "photo" | "video";
  origen: "" | "camera" | "whatsapp" | "screenshot" | "other";
  persona: string;
  de: string;
  a: string;
  dudosa: boolean;
  album: string;
  sinAlbum: boolean;
  q: string;
  zona: string; // «sur,oeste,norte,este», desde el mapa
}

export function readFilters(params: URLSearchParams): PhotoFilters {
  return {
    estado: (params.get("estado") ?? "") as PhotoFilters["estado"],
    fav: params.get("fav") === "1",
    tipo: (params.get("tipo") ?? "") as PhotoFilters["tipo"],
    origen: (params.get("origen") ?? "") as PhotoFilters["origen"],
    persona: params.get("persona") ?? "",
    de: params.get("de") ?? "",
    a: params.get("a") ?? "",
    dudosa: params.get("dudosa") === "1",
    album: params.get("album") ?? "",
    sinAlbum: params.get("sin-album") === "1",
    q: params.get("q") ?? "",
    zona: params.get("zona") ?? "",
  };
}

const REVIEW: Record<string, string[]> = {
  pendiente: ["pending"],
  vale: ["kept"],
  descartada: ["discarded"],
  todas: ["pending", "kept", "discarded"],
};

/** Parámetros de la API a partir de los filtros. */
export function toApiParams(f: PhotoFilters, extra: Record<string, string> = {}): URLSearchParams {
  const p = new URLSearchParams(extra);
  for (const r of REVIEW[f.estado] ?? []) p.append("review", r);
  if (f.fav) p.set("favorite", "true");
  if (f.tipo) p.set("kind", f.tipo);
  if (f.origen) p.set("source", f.origen);
  if (f.persona) p.set("uploaded_by", f.persona);
  if (f.de) p.set("date_from", f.de);
  if (f.a) p.set("date_to", f.a);
  if (f.dudosa) p.set("doubtful", "true");
  if (f.album) p.set("album_id", f.album);
  if (f.sinAlbum) p.set("no_album", "true");
  if (f.q) p.set("q", f.q);
  const zone = f.zona.split(",").map(Number);
  if (zone.length === 4 && zone.every((n) => Number.isFinite(n))) {
    const [south, west, north, east] = zone as [number, number, number, number];
    p.set("south", String(south));
    p.set("west", String(west));
    p.set("north", String(north));
    p.set("east", String(east));
  }
  return p;
}

export function activeCount(f: PhotoFilters): number {
  return [
    f.estado,
    f.fav,
    f.tipo,
    f.origen,
    f.persona,
    f.de || f.a,
    f.dudosa,
    f.album,
    f.sinAlbum,
    f.q,
    f.zona,
  ].filter(Boolean).length;
}
