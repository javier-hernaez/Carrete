import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { api, type Tag } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { canEdit, useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { Alert, Card, PageTitle } from "../../design-system/components/Card";
import { Dialog } from "../../design-system/components/Dialog";
import { EmptyState } from "../../design-system/components/EmptyState";
import { TextField } from "../../design-system/components/Field";
import styles from "../page.module.css";
import { showToast } from "../toast/toast";
import { useTags } from "./tags";

/** Etiquetas del espacio: ver sus fotos, crear, renombrar y eliminar (sin tocar las fotos). */
export function TagsPage() {
  const { space } = useSession();
  const spaceId = space?.id ?? "";
  const tags = useTags(spaceId);
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Tag | null>(null);
  const [removing, setRemoving] = useState<Tag | null>(null);
  if (!space) return null;
  const editor = canEdit(space);
  const refresh = () =>
    Promise.all(["tags", "assets", "asset"].map((key) => queryClient.invalidateQueries({ queryKey: [key] })));

  return (
    <div className={styles.narrow}>
      <PageTitle>Etiquetas</PageTitle>
      <p className={styles.muted}>
        Una foto puede tener varias: «Personas», «Paisajes», «Humor»… Se ponen desde el visor, desde Revisar o
        seleccionando varias fotos.
      </p>
      {editor && (
        <Card title="Nueva etiqueta">
          <form
            className={styles.inline}
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              api
                .createTag(spaceId, name)
                .then(async () => {
                  setName("");
                  await refresh();
                })
                .catch((err: unknown) => setError(errorMessage(err)));
            }}
          >
            <TextField
              label="Nombre"
              placeholder="Mascotas"
              value={name}
              maxLength={40}
              onChange={(e) => setName(e.target.value)}
              error={error ?? undefined}
            />
            <Button type="submit" variant="primary" disabled={!name.trim()}>
              Crear
            </Button>
          </form>
        </Card>
      )}
      {tags.isError && <Alert tone="danger">{errorMessage(tags.error)}</Alert>}
      {tags.isSuccess && tags.data.length === 0 ? (
        <EmptyState title="Aún no hay etiquetas">
          Crea la primera aquí o desde el visor de cualquier foto.
        </EmptyState>
      ) : (
        <Card title="En este espacio">
          <ul className={styles.list}>
            {tags.data?.map((tag) => (
              <li key={tag.id} className={styles.row}>
                <div className={styles.grow}>
                  <Link to={`/?etiqueta=${tag.id}`}>{tag.name}</Link>{" "}
                  <span className={styles.muted}>
                    ({tag.count} {tag.count === 1 ? "elemento" : "elementos"})
                  </span>
                </div>
                {editor && (
                  <>
                    <Button variant="ghost" onClick={() => setEditing(tag)}>
                      Renombrar
                    </Button>
                    <Button variant="ghost" onClick={() => setRemoving(tag)}>
                      Eliminar
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
      {editing && (
        <RenameDialog
          tag={editing}
          onClose={() => setEditing(null)}
          onSave={(next) =>
            api.renameTag(spaceId, editing.id, next).then(async () => {
              setEditing(null);
              await refresh();
            })
          }
        />
      )}
      {removing && (
        <Dialog title="Eliminar la etiqueta" onClose={() => setRemoving(null)}>
          <p>
            Se quita «{removing.name}» de {removing.count} {removing.count === 1 ? "elemento" : "elementos"}.
            Las fotos no se borran.
          </p>
          <div className={styles.inline}>
            <Button variant="secondary" onClick={() => setRemoving(null)}>
              Cancelar
            </Button>
            <Button
              variant="danger"
              onClick={() =>
                void api
                  .deleteTag(spaceId, removing.id)
                  .then(async () => {
                    showToast(`Etiqueta «${removing.name}» eliminada`);
                    setRemoving(null);
                    await refresh();
                  })
                  .catch((err: unknown) => showToast(errorMessage(err), { tone: "danger" }))
              }
            >
              Eliminar etiqueta
            </Button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function RenameDialog({
  tag,
  onClose,
  onSave,
}: {
  tag: Tag;
  onClose: () => void;
  onSave: (name: string) => Promise<unknown>;
}) {
  const [name, setName] = useState(tag.name);
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog title="Renombrar la etiqueta" onClose={onClose}>
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          onSave(name).catch((err: unknown) => setError(errorMessage(err)));
        }}
      >
        <TextField
          label="Nombre"
          value={name}
          maxLength={40}
          onChange={(e) => setName(e.target.value)}
          error={error ?? undefined}
        />
        <Button type="submit" variant="primary" disabled={!name.trim()}>
          Guardar
        </Button>
      </form>
    </Dialog>
  );
}
