import { dayKey, formatDay } from "../photos/format";

export function albumRange(first: string | null, last: string | null): string {
  if (!first || !last) return "";
  const a = formatDay(dayKey(first)).replace(/^[^,]+, /, "");
  const b = formatDay(dayKey(last)).replace(/^[^,]+, /, "");
  return a === b ? a : `${a} – ${b}`;
}
