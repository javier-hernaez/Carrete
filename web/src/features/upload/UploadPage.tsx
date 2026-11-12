import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { Link } from "react-router";

import { canEdit, useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { Alert, PageTitle } from "../../design-system/components/Card";
import { EmptyState } from "../../design-system/components/EmptyState";
import { Icon } from "../../design-system/components/Icon";
import { cx } from "../../design-system/cx";
import { filesFromDataTransfer, filesFromInput } from "./folders";
import { uploadQueue, type QueueItem } from "./queue";
import { FolderAlbums, Imports } from "./FolderAlbums";
import { useUploadQueue } from "./useUploadQueue";
import styles from "./upload.module.css";

const STATUS: Record<QueueItem["status"], string> = {
  waiting: "En cola",
  hashing: "Preparando",
  uploading: "Subiendo",
  done: "Subida",
  duplicate: "Ya estaba",
  error: "Error",
};

export function UploadPage() {
  const { space } = useSession();
  const queryClient = useQueryClient();
  const { items, running } = useUploadQueue();
  const [dragging, setDragging] = useState(false);
  const files = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);

  // Al terminar un lote, la línea temporal se refresca.
  useEffect(() => {
    if (!running && items.some((i) => i.status === "done"))
      void queryClient.invalidateQueries({ queryKey: ["assets"] });
  }, [running, items, queryClient]);

  if (!space)
    return <EmptyState title="Primero crea un espacio">Ve a «Más → Espacio y miembros».</EmptyState>;
  if (!canEdit(space))
    return (
      <EmptyState title="Solo puedes ver este espacio">
        Con el rol de lector no se pueden subir fotos.
      </EmptyState>
    );

  const add = (list: { file: File; relativePath: string | null }[]) => {
    uploadQueue.add(list, space.id);
  };
  const onDrop = async (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    add(await filesFromDataTransfer(e.dataTransfer));
  };

  const done = items.filter((i) => i.status === "done").length;
  const dup = items.filter((i) => i.status === "duplicate").length;
  const failed = items.filter((i) => i.status === "error").length;
  const total = items.length;

  return (
    <div>
      <PageTitle>Subir a «{space.name}»</PageTitle>
      {/* Soltar ficheros es un atajo de escritorio; los dos botones de dentro son el equivalente accesible. */}
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
      <div
        className={cx(styles.drop, dragging && styles.dragging)}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => void onDrop(e)}
      >
        <Icon name="upload" size={40} />
        <p className={styles.dropText}>Arrastra aquí fotos, vídeos o carpetas enteras</p>
        <p>También un .zip exportado de WhatsApp o de Google Fotos (Takeout): se importa con sus fechas.</p>
        <div className={styles.buttons}>
          <Button variant="primary" onClick={() => files.current?.click()}>
            Elegir fotos y vídeos
          </Button>
          <Button onClick={() => folder.current?.click()}>Elegir una carpeta</Button>
        </div>
        <input
          ref={files}
          type="file"
          multiple
          accept="image/*,video/*,.heic,.heif,.zip,application/zip"
          hidden
          aria-label="Elegir fotos y vídeos"
          onChange={(e) => {
            add(filesFromInput(e.target.files));
            e.target.value = "";
          }}
        />
        <input
          ref={folder}
          type="file"
          hidden
          aria-label="Elegir una carpeta"
          {...({ webkitdirectory: "" } as Record<string, string>)}
          onChange={(e) => {
            add(filesFromInput(e.target.files));
            e.target.value = "";
          }}
        />
      </div>

      <Imports spaceId={space.id} />
      {total > 0 && (
        <section aria-label="Cola de subida" className={styles.queue}>
          <div className={styles.summary} role="status" aria-live="polite">
            {running
              ? `Subiendo… ${done + dup} de ${total}`
              : `${done} subidas, ${dup} ya estaban, ${failed} errores`}
          </div>
          {!running && (
            <div className={styles.buttons}>
              {failed > 0 && (
                <Button onClick={() => uploadQueue.retryFailed()}>Reintentar los fallidos</Button>
              )}
              <Button variant="ghost" onClick={() => uploadQueue.clearFinished()}>
                Limpiar la lista
              </Button>
              {done > 0 && (
                <Link to="/revisar" className={styles.link}>
                  Revisar lo subido
                </Link>
              )}
            </div>
          )}
          {failed > 0 && !running && (
            <Alert tone="warning">Algunos ficheros no se pudieron subir. Mira el motivo en la lista.</Alert>
          )}
          {!running && <FolderAlbums spaceId={space.id} items={items} />}
          <ul className={styles.list}>
            {items.map((item) => (
              <li key={item.id} className={styles.item}>
                <div className={styles.itemName} title={item.relativePath ?? item.name}>
                  {item.name}
                </div>
                <div className={cx(styles.status, styles[item.status])}>
                  {item.error ?? STATUS[item.status]}
                </div>
                <progress
                  className={styles.progress}
                  max={1}
                  value={item.progress}
                  aria-label={`Progreso de ${item.name}`}
                />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
