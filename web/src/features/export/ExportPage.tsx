import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type ExportJob } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { isOwner, useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { Alert, Card, PageTitle } from "../../design-system/components/Card";
import { SelectField } from "../../design-system/components/Field";
import { formatBytes } from "../photos/format";
import { useAlbums } from "../selection/albums";
import styles from "../page.module.css";
import { volumeUrl } from "./download";

const STATE: Record<string, string> = {
  queued: "En cola",
  running: "Preparando",
  ready: "Lista",
  failed: "Falló",
  expired: "Caducada",
};

/** Exportar: ZIP ordenado de un álbum, varios o el espacio entero, siempre con los originales. */
export function ExportPage() {
  const { space, withReauth } = useSession();
  const queryClient = useQueryClient();
  const spaceId = space?.id ?? "";
  const albums = useAlbums(spaceId);
  const owner = isOwner(space);
  const [scope, setScope] = useState(owner ? "space" : "albums");
  const [albumIds, setAlbumIds] = useState<string[]>([]);
  const [structure, setStructure] = useState<"album" | "date" | "flat">("album");
  const [naming, setNaming] = useState<"normalized" | "original">("normalized");
  const [include, setInclude] = useState<"kept_pending" | "kept" | "all">("kept_pending");
  const [volume, setVolume] = useState("4");
  const jobs = useQuery({
    queryKey: ["exports", spaceId],
    queryFn: () => api.exports(spaceId),
    enabled: !!space,
    refetchInterval: (q) =>
      q.state.data?.some((j) => j.state === "queued" || j.state === "running") ? 2000 : false,
  });
  const create = useMutation({
    mutationFn: () =>
      withReauth(() =>
        api.createExport(spaceId, {
          target: "zip",
          structure,
          naming,
          include,
          album_ids: scope === "albums" ? albumIds : [],
          volume_bytes: Math.round(Number(volume) * 1024 ** 3),
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["exports", spaceId] }),
  });
  if (!space) return null;
  return (
    <div className={styles.narrow}>
      <PageTitle>Exportar</PageTitle>
      <Card title="Nueva exportación">
        <p className={styles.muted}>
          Siempre los originales, sin recomprimir, en ZIP. Incluye un manifiesto con fechas, álbumes y la
          huella de cada foto. Caduca a los 7 días.
        </p>
        <div className={styles.form}>
          <SelectField
            label="Qué exportar"
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            options={[
              ...(owner ? [{ value: "space", label: `Todo el espacio «${space.name}»` }] : []),
              { value: "albums", label: "Algunos álbumes" },
            ]}
          />
          {scope === "albums" && (
            <fieldset className={styles.form}>
              <legend>Álbumes</legend>
              {albums.data?.length === 0 && (
                <p className={styles.muted}>Este espacio aún no tiene álbumes.</p>
              )}
              {albums.data?.map((a) => (
                <label key={a.id} className={styles.row}>
                  <input
                    type="checkbox"
                    checked={albumIds.includes(a.id)}
                    onChange={(e) =>
                      setAlbumIds((ids) =>
                        e.target.checked ? [...ids, a.id] : ids.filter((i) => i !== a.id),
                      )
                    }
                  />{" "}
                  {a.name} <span className={styles.muted}>({a.count})</span>
                </label>
              ))}
            </fieldset>
          )}
          <SelectField
            label="Carpetas"
            value={structure}
            onChange={(e) => setStructure(e.target.value as typeof structure)}
            options={[
              { value: "album", label: "Por álbum (y «Sin álbum/AAAA/MM»)" },
              { value: "date", label: "Por fecha (AAAA/MM)" },
              { value: "flat", label: "Todo junto" },
            ]}
          />
          <SelectField
            label="Nombre de los ficheros"
            value={naming}
            onChange={(e) => setNaming(e.target.value as typeof naming)}
            options={[
              { value: "normalized", label: "AAAA-MM-DD_HHMMSS_nombre (ordena bien en cualquier sitio)" },
              { value: "original", label: "El original" },
            ]}
          />
          <SelectField
            label="Qué incluir"
            value={include}
            onChange={(e) => setInclude(e.target.value as typeof include)}
            options={[
              { value: "kept_pending", label: "Lo que vale y lo que está sin revisar" },
              { value: "kept", label: "Solo lo que vale" },
              { value: "all", label: "Todo, también lo descartado" },
            ]}
          />
          <SelectField
            label="Tamaño de cada parte"
            value={volume}
            onChange={(e) => setVolume(e.target.value)}
            options={[
              { value: "1", label: "1 GB" },
              { value: "4", label: "4 GB (recomendado)" },
              { value: "16", label: "16 GB" },
            ]}
          />
          {create.isError && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
          <Button
            variant="primary"
            disabled={create.isPending || (scope === "albums" && albumIds.length === 0)}
            onClick={() => create.mutate()}
          >
            Preparar la exportación
          </Button>
        </div>
      </Card>
      <Card title="Exportaciones">
        {jobs.data?.length === 0 && <p className={styles.muted}>Aún no hay ninguna.</p>}
        <ul className={styles.list}>
          {jobs.data?.map((job) => (
            <ExportRow key={job.id} spaceId={spaceId} job={job} />
          ))}
        </ul>
      </Card>
    </div>
  );
}

function ExportRow({ spaceId, job }: { spaceId: string; job: ExportJob }) {
  const queryClient = useQueryClient();
  const format = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short" });
  const busy = job.state === "queued" || job.state === "running";
  return (
    <li className={styles.row}>
      <div className={styles.grow}>
        <strong>{STATE[job.state] ?? job.state}</strong> · {job.total_items} elementos ·{" "}
        {formatBytes(job.total_bytes)}
        <div className={styles.muted}>
          {format.format(new Date(job.created_at))} · caduca el {format.format(new Date(job.expires_at))}
        </div>
        {busy && (
          <progress
            max={1}
            value={job.progress}
            aria-label="Progreso de la exportación"
            style={{ width: "100%" }}
          />
        )}
        {job.error && <Alert tone="danger">{job.error}</Alert>}
        {job.state === "ready" && (
          <ul className={styles.list}>
            {job.files.map((f) => (
              <li key={String(f.number)}>
                <a href={volumeUrl(spaceId, job.id, Number(f.number))} download>
                  {String(f.name)}
                </a>{" "}
                <span className={styles.muted}>({formatBytes(Number(f.size))})</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {!busy && (
        <Button
          variant="ghost"
          onClick={() =>
            void api
              .deleteExport(spaceId, job.id)
              .then(() => queryClient.invalidateQueries({ queryKey: ["exports", spaceId] }))
          }
        >
          Borrar
        </Button>
      )}
    </li>
  );
}
