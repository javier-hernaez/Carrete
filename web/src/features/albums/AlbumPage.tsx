import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";

import { api, type AssetItem } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { canEdit, useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { Alert } from "../../design-system/components/Card";
import { Dialog } from "../../design-system/components/Dialog";
import { EmptyState } from "../../design-system/components/EmptyState";
import { useAssetActions } from "../photos/actions";
import { readFilters, toApiParams } from "../photos/filters";
import { Grid } from "../photos/Grid";
import { thumbHashToPlaceholder } from "../../media/thumbhash";
import { Viewer } from "../photos/Viewer";
import { ViewerActions } from "../photos/ViewerActions";
import { SelectionBar } from "../selection/SelectionBar";
import { useSelection } from "../selection/useSelection";
import { showToast } from "../toast/toast";
import { albumRange } from "./range";
import styles from "./albums.module.css";

export function AlbumPage() {
  const { space } = useSession();
  const { albumId = "" } = useParams();
  if (!space) return null;
  return <AlbumDetail spaceId={space.id} albumId={albumId} editor={canEdit(space)} />;
}

function AlbumDetail({ spaceId, albumId, editor }: { spaceId: string; albumId: string; editor: boolean }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const album = useQuery({
    queryKey: ["album", spaceId, albumId],
    queryFn: () => api.album(spaceId, albumId),
  });
  const manual = album.data?.sort_mode === "manual";
  const filters = { ...readFilters(new URLSearchParams()), album: albumId };
  const assets = useInfiniteQuery({
    queryKey: ["assets", spaceId, "album", albumId, manual],
    queryFn: ({ pageParam }) =>
      api.assets(
        spaceId,
        toApiParams(filters, {
          limit: "500",
          ...(manual ? { order: "album" } : {}),
          ...(pageParam ? { cursor: pageParam } : {}),
        }),
      ),
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: album.isSuccess,
  });
  const items = useMemo(() => assets.data?.pages.flatMap((p) => p.items) ?? [], [assets.data]);
  const ids = useMemo(() => items.map((i) => i.id), [items]);
  const selection = useSelection(ids);
  const actions = useAssetActions(spaceId);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["album"] }),
      queryClient.invalidateQueries({ queryKey: ["albums"] }),
    ]);
  const update = useMutation({
    mutationFn: (body: Parameters<typeof api.updateAlbum>[2]) => api.updateAlbum(spaceId, albumId, body),
    onSuccess: refresh,
    onError: (e) => showToast(errorMessage(e), { tone: "danger" }),
  });
  const viewing = params.get("ver");
  const index = viewing ? items.findIndex((a) => a.id === viewing) : -1;
  const open = (i: number) => {
    const next = new URLSearchParams(params);
    const id = items[i]?.id;
    if (!id) return;
    next.set("ver", id);
    setParams(next, { replace: viewing !== null });
  };
  const close = () => {
    const next = new URLSearchParams(params);
    next.delete("ver");
    setParams(next, { replace: true });
  };

  if (album.isError) return <EmptyState title="Este álbum no existe" />;
  const a = album.data;
  if (!a) return null;
  return (
    <div className={styles.detail}>
      <div className={styles.head}>
        {editor ? (
          <input
            className={styles.title}
            defaultValue={a.name}
            key={a.name}
            aria-label="Nombre del álbum"
            onBlur={(e) => {
              if (e.target.value.trim() && e.target.value !== a.name) update.mutate({ name: e.target.value });
            }}
          />
        ) : (
          <h1 className={styles.title}>{a.name}</h1>
        )}
        <p className={styles.muted}>
          {a.count} {a.count === 1 ? "elemento" : "elementos"}
          {a.first && ` · ${albumRange(a.first, a.last)}`}
        </p>
        {editor ? (
          <textarea
            className={styles.description}
            defaultValue={a.description ?? ""}
            key={a.description ?? ""}
            placeholder="Añade una descripción"
            aria-label="Descripción del álbum"
            onBlur={(e) => {
              if (e.target.value !== (a.description ?? "")) update.mutate({ description: e.target.value });
            }}
          />
        ) : (
          a.description && <p>{a.description}</p>
        )}
        {editor && (
          <div className={styles.toolbar}>
            <div className={styles.segmented} role="radiogroup" aria-label="Orden">
              <label>
                <input
                  type="radio"
                  name="orden"
                  checked={!manual}
                  onChange={() => update.mutate({ sort_mode: "date" })}
                />{" "}
                Por fecha
              </label>
              <label>
                <input
                  type="radio"
                  name="orden"
                  checked={manual}
                  onChange={() => update.mutate({ sort_mode: "manual" })}
                />{" "}
                Manual
              </label>
            </div>
            <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
              Eliminar álbum
            </Button>
          </div>
        )}
        {manual && editor && (
          <Alert>
            Arrastra las fotos para ordenarlas (con teclado: Espacio para coger, flechas para mover, Espacio
            para soltar).
          </Alert>
        )}
      </div>

      {assets.isSuccess && items.length === 0 ? (
        <EmptyState title="Este álbum está vacío">
          Selecciona fotos en la línea temporal y añádelas, o arrástralas sobre el álbum en la barra lateral.
        </EmptyState>
      ) : manual && editor ? (
        <SortableAlbum
          items={items}
          onOpen={open}
          onMove={(assetId, afterId, beforeId) => {
            api
              .reorderAlbum(spaceId, albumId, { asset_id: assetId, after_id: afterId, before_id: beforeId })
              .catch((e: unknown) => showToast(errorMessage(e), { tone: "danger" }))
              .finally(
                () => void queryClient.invalidateQueries({ queryKey: ["assets", spaceId, "album", albumId] }),
              );
          }}
        />
      ) : (
        <Grid
          items={items}
          hasMore={assets.hasNextPage}
          loadMore={() => void assets.fetchNextPage()}
          onOpen={open}
          selected={editor ? selection.selected : undefined}
          onToggle={editor ? selection.toggle : undefined}
          onSelectDay={editor ? selection.toggleMany : undefined}
        />
      )}

      {selection.selected.size > 0 && (
        <SelectionBar
          spaceId={spaceId}
          ids={[...selection.selected]}
          items={items}
          onClear={selection.clear}
          onSelectAll={selection.selectAll}
          extra={(act, selected) => (
            <Button
              variant="ghost"
              onClick={() => void act.removeFromAlbum(selected, albumId).then(selection.clear)}
            >
              Quitar del álbum
            </Button>
          )}
        />
      )}
      {index >= 0 && (
        <Viewer
          items={items}
          index={index}
          onIndex={open}
          onClose={close}
          actions={(asset) =>
            editor ? (
              <ViewerActions
                spaceId={spaceId}
                asset={asset}
                onRemoved={close}
                extra={
                  <>
                    <button
                      type="button"
                      className={styles.viewerAction}
                      onClick={() =>
                        update.mutate(
                          { cover_asset_id: asset.id },
                          { onSuccess: () => showToast("Portada cambiada") },
                        )
                      }
                    >
                      Usar de portada
                    </button>
                    <button
                      type="button"
                      className={styles.viewerAction}
                      onClick={() => {
                        close();
                        void actions.removeFromAlbum([asset.id], albumId);
                      }}
                    >
                      Quitar del álbum
                    </button>
                  </>
                }
              />
            ) : null
          }
        />
      )}
      {confirmDelete && (
        <Dialog title="Eliminar el álbum" onClose={() => setConfirmDelete(false)}>
          <p>Se elimina el álbum «{a.name}». Sus fotos no se borran: siguen en la línea temporal.</p>
          <Button
            variant="primary"
            onClick={() =>
              void api.deleteAlbum(spaceId, albumId).then(async () => {
                await refresh();
                showToast("Álbum eliminado");
                await navigate("/albumes");
              })
            }
          >
            Eliminar álbum
          </Button>
        </Dialog>
      )}
    </div>
  );
}

/** Orden manual con dnd-kit: ratón, táctil y teclado. Sin virtualizar (los álbumes son pequeños). */
function SortableAlbum({
  items,
  onOpen,
  onMove,
}: {
  items: AssetItem[];
  onOpen: (i: number) => void;
  onMove: (id: string, after: string | null, before: string | null) => void;
}) {
  const [order, setOrder] = useState(() => items.map((i) => i.id));
  const [synced, setSynced] = useState(items);
  if (synced !== items) {
    setSynced(items);
    setOrder(items.map((i) => i.id));
  }
  const byId = useMemo(() => new Map(items.map((i) => [i.id, i])), [items]);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = order.indexOf(String(active.id));
    const to = order.indexOf(String(over.id));
    const next = arrayMove(order, from, to);
    setOrder(next);
    const position = next.indexOf(String(active.id));
    onMove(String(active.id), next[position - 1] ?? null, next[position + 1] ?? null);
  };
  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <SortableContext items={order} strategy={rectSortingStrategy}>
        <ul className={styles.sortable} aria-label="Fotos del álbum en orden manual">
          {order.map((id) => {
            const asset = byId.get(id);
            return asset ? (
              <SortableThumb
                key={id}
                asset={asset}
                onOpen={() => onOpen(items.findIndex((i) => i.id === id))}
              />
            ) : null;
          })}
        </ul>
      </SortableContext>
    </DndContext>
  );
}

function SortableThumb({ asset, onOpen }: { asset: AssetItem; onOpen: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: asset.id,
  });
  const placeholder = thumbHashToPlaceholder(asset.thumbhash);
  return (
    <li
      ref={setNodeRef}
      className={styles.sortItem}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        zIndex: isDragging ? 2 : undefined,
        backgroundColor: placeholder.color,
      }}
      {...attributes}
      {...listeners}
      aria-roledescription="foto ordenable"
      aria-label={`Foto del ${asset.taken_at.slice(0, 10)}`}
    >
      {asset.processing_state === "ready" && (
        <img src={`/api/v1/assets/${asset.id}/thumb`} alt="" draggable={false} />
      )}
      <button type="button" className={styles.openButton} onClick={onOpen} aria-label="Abrir">
        ⤢
      </button>
    </li>
  );
}
