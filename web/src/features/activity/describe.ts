import type { Activity } from "../../api/client";

const n = (value: unknown) => (typeof value === "number" ? value : 0);
const s = (value: unknown) => (typeof value === "string" ? value : "");
const fotos = (count: number) => `${count} ${count === 1 ? "foto" : "fotos"}`;

/** Frase legible de cada acción: «Lucía subió 34 fotos». */
export function describe(entry: Activity): string {
  const who = entry.actor ?? "Alguien";
  const d = entry.detail;
  switch (entry.action) {
    case "asset.uploaded":
      return `${who} subió ${fotos(n(d.uploaded))}${n(d.duplicates) ? ` (${n(d.duplicates)} ya estaban)` : ""}`;
    case "asset.trashed":
      return `${who} envió ${fotos(n(d.count))} a la papelera`;
    case "asset.restored":
      return `${who} recuperó ${fotos(n(d.count))} de la papelera`;
    case "asset.purged":
      return `Se borraron definitivamente ${fotos(n(d.count))}`;
    case "asset.date_changed":
      return `${who} corrigió la fecha de ${fotos(n(d.count))}`;
    case "album.created":
      return `${who} creó el álbum «${s(d.name)}»`;
    case "album.renamed":
      return `${who} renombró un álbum`;
    case "album.deleted":
      return `${who} eliminó el álbum «${s(d.name)}»`;
    case "album.assets_added":
      return `${who} añadió ${fotos(n(d.count))} a «${s(d.album)}»`;
    case "duplicates.resolved":
      return `${who} resolvió repetidas (${n(d.trashed)} a la papelera)`;
    case "trash.emptied":
      return `${who} vació la papelera (${fotos(n(d.count))})`;
    case "invitation.accepted":
      return `${who} se unió al espacio`;
    case "space.created":
      return `${who} creó el espacio`;
    case "space.renamed":
      return `${who} renombró el espacio a «${s(d.to)}»`;
    case "export.created":
      return `${who} preparó una exportación`;
    default:
      return `${who}: ${entry.action}`;
  }
}
