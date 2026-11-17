import { useMemo } from "react";
import { Link, useSearchParams } from "react-router";

import { errorMessage } from "../../app/errors";
import { Alert } from "../../design-system/components/Card";
import { EmptyState } from "../../design-system/components/EmptyState";
import { t } from "../../i18n";
import { readFilters } from "../photos/filters";
import { Grid } from "../photos/Grid";
import { useAssets, useTimeline } from "../photos/useAssets";
import { Viewer } from "../photos/Viewer";
import { ViewerActions } from "../photos/ViewerActions";
import { SelectionBar } from "../selection/SelectionBar";
import { useSelection } from "../selection/useSelection";
import styles from "./review.module.css";
import { ModeSwitch } from "./ModeSwitch";

/**
 * Revisar en cuadrícula: lo pendiente agrupado por días, para decidir en bloque. Se marca con la
 * casilla, con «Seleccionar el día» o manteniendo pulsada una foto y deslizando; luego «Vale» o
 * «Descartar» (o etiquetas, álbum…) para todas a la vez. Lo decidido sale de la lista.
 */
export function ReviewGrid({ spaceId, onMode }: { spaceId: string; onMode: (mode: "one") => void }) {
  const [params, setParams] = useSearchParams();
  const filters = readFilters(params);
  const effective = filters.estado ? filters : { ...filters, estado: "pendiente" as const };
  const assets = useAssets(spaceId, effective);
  const timeline = useTimeline(spaceId, effective);
  const ids = useMemo(() => assets.items.map((a) => a.id), [assets.items]);
  const selection = useSelection(ids);
  const viewing = params.get("ver");
  const index = viewing ? assets.items.findIndex((a) => a.id === viewing) : -1;
  const open = (i: number) => {
    const id = assets.items[i]?.id;
    if (!id) return;
    const next = new URLSearchParams(params);
    next.set("ver", id);
    setParams(next, { replace: viewing !== null });
  };
  const close = () => {
    const next = new URLSearchParams(params);
    next.delete("ver");
    setParams(next, { replace: true });
  };
  const total = timeline.data?.total;

  return (
    <div className={styles.gridPage}>
      <header className={styles.gridHead}>
        <h1 className={styles.gridTitle}>Revisar</h1>
        <ModeSwitch mode="grid" onMode={(m) => m === "one" && onMode("one")} />
      </header>
      {total !== undefined && total > 0 && (
        <p className={styles.gridHint}>
          {total.toLocaleString("es")} sin revisar. Marca varias (con la casilla, «Seleccionar el día» o
          manteniendo pulsada una foto y deslizando) y decide para todas a la vez.
        </p>
      )}
      {assets.isError && <Alert tone="danger">{errorMessage(assets.error)}</Alert>}
      {assets.isSuccess && assets.items.length === 0 ? (
        <EmptyState title={t("review.empty.title")} action={<Link to="/">Ver las fotos</Link>}>
          {t("review.empty.text")}
        </EmptyState>
      ) : (
        <Grid
          items={assets.items}
          hasMore={assets.hasNextPage}
          loadMore={() => {
            if (!assets.isFetchingNextPage) void assets.fetchNextPage();
          }}
          onOpen={open}
          selected={selection.selected}
          onToggle={selection.toggle}
          onSelectDay={selection.toggleMany}
          onReplace={selection.replace}
          showChecks
        />
      )}
      {selection.selected.size > 0 && (
        <SelectionBar
          spaceId={spaceId}
          ids={[...selection.selected]}
          items={assets.items}
          onClear={selection.clear}
          onSelectAll={selection.selectAll}
        />
      )}
      {index >= 0 && (
        <Viewer
          items={assets.items}
          index={index}
          onIndex={open}
          onClose={close}
          actions={(asset) => (
            <ViewerActions
              spaceId={spaceId}
              asset={asset}
              onRemoved={() => {
                const next = assets.items[index + 1] ?? assets.items[index - 1];
                if (next) open(assets.items.indexOf(next));
                else close();
              }}
            />
          )}
        />
      )}
    </div>
  );
}
