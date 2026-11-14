import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "../../api/client";
import { errorMessage } from "../../app/errors";
import { useSession } from "../../app/session";
import { applyTheme } from "../../app/theme";
import { Button } from "../../design-system/components/Button";
import { Alert, Card, PageTitle } from "../../design-system/components/Card";
import { SelectField, TextField } from "../../design-system/components/Field";
import { RecoveryCodes } from "../auth/RecoveryCodes";
import { PasskeysCard } from "../passkeys/PasskeysCard";
import styles from "../page.module.css";

export function SettingsPage() {
  return (
    <div className={styles.narrow}>
      <PageTitle>Ajustes</PageTitle>
      <ProfileCard />
      <PasswordCard />
      <TwoFactorCard />
      <PasskeysCard />
      <AndroidCard />
      <SessionsCard />
      <LogoutCard />
    </div>
  );
}

function ProfileCard() {
  const { me, refresh } = useSession();
  const [name, setName] = useState(me.display_name);
  const theme = (me.preferences.theme as string | undefined) ?? "system";
  const save = useMutation({ mutationFn: () => api.updateMe({ display_name: name }), onSuccess: refresh });
  const setTheme = (value: string) => {
    applyTheme(value);
    void api.updateMe({ theme: value as "system" | "light" | "dark" }).then(refresh);
  };
  return (
    <Card title="Perfil">
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <TextField
          label="Nombre"
          value={name}
          onChange={(e) => setName(e.target.value)}
          hint={`Usuario: ${me.username}`}
        />
        {save.isError && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
        <Button type="submit" disabled={save.isPending || name === me.display_name}>
          Guardar
        </Button>
      </form>
      <SelectField
        label="Apariencia"
        value={theme}
        onChange={(e) => setTheme(e.target.value)}
        options={[
          { value: "system", label: "Como el sistema" },
          { value: "light", label: "Clara" },
          { value: "dark", label: "Oscura" },
        ]}
      />
    </Card>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useMutation({ mutationFn: () => api.changePassword(current, next) });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    change.mutate(undefined, {
      onSuccess: () => {
        setCurrent("");
        setNext("");
      },
    });
  };
  return (
    <Card title="Contraseña">
      <form className={styles.form} onSubmit={submit}>
        <TextField
          label="Contraseña actual"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          required
        />
        <TextField
          label="Nueva contraseña"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          minLength={12}
          hint="Al menos 12 caracteres."
          required
        />
        {change.isError && <Alert tone="danger">{errorMessage(change.error)}</Alert>}
        {change.isSuccess && (
          <Alert tone="success">
            Contraseña cambiada. Se han cerrado {change.data.sessions_closed} sesiones en otros dispositivos.
          </Alert>
        )}
        <Button type="submit" disabled={change.isPending}>
          Cambiar contraseña
        </Button>
      </form>
    </Card>
  );
}

function TwoFactorCard() {
  const { me, withReauth, refresh } = useSession();
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<string>();
  const regenerate = async () => {
    try {
      setCodes((await withReauth(api.regenerateCodes)).recovery_codes);
      await refresh();
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  return (
    <Card title="Verificación en dos pasos">
      {me.has_totp ? (
        <p>Activada. Te quedan {me.recovery_codes_left} códigos de recuperación.</p>
      ) : (
        <p>Desactivada.</p>
      )}
      {me.has_totp && me.recovery_codes_left <= 3 && (
        <Alert tone="warning">Te quedan pocos códigos de recuperación: genera unos nuevos.</Alert>
      )}
      {error && <Alert tone="danger">{error}</Alert>}
      {codes ? (
        <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />
      ) : (
        me.has_totp && (
          <Button onClick={() => void regenerate()}>Generar nuevos códigos de recuperación</Button>
        )
      )}
    </Card>
  );
}

function describeAgent(ua: string | null): string {
  if (!ua) return "Dispositivo desconocido";
  const browser = /Firefox/.test(ua)
    ? "Firefox"
    : /Edg\//.test(ua)
      ? "Edge"
      : /Chrome/.test(ua)
        ? "Chrome"
        : /Safari/.test(ua)
          ? "Safari"
          : "Navegador";
  const os = /Android/.test(ua)
    ? "Android"
    : /iPhone|iPad/.test(ua)
      ? "iOS"
      : /Windows/.test(ua)
        ? "Windows"
        : /Mac OS/.test(ua)
          ? "macOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "";
  return os ? `${browser} en ${os}` : browser;
}

function SessionsCard() {
  const queryClient = useQueryClient();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: api.sessions });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["sessions"] });
  const revoke = useMutation({ mutationFn: api.revokeSession, onSuccess: invalidate });
  const revokeOthers = useMutation({ mutationFn: api.revokeOtherSessions, onSuccess: invalidate });
  const format = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short" });
  return (
    <Card title="Sesiones y dispositivos">
      <ul className={styles.list}>
        {sessions.data?.map((s) => (
          <li key={s.id} className={styles.row}>
            <div className={styles.grow}>
              <strong>{s.device_name ?? describeAgent(s.user_agent)}</strong>
              {s.current && <span className={styles.badge}>Esta</span>}
              <div className={styles.muted}>Última actividad: {format.format(new Date(s.last_seen_at))}</div>
            </div>
            {!s.current && (
              <Button variant="ghost" onClick={() => revoke.mutate(s.id)}>
                Cerrar
              </Button>
            )}
          </li>
        ))}
      </ul>
      {(sessions.data?.length ?? 0) > 1 && (
        <Button onClick={() => revokeOthers.mutate()}>Cerrar todas las demás</Button>
      )}
    </Card>
  );
}

function LogoutCard() {
  const queryClient = useQueryClient();
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear();
      window.location.assign("/");
    },
  });
  return (
    <Button variant="secondary" onClick={() => logout.mutate()}>
      Cerrar sesión
    </Button>
  );
}

/** Distribución de la app sin tiendas: APK desde aquí y QR para configurarla. */
function AndroidCard() {
  const app = useQuery({ queryKey: ["android"], queryFn: api.androidApp });
  if (!app.data?.available) return null;
  return (
    <Card title="App para el móvil (Android)">
      <p className={styles.muted}>
        Para subir desde WhatsApp o la galería con «Compartir», y para que las subidas sigan aunque apagues la
        pantalla. Versión {app.data.version_name ?? "—"}.
      </p>
      <ol className={styles.form}>
        <li>
          <a href="/api/v1/app/android/apk" download>
            Descargar la app (APK)
          </a>{" "}
          y ábrela en el móvil. Android pedirá permiso para instalar apps de esta fuente.
        </li>
        <li>Al abrirla, escanea este código con la cámara del móvil para poner la dirección del servidor:</li>
      </ol>
      <img
        src="/api/v1/app/android/setup-qr"
        alt="Código QR con la dirección del servidor de Carrete"
        width={200}
        height={200}
      />
    </Card>
  );
}
