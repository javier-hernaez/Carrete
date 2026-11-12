import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { Alert } from "../../design-system/components/Card";
import { showToast } from "../toast/toast";
import type { QueueItem } from "./queue";
import styles from "./upload.module.css";

/** Al subir carpetas, propone un álbum con el nombre de cada carpeta. */
export function FolderAlbums({ spaceId, items }: { spaceId: string; items: QueueItem[] }) {
  const queryClient = useQueryClient();
  const [created, setCreated] = useState<string[]>([]);
  const groups = new Map<string, string[]>();
  for (const item of items) {
    const folder = item.relativePath?.split("/")[0];
    if (folder && item.assetId && (item.status === "done" || item.status === "duplicate"))
      groups.set(folder, [...(groups.get(folder) ?? []), item.assetId]);
  }
  const create = useMutation({
    mutationFn: ({ name, ids }: { name: string; ids: string[] }) => api.createAlbum(spaceId, name, ids),
    onSuccess: async (album, { name }) => {
      setCreated((c) => [...c, name]);
      await queryClient.invalidateQueries({ queryKey: ["albums"] });
      showToast(`Álbum «${album.name}» creado con ${album.count} fotos`);
    },
  });
  const pending = [...groups.entries()].filter(([name]) => !created.includes(name));
  if (pending.length === 0) return null;
  return (
    <Alert>
      <div className={styles.buttons}>
        {pending.map(([name, ids]) => (
          <Button key={name} onClick={() => create.mutate({ name, ids })}>
            Crear el álbum «{name}» con {ids.length} fotos
          </Button>
        ))}
      </div>
    </Alert>
  );
}

/** Importaciones de ZIP en curso o recientes. */
export function Imports({ spaceId }: { spaceId: string }) {
  const imports = useQuery({
    queryKey: ["imports", spaceId],
    queryFn: () => api.imports(spaceId),
    refetchInterval: (q) =>
      q.state.data?.some((i) => i.state === "queued" || i.state === "running") ? 3000 : 15000,
  });
  const recent = (imports.data ?? []).slice(0, 5);
  if (recent.length === 0) return null;
  return (
    <section aria-label="Importaciones" className={styles.queue}>
      <h2 className={styles.summary}>Importaciones de ZIP</h2>
      <ul className={styles.list}>
        {recent.map((i) => (
          <li key={i.id} className={styles.item}>
            <div className={styles.itemName}>{i.name}</div>
            <div className={styles.status}>
              {i.state === "done"
                ? `${Number(i.counts.imported ?? 0)} importadas, ${Number(i.counts.duplicates ?? 0)} ya estaban, ${Number(i.counts.unsupported ?? 0) + Number(i.counts.suspicious ?? 0) + Number(i.counts.skipped ?? 0)} descartadas`
                : i.state === "failed"
                  ? `Falló: ${i.error ?? ""}`
                  : "Importando…"}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
