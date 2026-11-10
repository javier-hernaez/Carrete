import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";

import { api } from "../../api/client";
import { useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { SelectField, TextField } from "../../design-system/components/Field";
import { activeCount, readFilters } from "./filters";
import styles from "./photos.module.css";

const KEYS = ["estado", "fav", "tipo", "origen", "persona", "de", "a", "dudosa", "sin-album", "q"];

export function FiltersBar({ hideState = false }: { hideState?: boolean }) {
  const { space } = useSession();
  const [params, setParams] = useSearchParams();
  const filters = readFilters(params);
  const members = useQuery({
    queryKey: ["members", space?.id],
    queryFn: () => api.members(space?.id ?? ""),
    enabled: !!space,
    staleTime: 60_000,
  });
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("desde");
    setParams(next, { replace: true });
  };
  const count = activeCount(filters);
  return (
    <details className={styles.filters} open={count > 0}>
      <summary className={styles.filtersSummary}>Filtros{count ? ` (${count})` : ""}</summary>
      <div className={styles.filtersBody}>
        {!hideState && (
          <SelectField
            label="Estado"
            value={filters.estado}
            onChange={(e) => set("estado", e.target.value)}
            options={[
              { value: "", label: "Sin descartadas" },
              { value: "pendiente", label: "Sin revisar" },
              { value: "vale", label: "Valen" },
              { value: "descartada", label: "Descartadas" },
              { value: "todas", label: "Todas" },
            ]}
          />
        )}
        <SelectField
          label="Tipo"
          value={filters.tipo}
          onChange={(e) => set("tipo", e.target.value)}
          options={[
            { value: "", label: "Fotos y vídeos" },
            { value: "photo", label: "Solo fotos" },
            { value: "video", label: "Solo vídeos" },
          ]}
        />
        <SelectField
          label="Origen"
          value={filters.origen}
          onChange={(e) => set("origen", e.target.value)}
          options={[
            { value: "", label: "Cualquiera" },
            { value: "camera", label: "Cámara" },
            { value: "whatsapp", label: "WhatsApp" },
            { value: "screenshot", label: "Capturas" },
            { value: "other", label: "Otro" },
          ]}
        />
        <SelectField
          label="Subida por"
          value={filters.persona}
          onChange={(e) => set("persona", e.target.value)}
          options={[
            { value: "", label: "Cualquiera" },
            ...(members.data ?? []).map((m) => ({ value: m.user_id, label: m.display_name })),
          ]}
        />
        <TextField label="Desde" type="date" value={filters.de} onChange={(e) => set("de", e.target.value)} />
        <TextField label="Hasta" type="date" value={filters.a} onChange={(e) => set("a", e.target.value)} />
        <TextField
          label="Buscar"
          type="search"
          placeholder="Nombre o descripción"
          value={filters.q}
          onChange={(e) => set("q", e.target.value)}
        />
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={filters.fav}
            onChange={(e) => set("fav", e.target.checked ? "1" : "")}
          />{" "}
          Solo favoritas
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={filters.dudosa}
            onChange={(e) => set("dudosa", e.target.checked ? "1" : "")}
          />{" "}
          Fecha dudosa
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={filters.sinAlbum}
            onChange={(e) => set("sin-album", e.target.checked ? "1" : "")}
          />{" "}
          Sin álbum
        </label>
        {count > 0 && (
          <Button
            variant="ghost"
            onClick={() => {
              const next = new URLSearchParams(params);
              KEYS.forEach((k) => {
                next.delete(k);
              });
              setParams(next, { replace: true });
            }}
          >
            Quitar filtros
          </Button>
        )}
      </div>
    </details>
  );
}
