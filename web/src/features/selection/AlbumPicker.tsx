import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type Album } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { Button } from "../../design-system/components/Button";
import { Dialog } from "../../design-system/components/Dialog";
import { TextField } from "../../design-system/components/Field";
import { rememberAlbum, useAlbums } from "./albums";
import styles from "./selection.module.css";

/** Elegir álbum (o crear uno nuevo) para la selección. */
export function AlbumPicker({
  spaceId,
  count,
  onPick,
  onClose,
}: {
  spaceId: string;
  count: number;
  onPick: (album: Album) => void;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const albums = useAlbums(spaceId);
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => api.createAlbum(spaceId, name),
    onSuccess: async (album) => {
      await queryClient.invalidateQueries({ queryKey: ["albums", spaceId] });
      pick(album);
    },
  });
  const pick = (album: Album) => {
    rememberAlbum(spaceId, album.id);
    onPick(album);
  };
  return (
    <Dialog title={count === 1 ? "Añadir a un álbum" : `Añadir ${count} a un álbum`} onClose={onClose}>
      <ul className={styles.albumList}>
        {albums.sorted.map((album, i) => (
          <li key={album.id}>
            <button type="button" className={styles.albumButton} onClick={() => pick(album)}>
              {i < 9 && <kbd className={styles.kbd}>{i + 1}</kbd>}
              <span className={styles.grow}>{album.name}</span>
              <span className={styles.muted}>{album.count}</span>
            </button>
          </li>
        ))}
      </ul>
      <form
        className={styles.newAlbum}
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <TextField
          label="Nuevo álbum"
          placeholder="Asturias 2025"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={create.isError ? errorMessage(create.error) : undefined}
        />
        <Button type="submit" variant="primary" disabled={!name.trim() || create.isPending}>
          Crear y añadir
        </Button>
      </form>
    </Dialog>
  );
}
