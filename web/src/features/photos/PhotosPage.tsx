import { useSearchParams } from "react-router";

import { useMemo } from "react";

import { canEdit, useSession } from "../../app/session";
import { Alert } from "../../design-system/components/Card";
import { EmptyState } from "../../design-system/components/EmptyState";
import { errorMessage } from "../../app/errors";
import { t } from "../../i18n";
import { readFilters, activeCount } from "./filters";
import { FiltersBar } from "./FiltersBar";
import { formatMonth } from "./format";
import { Grid } from "./Grid";
import styles from "./photos.module.css";
import { useAssets, useTimeline } from "./useAssets";
import { SelectionBar } from "../selection/SelectionBar";
import { useSelection } from "../selection/useSelection";
import { Viewer } from "./Viewer";
import { ViewerActions } from "./ViewerActions";

/** Línea temporal del espacio con filtros y visor. */
export function PhotosPage() {
  const { space } = useSession();
  if (!space)
    return (
      <EmptyState title="Aún no tienes ningún espacio">
        Ve a «Más → Espacio y miembros» para crear uno.
      </EmptyState>
    );
  return <SpaceTimeline spaceId={space.id} editor={canEdit(space)} />;
}

function SpaceTimeline({ spaceId, editor }: { spaceId: string; editor: boolean }) {
  const [params, setParams] = useSearchParams();
  const filters = readFilters(params);
  const start = params.get("desde") ?? undefined;
  const assets = useAssets(spaceId, filters, start);
  const timeline = useTimeline(spaceId, filters);
  const viewing = params.get("ver");
  const ids = useMemo(() => assets.items.map((a) => a.id), [assets.items]);
  const selection = useSelection(ids);
  const index = viewing ? assets.items.findIndex((a) => a.id === viewing) : -1;

  const open = (i: number) => {
    const next = new URLSearchParams(params);
    const id = assets.items[i]?.id;
    if (!id) return;
    next.set("ver", id);
    // La primera apertura añade una entrada al historial: «atrás» cierra el visor.
    setParams(next, { replace: viewing !== null });
  };
  const close = () => {
    const next = new URLSearchParams(params);
    next.delete("ver");
    setParams(next, { replace: true });
  };
  const jump = (year: number, month: number) => {
    const next = new URLSearchParams(params);
    const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
    next.set("desde", `${year}-${String(month).padStart(2, "0")}-${lastDay}`);
    next.delete("ver");
    setParams(next);
    window.scrollTo({ top: 0 });
  };

  const total = timeline.data?.total;
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <p className={styles.count} aria-live="polite">
          {total === undefined
            ? ""
            : `${total.toLocaleString("es")} ${total === 1 ? "elemento" : "elementos"}`}
        </p>
        {(timeline.data?.months.length ?? 0) > 1 && (
          <label className={styles.jump}>
            <span className="visually-hidden">Ir a</span>
            <select
              value=""
              onChange={(e) => {
                const [y, m] = e.target.value.split("-").map(Number);
                if (y && m) jump(y, m);
              }}
            >
              <option value="">Ir a…</option>
              {timeline.data?.months.map((m) => (
                <option key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>
                  {formatMonth(m.year, m.month)} ({m.count})
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <FiltersBar />
      {start && (
        <Alert>
          Mostrando desde {start}.{" "}
          <button
            type="button"
            className={styles.linkButton}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.delete("desde");
              setParams(next);
            }}
          >
            Volver a lo más reciente
          </button>
        </Alert>
      )}
      {assets.isError && <Alert tone="danger">{errorMessage(assets.error)}</Alert>}
      {assets.isSuccess && assets.items.length === 0 ? (
        activeCount(filters) > 0 ? (
          <EmptyState title="Nada con estos filtros">Prueba a quitar alguno.</EmptyState>
        ) : (
          <EmptyState title={t("photos.empty.title")}>{t("photos.empty.text")}</EmptyState>
        )
      ) : (
        <Grid
          items={assets.items}
          hasMore={assets.hasNextPage}
          loadMore={() => {
            if (!assets.isFetchingNextPage) void assets.fetchNextPage();
          }}
          onOpen={open}
          selected={editor ? selection.selected : undefined}
          onToggle={editor ? selection.toggle : undefined}
          onSelectDay={editor ? selection.toggleMany : undefined}
          draggable={editor}
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
          actions={(asset) =>
            editor ? (
              <ViewerActions
                spaceId={spaceId}
                asset={asset}
                onRemoved={() => {
                  const next = assets.items[index + 1] ?? assets.items[index - 1];
                  if (next) open(assets.items.indexOf(next));
                  else close();
                }}
              />
            ) : null
          }
        />
      )}
    </div>
  );
}
