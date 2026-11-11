import { memo, useMemo, useRef, useState, type DragEvent } from "react";

import type { AssetItem } from "../../api/client";
import { thumbHashToPlaceholder } from "../../media/thumbhash";
import { formatDuration } from "./format";
import { DRAG_TYPE } from "./drag";
import styles from "./photos.module.css";

const LONG_PRESS_MS = 450;

interface ThumbProps {
  asset: AssetItem;
  label: string;
  selected?: boolean | undefined;
  selecting?: boolean | undefined;
  onActivate: (event: { shiftKey: boolean }) => void;
  onSelect?: ((event: { shiftKey: boolean }) => void) | undefined;
  dragIds?: (() => string[]) | undefined;
}

/** Miniatura con marcador ThumbHash; selección por casilla, pulsación larga o Mayús+clic; arrastrable. */
export const Thumb = memo(function Thumb({
  asset,
  label,
  selected,
  selecting,
  onActivate,
  onSelect,
  dragIds,
}: ThumbProps) {
  const placeholder = useMemo(() => thumbHashToPlaceholder(asset.thumbhash), [asset.thumbhash]);
  const [loaded, setLoaded] = useState(false);
  const timer = useRef<number | null>(null);
  const longPressed = useRef(false);
  const ready = asset.processing_state === "ready";

  const startPress = (pointerType: string) => {
    if (!onSelect || pointerType === "mouse") return;
    longPressed.current = false;
    timer.current = window.setTimeout(() => {
      longPressed.current = true;
      onSelect({ shiftKey: false });
      if ("vibrate" in navigator) navigator.vibrate(15);
    }, LONG_PRESS_MS);
  };
  const cancelPress = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  };
  const onDragStart = (e: DragEvent) => {
    const ids = dragIds?.() ?? [asset.id];
    e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(ids));
    e.dataTransfer.setData("text/plain", `${ids.length} fotos`);
    e.dataTransfer.effectAllowed = "copy";
  };

  return (
    <div className={styles.thumbWrap} data-selected={selected ? "" : undefined}>
      <button
        type="button"
        className={styles.thumb}
        style={{
          backgroundColor: placeholder.color,
          backgroundImage: placeholder.url ? `url(${placeholder.url})` : undefined,
        }}
        onClick={(e) => {
          if (longPressed.current) {
            longPressed.current = false;
            return;
          }
          if ((e.shiftKey || selecting) && onSelect) onSelect({ shiftKey: e.shiftKey });
          else onActivate({ shiftKey: e.shiftKey });
        }}
        onPointerDown={(e) => startPress(e.pointerType)}
        onPointerUp={cancelPress}
        onPointerLeave={cancelPress}
        onPointerCancel={cancelPress}
        onContextMenu={(e) => {
          if (onSelect && longPressed.current) e.preventDefault();
        }}
        draggable={!!dragIds}
        onDragStart={onDragStart}
        aria-label={label}
      >
        {ready && (
          <img
            src={`/api/v1/assets/${asset.id}/thumb`}
            alt=""
            loading="lazy"
            decoding="async"
            className={styles.thumbImg}
            data-loaded={loaded ? "" : undefined}
            onLoad={() => setLoaded(true)}
            draggable={false}
          />
        )}
        {asset.processing_state === "pending" && <span className={styles.badgeProcessing}>Procesando…</span>}
        {asset.processing_state === "failed" && (
          <span className={styles.badgeFailed}>No se pudo procesar</span>
        )}
        {asset.kind === "video" && (
          <span className={styles.badgeVideo}>▶ {formatDuration(asset.duration_ms)}</span>
        )}
        {asset.is_favorite && (
          <span className={styles.badgeFav} aria-hidden="true">
            ★
          </span>
        )}
      </button>
      {onSelect && (
        <button
          type="button"
          className={styles.selectBox}
          aria-pressed={!!selected}
          aria-label={`Seleccionar: ${label}`}
          onClick={(e) => onSelect({ shiftKey: e.shiftKey })}
        >
          ✓
        </button>
      )}
    </div>
  );
});
