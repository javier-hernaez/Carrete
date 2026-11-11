import { useMemo } from "react";
import { useSearchParams } from "react-router";

import { canEdit, useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { Alert, PageTitle } from "../../design-system/components/Card";
import { EmptyState } from "../../design-system/components/EmptyState";
import { readFilters } from "../photos/filters";
import { Grid } from "../photos/Grid";
import { useAssets } from "../photos/useAssets";
import { Viewer } from "../photos/Viewer";
import { SelectionBar } from "../selection/SelectionBar";
import { useSelection } from "../selection/useSelection";
import { useAssetActions } from "../photos/actions";

/** Descartadas: fuera de la vista normal, se conservan. Se recuperan o se mandan a la papelera. */
export function DiscardedPage() {
  const { space } = useSession();
  const [params, setParams] = useSearchParams();
  const spaceId = space?.id ?? "";
  const filters = { ...readFilters(new URLSearchParams()), estado: "descartada" as const };
  const assets = useAssets(spaceId, filters);
  const ids = useMemo(() => assets.items.map((a) => a.id), [assets.items]);
  const selection = useSelection(ids);
  const actions = useAssetActions(spaceId);
  if (!space) return null;
  const editor = canEdit(space);
  const viewing = params.get("ver");
  const index = viewing ? assets.items.findIndex((a) => a.id === viewing) : -1;
  const setViewing = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set("ver", id);
    else next.delete("ver");
    setParams(next, { replace: true });
  };
  return (
    <div>
      <PageTitle>Descartadas</PageTitle>
      <Alert>
        Lo descartado no sale en la línea temporal ni en los álbumes, pero se conserva. Puedes recuperarlo o
        mandarlo a la papelera.
      </Alert>
      {assets.isSuccess && assets.items.length === 0 ? (
        <EmptyState title="No hay nada descartado" />
      ) : (
        <Grid
          items={assets.items}
          hasMore={assets.hasNextPage}
          loadMore={() => void assets.fetchNextPage()}
          onOpen={(i) => setViewing(assets.items[i]?.id ?? null)}
          selected={editor ? selection.selected : undefined}
          onToggle={editor ? selection.toggle : undefined}
          onSelectDay={editor ? selection.toggleMany : undefined}
        />
      )}
      {selection.selected.size > 0 && (
        <SelectionBar
          spaceId={spaceId}
          ids={[...selection.selected]}
          items={assets.items}
          onClear={selection.clear}
          onSelectAll={selection.selectAll}
          hideStandard
          extra={(act, selected) => (
            <>
              <Button
                variant="ghost"
                onClick={() => void act.review(selected, "pending").then(selection.clear)}
              >
                Recuperar
              </Button>
              <Button variant="ghost" onClick={() => void act.trash(selected).then(selection.clear)}>
                A la papelera
              </Button>
            </>
          )}
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
                  void actions.review([asset.id], "pending");
                }}
              >
                Recuperar
              </Button>
            ) : null
          }
        />
      )}
    </div>
  );
}
