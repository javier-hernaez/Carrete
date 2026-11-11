import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { api } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { canEdit, useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { Alert, PageTitle } from "../../design-system/components/Card";
import { EmptyState } from "../../design-system/components/EmptyState";
import { TextField } from "../../design-system/components/Field";
import { t } from "../../i18n";
import { useAlbums } from "../selection/albums";
import styles from "./albums.module.css";
import { albumRange } from "./range";

export function AlbumsPage() {
  const { space } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const albums = useAlbums(space?.id ?? "");
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => api.createAlbum(space?.id ?? "", name),
    onSuccess: async (album) => {
      await queryClient.invalidateQueries({ queryKey: ["albums"] });
      await navigate(`/albumes/${album.id}`);
    },
  });
  if (!space) return null;
  const list = [...(albums.data ?? [])];
  return (
    <div>
      <PageTitle>Álbumes</PageTitle>
      {canEdit(space) && (
        <form
          className={styles.create}
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
          />
          <Button type="submit" variant="primary" disabled={!name.trim() || create.isPending}>
            Crear
          </Button>
        </form>
      )}
      {create.isError && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
      {albums.isSuccess && list.length === 0 ? (
        <EmptyState title={t("albums.empty.title")}>{t("albums.empty.text")}</EmptyState>
      ) : (
        <ul className={styles.grid}>
          {list.map((album) => (
            <li key={album.id}>
              <Link to={`/albumes/${album.id}`} className={styles.card}>
                <div className={styles.cover}>
                  {album.cover_asset_id && (
                    <img src={`/api/v1/assets/${album.cover_asset_id}/thumb`} alt="" loading="lazy" />
                  )}
                </div>
                <div className={styles.cardText}>
                  <strong>{album.name}</strong>
                  <span className={styles.muted}>
                    {album.count} {album.count === 1 ? "elemento" : "elementos"}
                    {album.first && ` · ${albumRange(album.first, album.last)}`}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
