/** Fechas «de pared»: la hora de la captura tal cual, sin convertir a la zona del navegador. */

const MONTHS = [
  "enero",
  "febrero",
  "marzo",
  "abril",
  "mayo",
  "junio",
  "julio",
  "agosto",
  "septiembre",
  "octubre",
  "noviembre",
  "diciembre",
];
const DAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

export function dayKey(takenAt: string): string {
  return takenAt.slice(0, 10);
}

export function formatDay(key: string): string {
  const [y, m, d] = key.split("-").map(Number) as [number, number, number];
  const weekday = DAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] ?? "";
  const thisYear = new Date().getFullYear();
  return `${weekday}, ${d} de ${MONTHS[m - 1] ?? ""}${y === thisYear ? "" : ` de ${y}`}`;
}

export function formatMonth(year: number, month: number): string {
  return `${MONTHS[month - 1] ?? ""} ${year}`;
}

export function formatDateTime(takenAt: string, offsetMinutes: number | null): string {
  const key = dayKey(takenAt);
  const time = takenAt.slice(11, 16);
  let zone = "";
  if (offsetMinutes !== null) {
    const sign = offsetMinutes >= 0 ? "+" : "−";
    const abs = Math.abs(offsetMinutes);
    zone = ` (UTC${sign}${Math.floor(abs / 60)}${abs % 60 ? `:${String(abs % 60).padStart(2, "0")}` : ""})`;
  }
  return `${formatDay(key)}, ${time}${zone}`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (!ms) return "";
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m >= 60
    ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}

export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit++;
  }
  return `${value.toLocaleString("es", { maximumFractionDigits: unit ? 1 : 0 })} ${units[unit] ?? ""}`;
}

export const SOURCE_LABEL: Record<string, string> = {
  camera: "Cámara",
  whatsapp: "WhatsApp",
  screenshot: "Captura de pantalla",
  other: "Otro",
};
