import { useQueryClient } from "@tanstack/react-query";
import { useState, type DragEvent } from "react";
import { NavLink } from "react-router";

import { api } from "../api/client";
import { cx } from "../design-system/cx";
import { useAssetActions } from "../features/photos/actions";
import { DRAG_TYPE } from "../features/photos/drag";
import { rememberAlbum, useAlbums } from "../features/selection/albums";
import { showToast } from "../features/toast/toast";
import { errorMessage } from "./errors";
import styles from "./AppShell.module.css";

function draggedIds(e: DragEvent): string[] | null {
  try {
    const raw = e.dataTransfer.getData(DRAG_TYPE);
    return raw ? (JSON.parse(raw) as string[]) : null;
  } catch {
    return null;
  }
}

/** Álbumes en la barra lateral (escritorio): se puede soltar encima una selección. */
export function SidebarAlbums({ spaceId, editor }: { spaceId: string; editor: boolean }) {
  const albums = useAlbums(spaceId);
  const actions = useAssetActions(spaceId);
  const queryClient = useQueryClient();
  const [over, setOver] = useState<string | null>(null);
  const accepts = (e: DragEvent) => editor && e.dataTransfer.types.includes(DRAG_TYPE);
  const dropProps = (key: string, onIds: (ids: string[]) => void) => ({
    onDragOver: (e: DragEvent) => {
      if (!accepts(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      setOver(key);
    },
    onDragLeave: () => setOver(null),
    onDrop: (e: DragEvent) => {
      setOver(null);
      const ids = draggedIds(e);
      if (!ids) return;
      e.preventDefault();
      onIds(ids);
    },
  });
  const list = (albums.data ?? []).slice(0, 30);
  return (
    <div className={styles.albums}>
      <h2 className={styles.albumsTitle}>Álbumes</h2>
      <ul className={styles.albumsList}>
        {list.map((album) => (
          <li key={album.id}>
            <NavLink
              to={`/albumes/${album.id}`}
              className={({ isActive }) =>
                cx(styles.albumLink, isActive && styles.active, over === album.id && styles.dropOver)
              }
              {...dropProps(album.id, (ids) => {
                rememberAlbum(spaceId, album.id);
                void actions.addToAlbum(ids, album.id, album.name);
              })}
            >
              <span className={styles.albumName}>{album.name}</span>
              <span className={styles.albumCount}>{album.count}</span>
            </NavLink>
          </li>
        ))}
        {editor && (
          <li>
            <div
              className={cx(styles.albumLink, styles.newAlbum, over === "new" && styles.dropOver)}
              {...dropProps("new", (ids) => {
                const name = window.prompt("Nombre del nuevo álbum");
                if (!name?.trim()) return;
                api
                  .createAlbum(spaceId, name, ids)
                  .then(async (album) => {
                    rememberAlbum(spaceId, album.id);
                    await queryClient.invalidateQueries({ queryKey: ["albums"] });
                    showToast(`Álbum «${album.name}» creado con ${ids.length} fotos`);
                  })
                  .catch((err: unknown) => showToast(errorMessage(err), { tone: "danger" }));
              })}
            >
              + Suelta aquí para un álbum nuevo
            </div>
          </li>
        )}
      </ul>
    </div>
  );
}
