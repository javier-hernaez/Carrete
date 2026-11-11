import { useState } from "react";

import type { AssetItem } from "../../api/client";
import { AlbumPicker } from "../selection/AlbumPicker";
import { DateDialog } from "../selection/DateDialog";
import { useAssetActions } from "./actions";
import styles from "./viewer.module.css";

/** Botones de organizar dentro del visor. */
export function ViewerActions({
  spaceId,
  asset,
  onRemoved,
  extra,
}: {
  spaceId: string;
  asset: AssetItem;
  onRemoved: () => void;
  extra?: React.ReactNode;
}) {
  const actions = useAssetActions(spaceId);
  const [dialog, setDialog] = useState<"album" | "date" | null>(null);
  const ids = [asset.id];
  return (
    <>
      <button
        type="button"
        className={styles.action}
        aria-pressed={asset.review_state === "kept"}
        onClick={() => void actions.review(ids, asset.review_state === "kept" ? "pending" : "kept")}
      >
        ✓ Vale
      </button>
      <button
        type="button"
        className={styles.action}
        aria-pressed={asset.review_state === "discarded"}
        onClick={() => {
          if (asset.review_state !== "discarded") onRemoved();
          void actions.review(ids, asset.review_state === "discarded" ? "pending" : "discarded");
        }}
      >
        ✕ No vale
      </button>
      <button
        type="button"
        className={styles.action}
        aria-pressed={asset.is_favorite}
        onClick={() => void actions.favorite(ids, !asset.is_favorite)}
      >
        ★ Favorita
      </button>
      <button type="button" className={styles.action} onClick={() => setDialog("album")}>
        Álbum…
      </button>
      <button type="button" className={styles.action} onClick={() => setDialog("date")}>
        Fecha…
      </button>
      {extra}
      <button
        type="button"
        className={styles.action}
        onClick={() => {
          onRemoved();
          void actions.trash(ids);
        }}
      >
        Eliminar
      </button>
      {dialog === "album" && (
        <AlbumPicker
          spaceId={spaceId}
          count={1}
          onClose={() => setDialog(null)}
          onPick={(album) => {
            setDialog(null);
            void actions.addToAlbum(ids, album.id, album.name);
          }}
        />
      )}
      {dialog === "date" && (
        <DateDialog
          count={1}
          initial={asset.taken_at}
          onClose={() => setDialog(null)}
          onSet={(value) => {
            setDialog(null);
            void actions.setDate(ids, value);
          }}
          onShift={(minutes) => {
            setDialog(null);
            void actions.shiftDate(ids, minutes);
          }}
        />
      )}
    </>
  );
}
