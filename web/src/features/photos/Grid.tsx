import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { AssetItem } from "../../api/client";
import { dayKey, formatDay } from "./format";
import styles from "./photos.module.css";
import { Thumb } from "./Thumb";

type Row =
  | { type: "header"; key: string; label: string; ids: string[] }
  | { type: "cells"; key: string; items: { asset: AssetItem; index: number }[] };

interface GridProps {
  items: AssetItem[];
  hasMore: boolean;
  loadMore: () => void;
  onOpen: (index: number) => void;
  selected?: ReadonlySet<string>;
  onToggle?: (index: number, event: { shiftKey: boolean }) => void;
  onSelectDay?: (ids: string[]) => void;
  dayAction?: (ids: string[]) => ReactNode;
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [top, setTop] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    setTop(el.getBoundingClientRect().top + window.scrollY);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) {
        setWidth(entry.contentRect.width);
        setTop(entry.target.getBoundingClientRect().top + window.scrollY);
      }
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, []);
  return { ref, width: width || 960, top };
}

/**
 * Cuadrícula agrupada por días y virtualizada: solo existen en el DOM las filas visibles,
 * así que se mueve con fluidez aunque el espacio tenga decenas de miles de elementos.
 */
export function Grid({ items, hasMore, loadMore, onOpen, selected, onToggle, dayAction }: GridProps) {
  const { ref, width, top: offsetTop } = useWidth();
  const target = width < 600 ? 104 : 168;
  const columns = Math.max(3, Math.floor(width / target));
  const gap = 3;
  const cell = (width - gap * (columns - 1)) / columns;

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    let current: { asset: AssetItem; index: number }[] = [];
    let currentDay = "";
    let header: Extract<Row, { type: "header" }> | null = null;
    const flush = () => {
      for (let i = 0; i < current.length; i += columns) {
        out.push({ type: "cells", key: `${currentDay}-${i}`, items: current.slice(i, i + columns) });
      }
      current = [];
    };
    items.forEach((asset, index) => {
      const day = dayKey(asset.taken_at);
      if (day !== currentDay) {
        flush();
        currentDay = day;
        header = { type: "header", key: `h-${day}`, label: formatDay(day), ids: [] };
        out.push(header);
      }
      header?.ids.push(asset.id);
      current.push({ asset, index });
    });
    flush();
    return out;
  }, [items, columns]);

  const virtualizer = useWindowVirtualizer({
    count: rows.length,
    estimateSize: (i) => (rows[i]?.type === "header" ? 48 : cell + gap),
    overscan: 8,
    scrollMargin: offsetTop,
  });
  const virtualRows = virtualizer.getVirtualItems();
  const last = virtualRows[virtualRows.length - 1];

  useEffect(() => {
    virtualizer.measure();
  }, [cell, virtualizer]);

  useEffect(() => {
    if (last && hasMore && last.index >= rows.length - 6) loadMore();
  }, [last, hasMore, rows.length, loadMore]);

  return (
    <div ref={ref} className={styles.grid} style={{ height: virtualizer.getTotalSize() }}>
      {virtualRows.map((v) => {
        const row = rows[v.index];
        if (!row) return null;
        const top = v.start - virtualizer.options.scrollMargin;
        if (row.type === "header") {
          return (
            <div
              key={row.key}
              className={styles.dayHeader}
              style={{ transform: `translateY(${top}px)`, height: 48 }}
            >
              <h2 className={styles.dayTitle}>{row.label}</h2>
              {dayAction?.(row.ids)}
            </div>
          );
        }
        return (
          <div
            key={row.key}
            className={styles.row}
            style={{
              transform: `translateY(${top}px)`,
              gridTemplateColumns: `repeat(${columns}, ${cell}px)`,
              gap,
              height: cell,
            }}
          >
            {row.items.map(({ asset, index }) => (
              <Thumb
                key={asset.id}
                asset={asset}
                label={`${asset.kind === "video" ? "Vídeo" : "Foto"} del ${formatDay(dayKey(asset.taken_at))}, ${asset.taken_at.slice(11, 16)}`}
                selected={selected?.has(asset.id)}
                onOpen={() =>
                  onToggle && selected && selected.size > 0
                    ? onToggle(index, { shiftKey: false })
                    : onOpen(index)
                }
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
