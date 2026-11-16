import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";

import { api, type AssetItem } from "../../api/client";
import { formatBytes, formatDateTime, placeLabel, SOURCE_LABEL } from "./format";
import styles from "./viewer.module.css";

interface ViewerProps {
  items: AssetItem[];
  index: number;
  onIndex: (index: number) => void;
  onClose: () => void;
  /** Botones extra (vale, descartar, álbum…) que añaden Revisar y la selección. */
  actions?: (asset: AssetItem) => ReactNode;
  onKey?: (e: KeyboardEvent, asset: AssetItem) => boolean;
  hideNav?: boolean;
}

const MAX_ZOOM = 6;

/** Visor a pantalla completa. Siempre oscuro. */
export function Viewer({ items, index, onIndex, onClose, actions, onKey, hideNav }: ViewerProps) {
  const asset = items[index];
  const [info, setInfo] = useState(false);
  // El zoom pertenece a una foto concreta: al cambiar de foto vuelve a 1 sin efectos extra.
  const [zoomState, setZoomState] = useState({ index, scale: 1, x: 0, y: 0 });
  const zoom = zoomState.index === index ? zoomState : { index, scale: 1, x: 0, y: 0 };
  const setZoom = (
    next:
      | { scale: number; x: number; y: number }
      | ((z: { scale: number; x: number; y: number }) => { scale: number; x: number; y: number }),
  ) => {
    setZoomState((current) => {
      const base = current.index === index ? current : { index, scale: 1, x: 0, y: 0 };
      const value = typeof next === "function" ? next(base) : next;
      return { index, scale: value.scale, x: value.x, y: value.y };
    });
  };
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{
    startX: number;
    startY: number;
    dist: number;
    scale: number;
    panX: number;
    panY: number;
  } | null>(null);
  const lastTap = useRef(0);
  const closeRef = useRef<HTMLButtonElement>(null);

  const go = useCallback(
    (delta: number) => {
      const next = index + delta;
      if (next >= 0 && next < items.length) onIndex(next);
    },
    [index, items.length, onIndex],
  );

  useEffect(() => {
    closeRef.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  // Precarga las vistas previas vecinas para que pasar de foto no tenga esperas.
  useEffect(() => {
    for (const d of [1, -1, 2]) {
      const n = items[index + d];
      if (n && n.processing_state === "ready") new Image().src = `/api/v1/assets/${n.id}/preview`;
    }
  }, [index, items]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        !asset ||
        e.defaultPrevented ||
        (e.target instanceof Element && e.target.closest("input, textarea, select"))
      )
        return;
      if (onKey?.(e, asset)) {
        e.preventDefault();
        return;
      }
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight" && !hideNav) go(1);
      else if (e.key === "ArrowLeft" && !hideNav) go(-1);
      else if (e.key.toLowerCase() === "i") setInfo((v) => !v);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
    };
  }, [asset, go, onClose, onKey, hideNav]);

  if (!asset) return null;

  const onPointerDown = (e: PointerEvent) => {
    (e.target as Element).setPointerCapture(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const pts = [...pointers.current.values()];
    const dist =
      pts.length === 2 && pts[0] && pts[1] ? Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) : 0;
    gesture.current = {
      startX: e.clientX,
      startY: e.clientY,
      dist,
      scale: zoom.scale,
      panX: zoom.x,
      panY: zoom.y,
    };
  };
  const onPointerMove = (e: PointerEvent) => {
    if (!pointers.current.has(e.pointerId) || !gesture.current) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const pts = [...pointers.current.values()];
    const g = gesture.current;
    if (pts.length === 2 && pts[0] && pts[1] && g.dist) {
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      setZoom((z) => ({ ...z, scale: Math.min(MAX_ZOOM, Math.max(1, (g.scale * dist) / g.dist)) }));
    } else if (zoom.scale > 1) {
      setZoom({ scale: zoom.scale, x: g.panX + e.clientX - g.startX, y: g.panY + e.clientY - g.startY });
    }
  };
  const onPointerUp = (e: PointerEvent) => {
    const g = gesture.current;
    pointers.current.delete(e.pointerId);
    if (!g || pointers.current.size > 0) return;
    gesture.current = null;
    const dx = e.clientX - g.startX;
    const dy = e.clientY - g.startY;
    if (zoom.scale === 1 && Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      if (!hideNav) go(dx < 0 ? 1 : -1);
      return;
    }
    if (Math.abs(dx) < 10 && Math.abs(dy) < 10) {
      const now = Date.now();
      if (now - lastTap.current < 300) {
        setZoom((z) => (z.scale > 1 ? { scale: 1, x: 0, y: 0 } : { scale: 2.5, x: 0, y: 0 }));
        lastTap.current = 0;
      } else lastTap.current = now;
    }
  };

  return (
    <div
      className={styles.viewer}
      role="dialog"
      aria-modal="true"
      aria-label="Visor de fotos"
      data-fullscreen=""
    >
      <div className={styles.toolbar}>
        <button
          ref={closeRef}
          type="button"
          className={styles.tool}
          onClick={onClose}
          aria-label="Cerrar (Esc)"
        >
          ✕
        </button>
        <span className={styles.position}>
          {index + 1} de {items.length}
        </span>
        <div className={styles.toolGroup}>
          <a
            className={styles.tool}
            href={`/api/v1/assets/${asset.id}/original`}
            download
            aria-label="Descargar el original"
          >
            ⤓
          </a>
          <button
            type="button"
            className={styles.tool}
            onClick={() => setInfo((v) => !v)}
            aria-pressed={info}
            aria-label="Información (I)"
          >
            ⓘ
          </button>
        </div>
      </div>

      <div
        className={styles.stage}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onWheel={(e) => {
          if (asset.kind === "video") return;
          const scale = Math.min(MAX_ZOOM, Math.max(1, zoom.scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
          setZoom(scale === 1 ? { scale: 1, x: 0, y: 0 } : { ...zoom, scale });
        }}
      >
        {asset.kind === "video" ? (
          // Vídeos personales: no existen subtítulos que ofrecer.
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video
            key={asset.id}
            className={styles.media}
            src={`/api/v1/assets/${asset.id}/video`}
            poster={asset.processing_state === "ready" ? `/api/v1/assets/${asset.id}/preview` : undefined}
            controls
            playsInline
            preload="metadata"
          />
        ) : asset.processing_state === "ready" ? (
          <img
            key={asset.id}
            className={styles.media}
            src={`/api/v1/assets/${asset.id}/preview`}
            alt=""
            draggable={false}
            style={{ transform: `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.scale})` }}
          />
        ) : (
          <p className={styles.processing}>
            {asset.processing_state === "failed"
              ? "No se pudo procesar esta foto. El original está guardado y se puede descargar."
              : "Procesando…"}
          </p>
        )}
        {!hideNav && index > 0 && (
          <button
            type="button"
            className={`${styles.nav ?? ""} ${styles.prev ?? ""}`}
            onClick={() => go(-1)}
            aria-label="Anterior (←)"
          >
            ‹
          </button>
        )}
        {!hideNav && index < items.length - 1 && (
          <button
            type="button"
            className={`${styles.nav ?? ""} ${styles.next ?? ""}`}
            onClick={() => go(1)}
            aria-label="Siguiente (→)"
          >
            ›
          </button>
        )}
      </div>

      {actions && <div className={styles.actions}>{actions(asset)}</div>}
      {info && <InfoPanel id={asset.id} />}
    </div>
  );
}

function InfoPanel({ id }: { id: string }) {
  const detail = useQuery({ queryKey: ["asset", id], queryFn: () => api.asset(id) });
  const d = detail.data;
  return (
    <aside className={styles.info} aria-label="Información">
      {!d ? (
        <p>Cargando…</p>
      ) : (
        <dl className={styles.infoList}>
          <dt>Fecha</dt>
          <dd>
            {formatDateTime(d.taken_at, d.taken_at_offset)}
            {d.date_doubtful && <span className={styles.warn}> · fecha dudosa</span>}
          </dd>
          <dt>Origen</dt>
          <dd>{SOURCE_LABEL[d.source] ?? d.source}</dd>
          <dt>Subida por</dt>
          <dd>
            {d.uploaded_by ?? "—"}
            {d.contributors.length > 1 && ` (y ${d.contributors.length - 1} más)`}
          </dd>
          {d.albums.length > 0 && (
            <>
              <dt>Álbumes</dt>
              <dd>{d.albums.map((a) => a.name).join(", ")}</dd>
            </>
          )}
          {d.description && (
            <>
              <dt>Descripción</dt>
              <dd>{d.description}</dd>
            </>
          )}
          <dt>Fichero</dt>
          <dd>
            {d.original_filename} · {formatBytes(d.size_bytes)}
            {d.width && d.height ? ` · ${d.width}×${d.height}` : ""}
          </dd>
          {d.camera && (
            <>
              <dt>Cámara</dt>
              <dd>{d.camera}</dd>
            </>
          )}
          {d.lat !== null && d.lon !== null && (
            <>
              <dt>Ubicación</dt>
              <dd>
                {placeLabel(d) && (
                  <>
                    {placeLabel(d)}
                    <br />
                  </>
                )}
                <span className={styles.coords}>
                  {d.lat.toFixed(5)}, {d.lon.toFixed(5)}
                </span>
              </dd>
            </>
          )}
        </dl>
      )}
    </aside>
  );
}
