import { useState } from "react";

import type { AssetItem } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { downloadSelection } from "../export/download";
import { useAssetActions } from "../photos/actions";
import { AlbumPicker } from "./AlbumPicker";
import { DateDialog } from "./DateDialog";
import styles from "./selection.module.css";

interface SelectionBarProps {
  spaceId: string;
  ids: string[];
  items: AssetItem[];
  onClear: () => void;
  onSelectAll: () => void;
  /** Acciones de la vista (p. ej. «Quitar del álbum» o «Recuperar»). Si se dan, sustituyen a las normales. */
  extra?: ((actions: ReturnType<typeof useAssetActions>, ids: string[]) => React.ReactNode) | undefined;
  hideStandard?: boolean | undefined;
}

/** Barra de acciones sobre la selección: vale, descartar, favorita, álbum, fecha, eliminar. */
export function SelectionBar({
  spaceId,
  ids,
  items,
  onClear,
  onSelectAll,
  extra,
  hideStandard,
}: SelectionBarProps) {
  const actions = useAssetActions(spaceId);
  const [dialog, setDialog] = useState<"album" | "date" | null>(null);
  const done = (promise: Promise<unknown>) => {
    void promise.then(onClear);
  };
  const allFavorite = ids.every((id) => items.find((i) => i.id === id)?.is_favorite);
  return (
    <div className={styles.bar} role="toolbar" aria-label="Acciones sobre la selección">
      <span className={styles.count} aria-live="polite">
        {ids.length} {ids.length === 1 ? "seleccionada" : "seleccionadas"}
      </span>
      {!hideStandard && (
        <>
          <Button variant="ghost" onClick={() => done(actions.review(ids, "kept"))}>
            Vale
          </Button>
          <Button variant="ghost" onClick={() => done(actions.review(ids, "discarded"))}>
            Descartar
          </Button>
          <Button variant="ghost" onClick={() => done(actions.favorite(ids, !allFavorite))}>
            {allFavorite ? "Quitar ★" : "Favorita ★"}
          </Button>
          <Button variant="ghost" onClick={() => setDialog("album")}>
            Álbum…
          </Button>
          <Button variant="ghost" onClick={() => setDialog("date")}>
            Fecha…
          </Button>
          <Button variant="ghost" onClick={() => done(downloadSelection(spaceId, ids))}>
            Descargar
          </Button>
          <Button variant="ghost" onClick={() => done(actions.trash(ids))}>
            Eliminar
          </Button>
        </>
      )}
      {extra?.(actions, ids)}
      <span className={styles.spacer} />
      <Button variant="ghost" onClick={onSelectAll}>
        Todas
      </Button>
      <Button variant="secondary" onClick={onClear}>
        Cancelar
      </Button>
      {dialog === "album" && (
        <AlbumPicker
          spaceId={spaceId}
          count={ids.length}
          onClose={() => setDialog(null)}
          onPick={(album) => {
            setDialog(null);
            done(actions.addToAlbum(ids, album.id, album.name));
          }}
        />
      )}
      {dialog === "date" && (
        <DateDialog
          count={ids.length}
          initial={ids.length === 1 ? items.find((i) => i.id === ids[0])?.taken_at : undefined}
          onClose={() => setDialog(null)}
          onSet={(value) => {
            setDialog(null);
            done(actions.setDate(ids, value));
          }}
          onShift={(minutes) => {
            setDialog(null);
            done(actions.shiftDate(ids, minutes));
          }}
        />
      )}
    </div>
  );
}
