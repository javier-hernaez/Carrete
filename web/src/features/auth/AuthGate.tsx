import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { api, ApiError } from "../../api/client";
import { errorMessage, hasCode } from "../../app/errors";
import { SessionContext, type SessionValue } from "../../app/session";
import { Button } from "../../design-system/components/Button";
import { TextField } from "../../design-system/components/Field";
import { LogoMark } from "../../design-system/components/Logo";
import { Dialog } from "../../design-system/components/Dialog";
import { EnrollScreen, LoginScreen, SetupScreen, TotpScreen } from "./screens";
import styles from "./auth.module.css";

function Splash() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Cargando">
      <LogoMark size={48} />
    </div>
  );
}

/** Decide qué ve la persona: asistente, entrar, segundo factor, activarlo o la aplicación. */
export function AuthGate({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  const unauthenticated = me.error instanceof ApiError && me.error.status === 401;
  const setupState = useQuery({ queryKey: ["setup"], queryFn: api.setupState, enabled: unauthenticated });
  const [reauth, setReauth] = useState<{ resolve: () => void; reject: (e: unknown) => void } | null>(null);

  const withReauth = useCallback(async <T,>(action: () => Promise<T>): Promise<T> => {
    try {
      return await action();
    } catch (error) {
      if (!hasCode(error, "reauth_required")) throw error;
      await new Promise<void>((resolve, reject) => {
        setReauth({ resolve, reject });
      });
      return action();
    }
  }, []);

  const value = useMemo<SessionValue | null>(() => {
    if (!me.data || me.data.stage !== "full") return null;
    const data = me.data;
    const space = data.spaces.find((s) => s.id === data.current_space_id) ?? null;
    return {
      me: data,
      space,
      setSpace: (id: string) => {
        queryClient.setQueryData(["me"], { ...data, current_space_id: id });
        void api.updateMe({ last_space_id: id });
      },
      refresh: () => queryClient.invalidateQueries({ queryKey: ["me"] }),
      withReauth,
    };
  }, [me.data, queryClient, withReauth]);

  if (me.isPending || (unauthenticated && setupState.isPending)) return <Splash />;
  if (unauthenticated) return setupState.data?.needed ? <SetupScreen /> : <LoginScreen />;
  if (me.isError) {
    return (
      <div className={styles.page} role="alert">
        <p>{errorMessage(me.error)}</p>
        <Button onClick={() => void me.refetch()}>Reintentar</Button>
      </div>
    );
  }
  if (me.data.stage === "totp") return <TotpScreen />;
  if (me.data.stage === "enroll") return <EnrollScreen />;
  if (!value) return <Splash />;

  return (
    <SessionContext.Provider value={value}>
      {children}
      {reauth && (
        <ReauthDialog
          hasTotp={me.data.has_totp}
          onDone={() => {
            reauth.resolve();
            setReauth(null);
          }}
          onCancel={() => {
            reauth.reject(new Error("cancelado"));
            setReauth(null);
          }}
        />
      )}
    </SessionContext.Provider>
  );
}

function ReauthDialog({
  hasTotp,
  onDone,
  onCancel,
}: {
  hasTotp: boolean;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.reauth(password, hasTotp ? code : undefined);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog title="Confirma que eres tú" onClose={onCancel}>
      <form className={styles.form} onSubmit={(e) => void submit(e)}>
        <p>Es una acción sensible: vuelve a introducir tu contraseña.</p>
        <TextField
          label="Contraseña"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {hasTotp && (
          <TextField
            label="Código de verificación"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
        )}
        {error && <p role="alert">{error}</p>}
        <Button type="submit" variant="primary" disabled={busy}>
          Confirmar
        </Button>
      </form>
    </Dialog>
  );
}
