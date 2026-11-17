import { memo, useMemo, useState } from "react";

import type { AssetItem } from "../../api/client";
import { thumbHashToPlaceholder } from "../../media/thumbhash";
import { formatDuration } from "./format";
import styles from "./photos.module.css";

interface ThumbProps {
  asset: AssetItem;
  label: string;
  selected?: boolean | undefined;
  selecting?: boolean | undefined;
  onActivate: (event: { shiftKey: boolean }) => void;
  onSelect?: ((event: { shiftKey: boolean }) => void) | undefined;
  /** Posición en la cuadrícula: la usa la pulsación larga (que gestiona la cuadrícula) para saber qué foto es. */
  index: number;
}

/**
 * Miniatura con marcador ThumbHash. Se selecciona con la casilla, con Mayús+clic o manteniendo pulsado
 * (eso lo gestiona la cuadrícula); con la selección en marcha, un toque añade o quita.
 */
export const Thumb = memo(function Thumb({
  asset,
  label,
  selected,
  selecting,
  onActivate,
  onSelect,
  index,
}: ThumbProps) {
  const placeholder = useMemo(() => thumbHashToPlaceholder(asset.thumbhash), [asset.thumbhash]);
  const [loaded, setLoaded] = useState(false);
  const ready = asset.processing_state === "ready";

  return (
    <div className={styles.thumbWrap} data-selected={selected ? "" : undefined} data-index={index}>
      <button
        type="button"
        className={styles.thumb}
        style={{
          backgroundColor: placeholder.color,
          backgroundImage: placeholder.url ? `url(${placeholder.url})` : undefined,
        }}
        onClick={(e) => {
          if ((e.shiftKey || selecting) && onSelect) onSelect({ shiftKey: e.shiftKey });
          else onActivate({ shiftKey: e.shiftKey });
        }}
        draggable={false}
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
