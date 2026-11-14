/** Acepta «40.4168, -3.7038» (lo que se copia de cualquier mapa). Devuelve null si no es válido. */
export function parseCoordinates(text: string): { lat: number; lon: number } | null {
  const parts = text
    .trim()
    .replace(/;/g, ",")
    .split(/[,\s]+/)
    .filter(Boolean)
    .map(Number);
  if (parts.length !== 2) return null;
  const [lat, lon] = parts as [number, number];
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180)
    return null;
  return { lat, lon };
}
