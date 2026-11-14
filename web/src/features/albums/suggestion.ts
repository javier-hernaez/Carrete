import type { Suggestion } from "../../api/client";

const dayMonth = new Intl.DateTimeFormat("es", { day: "numeric", month: "long" });
const monthYear = new Intl.DateTimeFormat("es", { month: "long", year: "numeric" });

export function suggestionKey(s: Suggestion): string {
  return `${s.start}|${String(s.count)}`;
}

/** «del 3 al 7 de octubre» o «del 30 de septiembre al 2 de octubre». */
export function suggestionRange(s: Suggestion): string {
  const start = new Date(s.start);
  const end = new Date(s.end);
  if (start.toDateString() === end.toDateString()) return `del ${dayMonth.format(start)}`;
  if (start.getMonth() === end.getMonth()) return `del ${String(start.getDate())} al ${dayMonth.format(end)}`;
  return `del ${dayMonth.format(start)} al ${dayMonth.format(end)}`;
}

export function suggestionName(s: Suggestion): string {
  const when = monthYear.format(new Date(s.start));
  return s.place ? `${s.place}, ${when}` : when.charAt(0).toUpperCase() + when.slice(1);
}
