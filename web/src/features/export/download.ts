import { api, type ExportJob } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { showToast } from "../toast/toast";

export function volumeUrl(spaceId: string, exportId: string, number: number) {
  return `/api/v1/spaces/${spaceId}/exports/${exportId}/files/${number}`;
}

/** Descarga con el navegador (reanudable: el servidor admite Range). */
export function startDownload(url: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** «Descargar» sobre una selección: prepara un ZIP pequeño y lo descarga al terminar. */
export async function downloadSelection(
  spaceId: string,
  ids: string[],
  wait = (ms: number) => new Promise((r) => setTimeout(r, ms)),
) {
  try {
    let job: ExportJob = await api.createExport(spaceId, {
      ids,
      target: "zip",
      structure: "flat",
      naming: "normalized",
      include: "all",
      all_albums: false,
    });
    showToast(ids.length === 1 ? "Preparando la descarga…" : `Preparando ${ids.length} fotos en un ZIP…`);
    for (let i = 0; i < 600 && (job.state === "queued" || job.state === "running"); i++) {
      await wait(1000);
      job = await api.exportJob(spaceId, job.id);
    }
    if (job.state !== "ready") throw new Error(job.error ?? "La exportación no se pudo preparar");
    for (const file of job.files) startDownload(volumeUrl(spaceId, job.id, Number(file.number)));
  } catch (error) {
    showToast(errorMessage(error), { tone: "danger" });
  }
}
