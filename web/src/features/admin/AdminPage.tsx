import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type AdminUser } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { useSession } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { Alert, Card, PageTitle } from "../../design-system/components/Card";
import { TextField } from "../../design-system/components/Field";
import { formatBytes } from "../photos/format";
import styles from "../page.module.css";

const dateTime = new Intl.DateTimeFormat("es", { dateStyle: "short", timeStyle: "short" });

export function AdminPage() {
  const { me } = useSession();
  if (!me.is_admin) return <Alert tone="danger">Solo el administrador puede ver esta página.</Alert>;
  return (
    <div>
      <PageTitle>Administración</PageTitle>
      <StatusCard />
      <NoticesCard />
      <PeopleCard />
      <AuditCard />
    </div>
  );
}

function NoticesCard() {
  const queryClient = useQueryClient();
  const notices = useQuery({ queryKey: ["admin", "notices"], queryFn: api.adminNotices });
  const ack = useMutation({
    mutationFn: api.adminAckNotice,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "notices"] }),
  });
  return (
    <Card title="Avisos">
      {notices.data?.length === 0 && <p className={styles.muted}>No hay avisos pendientes.</p>}
      <ul className={styles.list}>
        {notices.data?.map((n) => (
          <li key={n.id} className={styles.row}>
            <div className={styles.grow}>
              <Alert
                tone={n.severity === "critical" ? "danger" : n.severity === "warning" ? "warning" : "info"}
              >
                {n.message}
              </Alert>
              <div className={styles.muted}>{dateTime.format(new Date(n.created_at))}</div>
            </div>
            <Button variant="ghost" onClick={() => ack.mutate(n.id)}>
              Entendido
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function PeopleCard() {
  const { me, withReauth } = useSession();
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["admin", "users"], queryFn: api.adminUsers });
  const [link, setLink] = useState<string>();
  const [error, setError] = useState<string>();
  const run = async (action: () => Promise<unknown>) => {
    setError(undefined);
    try {
      await withReauth(action);
      await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  const reset = (u: AdminUser, totp: boolean) =>
    run(async () => {
      setLink((await api.adminReset(u.id, totp)).url);
    });
  return (
    <Card
      title="Personas"
      actions={
        <Button onClick={() => void run(async () => setLink((await api.adminInvite()).url))}>
          Invitar sin espacio
        </Button>
      }
    >
      {error && <Alert tone="danger">{error}</Alert>}
      {link && (
        <>
          <p className={styles.muted}>Enlace de un solo uso. Envíaselo por un canal de confianza:</p>
          <p className={styles.link}>{link}</p>
        </>
      )}
      <ul className={styles.list}>
        {users.data?.map((u) => (
          <li key={u.id} className={styles.row}>
            <div className={styles.grow}>
              <strong>{u.display_name}</strong> <span className={styles.muted}>@{u.username}</span>
              {u.is_admin && <span className={styles.badge}>Admin</span>}
              {!u.is_active && <span className={styles.badge}>Desactivada</span>}
              <div className={styles.muted}>
                {u.spaces} espacios · {u.has_totp ? "2FA activada" : "sin 2FA"} · último acceso{" "}
                {u.last_login_at ? dateTime.format(new Date(u.last_login_at)) : "nunca"}
              </div>
            </div>
            <details>
              <summary>Acciones</summary>
              <div className={styles.form}>
                <Button variant="ghost" onClick={() => void reset(u, false)}>
                  Enlace para nueva contraseña
                </Button>
                <Button variant="ghost" onClick={() => void reset(u, true)}>
                  Restablecer contraseña y 2FA
                </Button>
                <Button variant="ghost" onClick={() => void run(() => api.adminRevokeSessions(u.id))}>
                  Cerrar sus sesiones
                </Button>
                {u.id !== me.id && (
                  <Button
                    variant="ghost"
                    onClick={() => void run(() => api.adminSetActive(u.id, !u.is_active))}
                  >
                    {u.is_active ? "Desactivar cuenta" : "Reactivar cuenta"}
                  </Button>
                )}
              </div>
            </details>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function AuditCard() {
  const [action, setAction] = useState("");
  const [cursor, setCursor] = useState<string | undefined>();
  const params: Record<string, string> = { limit: "50" };
  if (action) params.action = action;
  if (cursor) params.cursor = cursor;
  const audit = useQuery({
    queryKey: ["admin", "audit", action, cursor],
    queryFn: () => api.adminAudit(params),
  });
  return (
    <Card title="Registro de auditoría">
      <TextField
        label="Filtrar por acción"
        placeholder="auth.login_failed, space., export.…"
        value={action}
        onChange={(e) => {
          setAction(e.target.value);
          setCursor(undefined);
        }}
      />
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Cuándo</th>
              <th scope="col">Quién</th>
              <th scope="col">Acción</th>
              <th scope="col">IP</th>
              <th scope="col">Detalle</th>
            </tr>
          </thead>
          <tbody>
            {audit.data?.items.map((e) => (
              <tr key={e.id}>
                <td>{dateTime.format(new Date(e.occurred_at))}</td>
                <td>{e.actor_name ?? "—"}</td>
                <td>{e.action}</td>
                <td>{e.ip ?? ""}</td>
                <td>{Object.keys(e.detail).length ? JSON.stringify(e.detail) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.inline}>
        {cursor && <Button onClick={() => setCursor(undefined)}>Más recientes</Button>}
        {audit.data?.next_cursor && (
          <Button onClick={() => setCursor(audit.data.next_cursor ?? undefined)}>Más antiguos</Button>
        )}
      </div>
    </Card>
  );
}

function age(iso: string | null | undefined): string {
  if (!iso) return "nunca";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "hace un momento";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `hace ${hours} h` : `hace ${Math.round(hours / 24)} días`;
}

function StatusCard() {
  const status = useQuery({
    queryKey: ["admin", "status"],
    queryFn: api.adminStatus,
    refetchInterval: 60_000,
  });
  const s = status.data;
  if (!s)
    return (
      <Card title="Estado">
        {status.isError ? <Alert tone="danger">{errorMessage(status.error)}</Alert> : <p>Cargando…</p>}
      </Card>
    );
  const used = s.disk.total ? s.disk.used / s.disk.total : 0;
  const db = s.backup.database;
  return (
    <Card title="Estado">
      {s.backup.agent.same_disk !== false && (
        <Alert tone="warning">
          Las copias están en el mismo disco que las fotos: protegen de errores y borrados, no de la rotura
          del disco, el robo o un incendio.
        </Alert>
      )}
      <div>
        <strong>Disco:</strong> {formatBytes(s.disk.used)} de {formatBytes(s.disk.total)} (
        {Math.round(used * 100)} %) · libres {formatBytes(s.disk.free)}
        <progress
          className={styles.grow}
          max={1}
          value={used}
          aria-label="Uso del disco"
          style={{ width: "100%" }}
        />
      </div>
      {s.storage.originals !== undefined && (
        <p className={styles.muted}>
          Originales {formatBytes(s.storage.originals)} · derivados {formatBytes(s.storage.derivatives ?? 0)}{" "}
          · exportaciones {formatBytes(s.storage.exports ?? 0)}
        </p>
      )}
      {(s.storage.spaces?.length ?? 0) > 0 && (
        <ul className={styles.list} aria-label="Espacio por espacio">
          {s.storage.spaces?.map((sp) => (
            <li key={sp.id} className={styles.row}>
              <span className={styles.grow}>{sp.name}</span>
              <span className={styles.muted}>
                {sp.count.toLocaleString("es")} elementos · {formatBytes(sp.bytes)}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p>
        <strong>Copia de la base de datos:</strong>{" "}
        {db ? `${db.ok ? "correcta" : "FALLIDA"}, ${age(db.finished_at)}` : "aún ninguna"}
        <br />
        <strong>Originales sin copia:</strong> {s.backup.pending_originals}
        <br />
        <strong>Integridad:</strong>{" "}
        {s.integrity
          ? `${s.integrity.ok ? "todo bien" : `${s.integrity.problems.length} problemas`} (${s.integrity.checked} revisados, ${age(s.integrity.finished_at)})`
          : "aún no verificada"}
        <br />
        <strong>Cola de tareas:</strong>{" "}
        {Object.entries(s.queue)
          .map(([k, v]) => `${k} ${v}`)
          .join(" · ") || "vacía"}
        <br />
        <strong>Versión:</strong> {s.version}
      </p>
      {s.failed_jobs.length > 0 && (
        <details>
          <summary>Tareas fallidas ({s.failed_jobs.length})</summary>
          <ul className={styles.list}>
            {s.failed_jobs.map((j, i) => (
              <li key={i} className={styles.muted}>
                {j.kind}: {j.error}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}
