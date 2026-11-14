import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { api, type Album, type AssetItem } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { canEdit, useSession } from "../../app/session";
import { EmptyState } from "../../design-system/components/EmptyState";
import { t } from "../../i18n";
import { readFilters, toApiParams } from "../photos/filters";
import { formatDateTime, formatDuration, SOURCE_LABEL } from "../photos/format";
import { AlbumPicker } from "../selection/AlbumPicker";
import { rememberAlbum, useAlbums } from "../selection/albums";
import { showToast } from "../toast/toast";
import styles from "./review.module.css";

type Decision = {
  id: string;
  kind: "kept" | "discarded" | "favorite" | "album" | "skip";
  previous: { review_state: string; is_favorite: boolean };
  albumId?: string;
};

const SWIPE = 70;

/** Modo Revisar: de una en una, decisiones inmediatas y deshacer. */
export function ReviewPage() {
  const { space } = useSession();
  if (!space) return <EmptyState title="Aún no tienes ningún espacio" />;
  if (!canEdit(space))
    return (
      <EmptyState title="Solo puedes ver este espacio">Con el rol de lector no se puede revisar.</EmptyState>
    );
  return <Review spaceId={space.id} />;
}

function Review({ spaceId }: { spaceId: string }) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const filters = readFilters(params);
  // Por defecto, la bandeja de entrada: lo que está sin revisar. Con filtros, cualquier selección.
  const effective = filters.estado ? filters : { ...filters, estado: "pendiente" as const };
  // Una sesión de revisión no se recarga sola: las decisiones cambian el estado de lo que se revisa.
  const [session] = useState(() => Date.now());
  const query = useInfiniteQuery({
    queryKey: ["review", spaceId, effective, session],
    queryFn: ({ pageParam }) =>
      api.assets(
        spaceId,
        toApiParams(effective, { limit: "500", order: "asc", ...(pageParam ? { cursor: pageParam } : {}) }),
      ),
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  const items = useMemo<AssetItem[]>(() => query.data?.pages.flatMap((p) => p.items) ?? [], [query.data]);
  const [index, setIndex] = useState(0);
  const [history, setHistory] = useState<Decision[]>([]);
  const [overrides, setOverrides] = useState<Record<string, Partial<AssetItem>>>({});
  const [picker, setPicker] = useState(false);
  const albums = useAlbums(spaceId);
  const asset = useMemo(() => {
    const current = items[index];
    return current ? { ...current, ...overrides[current.id] } : undefined;
  }, [items, index, overrides]);
  const total = items.length;
  const counts = useMemo(() => {
    const c = { kept: 0, discarded: 0 };
    for (const d of history) if (d.kind === "kept" || d.kind === "discarded") c[d.kind]++;
    return c;
  }, [history]);

  useEffect(() => {
    if (query.hasNextPage && index > total - 50 && !query.isFetchingNextPage) void query.fetchNextPage();
  }, [index, total, query]);

  useEffect(() => {
    for (let d = 1; d <= 3; d++) {
      const next = items[index + d];
      if (next?.processing_state === "ready") new Image().src = `/api/v1/assets/${next.id}/preview`;
    }
  }, [index, items]);

  useEffect(
    () => () => {
      void queryClient.invalidateQueries({ queryKey: ["assets"] });
      void queryClient.invalidateQueries({ queryKey: ["counters"] });
    },
    [queryClient],
  );

  const send = useCallback(
    (ids: string[], action: string, extra: Record<string, unknown>) => {
      api
        .batch(spaceId, ids, action, extra)
        .catch((e: unknown) => showToast(errorMessage(e), { tone: "danger" }));
    },
    [spaceId],
  );

  const decide = useCallback(
    (kind: Decision["kind"], album?: Album) => {
      if (!asset) return;
      const previous = { review_state: asset.review_state, is_favorite: asset.is_favorite };
      const decision: Decision = { id: asset.id, kind, previous, ...(album ? { albumId: album.id } : {}) };
      if (kind === "kept" || kind === "discarded") {
        send([asset.id], "review", { state: kind });
        setOverrides((o) => ({ ...o, [asset.id]: { ...o[asset.id], review_state: kind } }));
      } else if (kind === "favorite") {
        send([asset.id], "favorite", { value: !asset.is_favorite });
        setOverrides((o) => ({ ...o, [asset.id]: { ...o[asset.id], is_favorite: !asset.is_favorite } }));
        setHistory((h) => [...h, decision]);
        return; // marcar favorita no pasa a la siguiente
      } else if (kind === "album" && album) {
        send([asset.id], "add_album", { album_id: album.id });
        rememberAlbum(spaceId, album.id);
        showToast(`Añadida a «${album.name}»`);
        setHistory((h) => [...h, decision]);
        return;
      }
      setHistory((h) => [...h, decision]);
      setIndex((i) => i + 1);
    },
    [asset, send, spaceId],
  );

  const undo = useCallback(() => {
    const last = history[history.length - 1];
    if (!last) return;
    setHistory((h) => h.slice(0, -1));
    const position = items.findIndex((i) => i.id === last.id);
    if (position >= 0) setIndex(position);
    if (last.kind === "kept" || last.kind === "discarded")
      send([last.id], "review", { state: last.previous.review_state });
    if (last.kind === "favorite") send([last.id], "favorite", { value: last.previous.is_favorite });
    if (last.kind === "album" && last.albumId) send([last.id], "remove_album", { album_id: last.albumId });
    setOverrides((o) => ({ ...o, [last.id]: { ...o[last.id], ...last.previous } as Partial<AssetItem> }));
  }, [history, items, send]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (picker || (e.target instanceof Element && e.target.closest("input, textarea, select, dialog")))
        return;
      const key = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && key === "z") undo();
      else if (e.ctrlKey || e.metaKey || e.altKey) return;
      else if (key === "arrowright" || key === "v") decide("kept");
      else if (key === "arrowleft" || key === "x") decide("discarded");
      else if (key === "f") decide("favorite");
      else if (key === " ") decide("skip");
      else if (key === "z") undo();
      else if (key === "a") setPicker(true);
      else if (key === "escape") void navigate("/");
      else if (/^[1-9]$/.test(key)) {
        const album = albums.sorted[Number(key) - 1];
        if (album) decide("album", album);
      } else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
    };
  }, [decide, undo, picker, albums.sorted, navigate]);

  // Gestos: derecha vale, izquierda no vale, arriba favorita; doble toque favorita.
  const start = useRef<{ x: number; y: number } | null>(null);
  const [drag, setDrag] = useState({ x: 0, y: 0 });
  const lastTap = useRef(0);
  const onDown = (e: PointerEvent) => {
    start.current = { x: e.clientX, y: e.clientY };
  };
  const onMove = (e: PointerEvent) => {
    if (start.current) setDrag({ x: e.clientX - start.current.x, y: e.clientY - start.current.y });
  };
  const onUp = () => {
    const { x, y } = drag;
    start.current = null;
    setDrag({ x: 0, y: 0 });
    if (Math.abs(x) > SWIPE && Math.abs(x) > Math.abs(y)) decide(x > 0 ? "kept" : "discarded");
    else if (y < -SWIPE && Math.abs(y) > Math.abs(x)) decide("favorite");
    else if (Math.abs(x) < 8 && Math.abs(y) < 8) {
      const now = Date.now();
      if (now - lastTap.current < 300) {
        decide("favorite");
        lastTap.current = 0;
      } else lastTap.current = now;
    }
  };

  if (query.isPending) return <div className={styles.review} aria-busy="true" />;
  if (total === 0)
    return (
      <EmptyState title={t("review.empty.title")} action={<Link to="/subir">Subir fotos</Link>}>
        {t("review.empty.text")}
      </EmptyState>
    );
  if (!asset)
    return (
      <EmptyState title="¡Listo!" action={<Link to="/">Ver las fotos</Link>}>
        Has revisado {total} {total === 1 ? "elemento" : "elementos"}: {counts.kept} valen y{" "}
        {counts.discarded} descartados.
        {history.length > 0 && (
          <>
            {" "}
            <button type="button" className={styles.link} onClick={undo}>
              Deshacer la última
            </button>
          </>
        )}
      </EmptyState>
    );

  const hint = drag.x > SWIPE ? "kept" : drag.x < -SWIPE ? "discarded" : drag.y < -SWIPE ? "favorite" : null;
  return (
    <div className={styles.review} role="region" aria-label="Revisar">
      <header className={styles.top}>
        <Link to="/" className={styles.close} aria-label="Salir de Revisar (Esc)">
          ✕
        </Link>
        <div className={styles.progressText} aria-live="polite">
          {index + 1} de {total}
        </div>
        <progress className={styles.progress} max={total} value={index} aria-label="Progreso" />
      </header>
      <div
        className={styles.stage}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        style={{ transform: `translate(${drag.x}px, ${Math.min(0, drag.y)}px) rotate(${drag.x / 30}deg)` }}
      >
        {asset.kind === "video" ? (
          // Vídeos personales: no existen subtítulos que ofrecer.
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video
            key={asset.id}
            className={styles.media}
            src={`/api/v1/assets/${asset.id}/video`}
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
          />
        ) : (
          <p className={styles.processing}>Procesando…</p>
        )}
        {hint && (
          <div className={`${styles.stamp ?? ""} ${styles[hint] ?? ""}`}>
            {hint === "kept" ? "VALE" : hint === "discarded" ? "NO VALE" : "★"}
          </div>
        )}
      </div>
      <p className={styles.meta}>
        {formatDateTime(asset.taken_at, asset.taken_at_offset)} · {SOURCE_LABEL[asset.source]}
        {asset.kind === "video" && ` · ${formatDuration(asset.duration_ms)}`}
        {asset.is_favorite && " · ★"}
      </p>
      <div className={styles.actions}>
        <button
          type="button"
          className={`${styles.action ?? ""} ${styles.no ?? ""}`}
          onClick={() => decide("discarded")}
          aria-keyshortcuts="ArrowLeft X"
        >
          ✕<span>No vale</span>
        </button>
        <button
          type="button"
          className={styles.action}
          onClick={undo}
          disabled={history.length === 0}
          aria-keyshortcuts="Z"
        >
          ↶<span>Deshacer</span>
        </button>
        <button
          type="button"
          className={styles.action}
          onClick={() => decide("skip")}
          aria-keyshortcuts="Space"
        >
          ⤼<span>Saltar</span>
        </button>
        <button
          type="button"
          className={styles.action}
          aria-pressed={asset.is_favorite}
          onClick={() => decide("favorite")}
          aria-keyshortcuts="F"
        >
          ★<span>Favorita</span>
        </button>
        <button type="button" className={styles.action} onClick={() => setPicker(true)} aria-keyshortcuts="A">
          ▤<span>Álbum</span>
        </button>
        <button
          type="button"
          className={`${styles.action ?? ""} ${styles.yes ?? ""}`}
          onClick={() => decide("kept")}
          aria-keyshortcuts="ArrowRight V"
        >
          ✓<span>Vale</span>
        </button>
      </div>
      {albums.sorted.length > 0 && (
        <div className={styles.recent} aria-label="Álbumes recientes">
          {albums.sorted.slice(0, 9).map((album, i) => (
            <button
              key={album.id}
              type="button"
              className={styles.chip}
              onClick={() => decide("album", album)}
              aria-keyshortcuts={String(i + 1)}
            >
              <kbd>{i + 1}</kbd> {album.name}
            </button>
          ))}
        </div>
      )}
      {picker && (
        <AlbumPicker
          spaceId={spaceId}
          count={1}
          onClose={() => setPicker(false)}
          onPick={(album) => {
            setPicker(false);
            decide("album", album);
          }}
        />
      )}
    </div>
  );
}
