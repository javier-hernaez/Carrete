import { Upload, type HttpResponse } from "tus-js-client";

import { api } from "../../api/client";
import { sha256File } from "./hash";

export type ItemStatus = "waiting" | "hashing" | "uploading" | "done" | "duplicate" | "error";

export interface QueueItem {
  id: number;
  file: File;
  name: string;
  relativePath: string | null;
  spaceId: string;
  albumId: string | null;
  status: ItemStatus;
  progress: number;
  sha256?: string | undefined;
  assetId?: string | undefined;
  error?: string | undefined;
}

export interface QueueSnapshot {
  items: QueueItem[];
  running: boolean;
}

const ACCEPTED = /^(image|video)\//;
const EXTENSIONS = /\.(jpe?g|png|webp|gif|heic|heif|avif|mp4|mov|3gp|3g2|webm|mkv|m4v)$/i;
const CHUNK = 16 * 1024 * 1024;
const PARALLEL_HASH = 2;
const PARALLEL_UPLOAD = 2;
const CHECK_BATCH = 500;

export function isMedia(file: File): boolean {
  return ACCEPTED.test(file.type) || EXTENSIONS.test(file.name);
}

/**
 * Cola de subida de la web. Vive fuera de React: sigue subiendo aunque cambies de pantalla.
 * hashing → (comprobación en lote: ¿ya estaba?) → subida tus → hecho.
 */
class UploadQueue {
  private items: QueueItem[] = [];
  private nextId = 1;
  private listeners = new Set<() => void>();
  private snapshot: QueueSnapshot = { items: [], running: false };
  private pumping = false;
  private finishedBatches = new Set<string>();

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = () => this.snapshot;

  private emit() {
    const running = this.items.some(
      (i) => i.status === "waiting" || i.status === "hashing" || i.status === "uploading",
    );
    this.snapshot = { items: [...this.items], running };
    this.listeners.forEach((l) => {
      l();
    });
  }

  private update(item: QueueItem, patch: Partial<QueueItem>) {
    Object.assign(item, patch);
    this.emit();
  }

  add(files: { file: File; relativePath?: string | null }[], spaceId: string, albumId: string | null = null) {
    for (const { file, relativePath } of files) {
      if (!isMedia(file)) continue;
      this.items.push({
        id: this.nextId++,
        file,
        name: file.name,
        relativePath: relativePath ?? null,
        spaceId,
        albumId,
        status: "waiting",
        progress: 0,
      });
    }
    this.emit();
    void this.pump();
  }

  clearFinished() {
    this.items = this.items.filter((i) => i.status !== "done" && i.status !== "duplicate");
    this.emit();
  }

  retryFailed() {
    for (const item of this.items)
      if (item.status === "error") Object.assign(item, { status: "waiting", progress: 0, error: undefined });
    this.emit();
    void this.pump();
  }

  private async pump() {
    if (this.pumping) return;
    this.pumping = true;
    try {
      // 1) Huellas, de dos en dos.
      await runPool(
        this.items.filter((i) => i.status === "waiting" && !i.sha256),
        PARALLEL_HASH,
        async (item) => {
          this.update(item, { status: "hashing", progress: 0 });
          try {
            const sha256 = await sha256File(item.file, (p) => {
              this.update(item, { progress: p * 0.1 });
            });
            this.update(item, { sha256, status: "waiting" });
          } catch {
            this.update(item, { status: "error", error: "No se pudo leer el fichero" });
          }
        },
      );
      // 2) ¿Cuáles ya están en el espacio? (deduplicación en origen)
      const pending = this.items.filter((i) => i.status === "waiting" && i.sha256);
      const bySpace = new Map<string, QueueItem[]>();
      for (const item of pending) bySpace.set(item.spaceId, [...(bySpace.get(item.spaceId) ?? []), item]);
      for (const [space, group] of bySpace) {
        for (let i = 0; i < group.length; i += CHECK_BATCH) {
          const batch = group.slice(i, i + CHECK_BATCH);
          try {
            const { present } = await api.checkHashes(
              space,
              batch.map((b) => b.sha256 ?? ""),
            );
            const set = new Set(present);
            for (const item of batch)
              if (item.sha256 && set.has(item.sha256))
                this.update(item, { status: "duplicate", progress: 1 });
          } catch {
            // Sin comprobación previa se sube igual: el servidor también deduplica.
          }
        }
      }
      // 3) Subida, de dos en dos.
      await runPool(
        this.items.filter((i) => i.status === "waiting" && i.sha256),
        PARALLEL_UPLOAD,
        (item) => this.upload(item),
      );
    } finally {
      this.pumping = false;
      this.reportFinishedSpaces();
      if (this.items.some((i) => i.status === "waiting")) void this.pump();
    }
  }

  private upload(item: QueueItem): Promise<void> {
    return new Promise((resolve) => {
      const metadata: Record<string, string> = {
        filename: item.name,
        sha256: item.sha256 ?? "",
        space_id: item.spaceId,
        mtime: String(item.file.lastModified || ""),
      };
      if (item.relativePath) metadata.relative_path = item.relativePath;
      if (item.albumId) metadata.album_id = item.albumId;
      this.update(item, { status: "uploading", progress: 0.1 });
      const upload = new Upload(item.file, {
        endpoint: "/api/v1/uploads",
        chunkSize: CHUNK,
        retryDelays: [0, 1000, 3000, 5000, 10000, 20000, 30000],
        metadata,
        headers: { "X-Carrete-Request": "1" },
        // Misma huella = mismo fichero en el mismo espacio: permite reanudar tras cerrar la pestaña.
        fingerprint: () => Promise.resolve(`carrete:${item.spaceId}:${item.sha256 ?? ""}`),
        removeFingerprintOnSuccess: true,
        onProgress: (sent, total) => {
          this.update(item, { progress: 0.1 + 0.9 * (total ? sent / total : 0) });
        },
        onShouldRetry: (error) => {
          const status = error.originalResponse?.getStatus() ?? 0;
          // Se reintenta lo pasajero (red, servidor reiniciándose, trozo dañado); no el disco lleno (507).
          return (
            status === 0 ||
            (status >= 500 && status !== 507) ||
            status === 409 ||
            status === 423 ||
            status === 460
          );
        },
        onSuccess: ({ lastResponse }: { lastResponse: HttpResponse }) => {
          const duplicate = lastResponse.getHeader("Carrete-Duplicate") === "1";
          this.update(item, {
            status: duplicate ? "duplicate" : "done",
            progress: 1,
            assetId: lastResponse.getHeader("Carrete-Asset-Id") ?? undefined,
          });
          resolve();
        },
        onError: (error) => {
          const response = (error as { originalResponse?: HttpResponse | null }).originalResponse;
          const status = response?.getStatus() ?? 0;
          if (status === 409 && response?.getBody().includes("duplicate")) {
            this.update(item, { status: "duplicate", progress: 1 });
          } else {
            this.update(item, {
              status: "error",
              error: problemDetail(response) ?? "Falló la subida; se puede reintentar",
            });
          }
          resolve();
        },
      });
      void upload.findPreviousUploads().then((previous) => {
        const last = previous[0];
        if (last) upload.resumeFromPreviousUpload(last);
        upload.start();
      });
    });
  }

  private reportFinishedSpaces() {
    if (this.items.some((i) => i.status === "waiting" || i.status === "hashing" || i.status === "uploading"))
      return;
    const spaces = new Set(this.items.map((i) => i.spaceId));
    for (const space of spaces) {
      const group = this.items.filter((i) => i.spaceId === space);
      const key = `${space}:${group.map((i) => i.id).join(",")}`;
      if (this.finishedBatches.has(key)) continue;
      this.finishedBatches.add(key);
      void api
        .uploadSummary(space, {
          uploaded: group.filter((i) => i.status === "done").length,
          duplicates: group.filter((i) => i.status === "duplicate").length,
          failed: group.filter((i) => i.status === "error").length,
        })
        .catch(() => undefined);
    }
  }
}

function problemDetail(response: HttpResponse | null | undefined): string | null {
  if (!response) return null;
  try {
    const body = JSON.parse(response.getBody()) as { detail?: string };
    return body.detail ?? null;
  } catch {
    return null;
  }
}

async function runPool<T>(items: T[], size: number, worker: (item: T) => Promise<void>) {
  let index = 0;
  const lanes = Array.from({ length: Math.min(size, items.length) }, async () => {
    while (index < items.length) {
      const item = items[index++];
      if (item !== undefined) await worker(item);
    }
  });
  await Promise.all(lanes);
}

export const uploadQueue = new UploadQueue();
