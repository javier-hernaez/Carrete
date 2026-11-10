import { memo, useMemo, useState } from "react";

import type { AssetItem } from "../../api/client";
import { thumbHashToPlaceholder } from "../../media/thumbhash";
import { formatDuration } from "./format";
import styles from "./photos.module.css";

interface ThumbProps {
  asset: AssetItem;
  label: string;
  selected?: boolean | undefined;
  onOpen: () => void;
}

/** Miniatura con marcador ThumbHash mientras carga; marca vídeo, favorita y «procesando». */
export const Thumb = memo(function Thumb({ asset, label, selected, onOpen }: ThumbProps) {
  const placeholder = useMemo(() => thumbHashToPlaceholder(asset.thumbhash), [asset.thumbhash]);
  const [loaded, setLoaded] = useState(false);
  const ready = asset.processing_state === "ready";
  return (
    <button
      type="button"
      className={styles.thumb}
      style={{
        backgroundColor: placeholder.color,
        backgroundImage: placeholder.url ? `url(${placeholder.url})` : undefined,
      }}
      onClick={onOpen}
      aria-label={label}
      aria-pressed={selected}
      data-selected={selected ? "" : undefined}
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
      {asset.processing_state === "failed" && <span className={styles.badgeFailed}>No se pudo procesar</span>}
      {asset.kind === "video" && (
        <span className={styles.badgeVideo}>▶ {formatDuration(asset.duration_ms)}</span>
      )}
      {asset.is_favorite && (
        <span className={styles.badgeFav} aria-hidden="true">
          ★
        </span>
      )}
    </button>
  );
});
