import { useState } from "react";
import { useSearchParams } from "react-router";

import { api } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { canEdit, isOwner, useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { Alert, PageTitle } from "../../design-system/components/Card";
import { Dialog } from "../../design-system/components/Dialog";
import { EmptyState } from "../../design-system/components/EmptyState";
import { TextField } from "../../design-system/components/Field";
import { useAssetActions } from "../photos/actions";
import { readFilters } from "../photos/filters";
import { Grid } from "../photos/Grid";
import { useAssets } from "../photos/useAssets";
import { Viewer } from "../photos/Viewer";
import { showToast } from "../toast/toast";
import styles from "../page.module.css";

/** Papelera: se recupera durante 30 días; vaciarla exige teclear el nombre del espacio. */
export function TrashPage() {
  const { space } = useSession();
  if (!space) return null;
  return <Trash spaceId={space.id} spaceName={space.name} owner={isOwner(space)} editor={canEdit(space)} />;
}

function Trash({
  spaceId,
  spaceName,
  owner,
  editor,
}: {
  spaceId: string;
  spaceName: string;
  owner: boolean;
  editor: boolean;
}) {
  const { withReauth } = useSession();
  const [params, setParams] = useSearchParams();
  const filters = { ...readFilters(new URLSearchParams()), estado: "todas" as const };
  const assets = useAssets(spaceId, filters, undefined, true);
  const actions = useAssetActions(spaceId);
  const [confirming, setConfirming] = useState(false);
  const viewing = params.get("ver");
  const index = viewing ? assets.items.findIndex((a) => a.id === viewing) : -1;
  const setViewing = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set("ver", id);
    else next.delete("ver");
    setParams(next, { replace: viewing !== null || id === null });
  };

  return (
    <div>
      <PageTitle
        actions={
          owner && assets.items.length > 0 ? (
            <Button variant="secondary" onClick={() => setConfirming(true)}>
              Vaciar papelera
            </Button>
          ) : undefined
        }
      >
        Papelera
      </PageTitle>
      <Alert>Lo que envíes aquí se borra solo a los 30 días. Hasta entonces se puede recuperar.</Alert>
      {assets.isSuccess && assets.items.length === 0 ? (
        <EmptyState title="La papelera está vacía" />
      ) : (
        <Grid
          items={assets.items}
          hasMore={assets.hasNextPage}
          loadMore={() => void assets.fetchNextPage()}
          onOpen={(i) => setViewing(assets.items[i]?.id ?? null)}
        />
      )}
      {index >= 0 && (
        <Viewer
          items={assets.items}
          index={index}
          onIndex={(i) => setViewing(assets.items[i]?.id ?? null)}
          onClose={() => setViewing(null)}
          actions={(asset) =>
            editor ? (
              <Button
                variant="primary"
                onClick={() => {
                  setViewing(null);
                  void actions.restore([asset.id]);
                }}
              >
                Recuperar
              </Button>
            ) : null
          }
        />
      )}
      {confirming && (
        <EmptyTrashDialog
          spaceName={spaceName}
          count={assets.items.length}
          onCancel={() => setConfirming(false)}
          onConfirm={async (name) => {
            const { count } = await withReauth(() => api.emptyTrash(spaceId, name));
            setConfirming(false);
            await actions.refresh();
            showToast(`Se han borrado definitivamente ${count} elementos`);
          }}
        />
      )}
    </div>
  );
}

function EmptyTrashDialog({
  spaceName,
  count,
  onCancel,
  onConfirm,
}: {
  spaceName: string;
  count: number;
  onCancel: () => void;
  onConfirm: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  return (
    <Dialog title="Vaciar la papelera" onClose={onCancel}>
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          setBusy(true);
          onConfirm(name)
            .catch((err: unknown) => setError(errorMessage(err)))
            .finally(() => setBusy(false));
        }}
      >
        <p>
          Se borrarán <strong>definitivamente {count}</strong> elementos. Las copias de seguridad los guardan
          30 días más; después ya no se podrán recuperar.
        </p>
        <TextField
          label={`Escribe «${spaceName}» para confirmar`}
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={error}
          autoComplete="off"
          required
        />
        <Button type="submit" variant="primary" disabled={busy || name !== spaceName}>
          Borrar definitivamente
        </Button>
      </form>
    </Dialog>
  );
}
