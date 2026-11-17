import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, type AssetItem } from "../../api/client";
import type { useRandomPick } from "./random";
import { dayKey, formatDay, placeLabel } from "./format";
import styles from "./photos.module.css";

const HIDDEN_KEY = "carrete:recuerdo-oculto";

function readHidden() {
  try {
    return localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

function writeHidden(value: boolean) {
  try {
    if (value) localStorage.setItem(HIDDEN_KEY, "1");
    else localStorage.removeItem(HIDDEN_KEY);
  } catch {
    // Sin almacenamiento local: vuelve a salir al recargar.
  }
}

export function RandomPick({
  query,
  onOpen,
}: {
  query: ReturnType<typeof useRandomPick>;
  onOpen: (asset: AssetItem) => void;
}) {
  const [hidden, setHidden] = useState(readHidden);
  const asset = query.data;
  const detail = useQuery({
    queryKey: ["asset", asset?.id],
    queryFn: () => api.asset(asset?.id ?? ""),
    enabled: !!asset && !hidden,
  });
  if (!asset) return null;
  if (hidden)
    return (
      <button
        type="button"
        className={styles.memoryShow}
        onClick={() => {
          writeHidden(false);
          setHidden(false);
          void query.refetch();
        }}
      >
        Ver un recuerdo al azar
      </button>
    );
  const place = detail.data ? placeLabel(detail.data) : null;
  return (
    <section className={styles.memory} aria-label="Un recuerdo al azar">
      <button
        type="button"
        className={styles.memoryPhoto}
        onClick={() => onOpen(asset)}
        aria-label="Abrir el recuerdo"
      >
        <img key={asset.id} src={`/api/v1/assets/${asset.id}/preview`} alt="" draggable={false} />
      </button>
      <div className={styles.memoryText}>
        <span className={styles.memoryKicker}>Un recuerdo</span>
        <span className={styles.memoryWhen}>{formatDay(dayKey(asset.taken_at))}</span>
        {place && <span className={styles.memoryWhere}>{place}</span>}
      </div>
      <div className={styles.memoryActions}>
        <button
          type="button"
          className={styles.memoryButton}
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          Otra
        </button>
        <button
          type="button"
          className={styles.memoryButton}
          onClick={() => {
            writeHidden(true);
            setHidden(true);
          }}
          aria-label="Ocultar el recuerdo"
        >
          Ocultar
        </button>
      </div>
    </section>
  );
}
