import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { api } from "../../api/client";
import { errorMessage, UserError } from "../../app/errors";
import { Button } from "../../design-system/components/Button";
import { Alert } from "../../design-system/components/Card";
import { TextField } from "../../design-system/components/Field";
import { RoleSummary } from "../../app/RoleHelp";
import { ADMIN_NOTE } from "../../app/roles";
import { AuthLayout } from "./AuthLayout";
import styles from "./auth.module.css";
import { EnrollTotp } from "./EnrollTotp";
import { credentialToJson, passkeyError, passkeysSupported, requestOptions } from "../passkeys/webauthn";

const ROLE_LABEL: Record<string, string> = {
  owner: "propietario",
  collaborator: "colaborador",
  viewer: "lector",
};

const PASSWORD_HINT = "Al menos 12 caracteres. Mejor una frase que solo tú recuerdes.";

function useRefreshMe() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["me"] });
}

export function LoginScreen() {
  const refresh = useRefreshMe();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({ mutationFn: () => api.login(username, password), onSuccess: refresh });
  const passkey = useMutation({
    mutationFn: async () => {
      const { challenge_id, options } = await api.passkeyLoginOptions();
      let credential: Credential | null;
      try {
        credential = await navigator.credentials.get({ publicKey: requestOptions(options) });
      } catch (e) {
        throw new UserError(passkeyError(e));
      }
      if (!(credential instanceof PublicKeyCredential)) throw new UserError("No se eligió ninguna llave");
      return api.passkeyLogin(challenge_id, credentialToJson(credential));
    },
    onSuccess: refresh,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate();
  };
  return (
    <AuthLayout title="Entrar">
      <form className={styles.form} onSubmit={submit}>
        {login.isError && <Alert tone="danger">{errorMessage(login.error)}</Alert>}
        {passkey.isError && <Alert tone="danger">{errorMessage(passkey.error)}</Alert>}
        <TextField
          label="Usuario"
          autoComplete="username"
          autoCapitalize="none"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <TextField
          label="Contraseña"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button type="submit" variant="primary" disabled={login.isPending}>
          Entrar
        </Button>
        {passkeysSupported() && (
          <Button type="button" disabled={passkey.isPending} onClick={() => passkey.mutate()}>
            Entrar con una llave de acceso
          </Button>
        )}
      </form>
      <p className={styles.links}>
        ¿Has olvidado la contraseña? Pide al administrador un enlace para restablecerla.
      </p>
    </AuthLayout>
  );
}

export function TotpScreen() {
  const refresh = useRefreshMe();
  const [code, setCode] = useState("");
  const verify = useMutation({ mutationFn: () => api.verifyTotp(code), onSuccess: refresh });
  const logout = useMutation({ mutationFn: api.logout, onSuccess: refresh });
  return (
    <AuthLayout
      title="Verificación en dos pasos"
      intro="Escribe el código de tu app de autenticación, o uno de tus códigos de recuperación."
    >
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          verify.mutate();
        }}
      >
        <TextField
          label="Código"
          inputMode="text"
          autoComplete="one-time-code"
          autoCapitalize="none"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          error={verify.isError ? errorMessage(verify.error) : undefined}
          required
        />
        <Button type="submit" variant="primary" disabled={verify.isPending}>
          Continuar
        </Button>
        <Button variant="ghost" onClick={() => logout.mutate()}>
          Cancelar
        </Button>
      </form>
    </AuthLayout>
  );
}

export function EnrollScreen() {
  const refresh = useRefreshMe();
  return (
    <AuthLayout
      title="Protege tu cuenta"
      intro="Carrete está en internet: además de la contraseña, pedirá un código de tu móvil."
    >
      <EnrollTotp onDone={() => void refresh()} />
    </AuthLayout>
  );
}

export function SetupScreen() {
  const refresh = useRefreshMe();
  const [form, setForm] = useState({
    token: "",
    username: "",
    display_name: "",
    password: "",
    space_name: "Pareja",
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });
  const setup = useMutation({ mutationFn: () => api.setup(form), onSuccess: refresh });
  return (
    <AuthLayout
      title="Bienvenido a Carrete"
      intro={
        <>
          Vamos a crear la cuenta de administrador. El <strong>código de arranque</strong> está en el registro
          del servidor: <code>docker compose logs app</code>.
        </>
      }
    >
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          setup.mutate();
        }}
      >
        {setup.isError && <Alert tone="danger">{errorMessage(setup.error)}</Alert>}
        <TextField
          label="Código de arranque"
          autoComplete="off"
          value={form.token}
          onChange={set("token")}
          required
        />
        <TextField
          label="Tu nombre"
          autoComplete="name"
          value={form.display_name}
          onChange={set("display_name")}
          required
        />
        <TextField
          label="Usuario"
          autoComplete="username"
          autoCapitalize="none"
          value={form.username}
          onChange={set("username")}
          hint="Con el que entrarás. Letras, números, puntos o guiones."
          required
        />
        <TextField
          label="Contraseña"
          type="password"
          autoComplete="new-password"
          value={form.password}
          onChange={set("password")}
          hint={PASSWORD_HINT}
          minLength={12}
          required
        />
        <TextField
          label="Primer espacio"
          value={form.space_name}
          onChange={set("space_name")}
          hint="Por ejemplo «Pareja» o «Familia». Podrás crear más."
          required
        />
        <Button type="submit" variant="primary" disabled={setup.isPending}>
          Crear cuenta
        </Button>
      </form>
    </AuthLayout>
  );
}

export function InviteScreen() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const preview = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => api.invitationPreview(token),
    retry: false,
  });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });
  const [form, setForm] = useState({ username: "", display_name: "", password: "" });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });
  const accept = useMutation({
    mutationFn: () => api.acceptInvitation(token, form),
    onSuccess: async (result) => {
      if (result.space_id) await api.updateMe({ last_space_id: result.space_id }).catch(() => undefined);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      await navigate("/", { replace: true });
    },
  });

  if (preview.isError) {
    return (
      <AuthLayout title="Invitación no válida" intro={errorMessage(preview.error)}>
        <Link to="/">Ir a Carrete</Link>
      </AuthLayout>
    );
  }
  const data = preview.data;
  const loggedIn = me.data?.stage === "full";
  const intro = data
    ? data.space_name
      ? `${data.invited_by ?? "Alguien"} te invita al espacio «${data.space_name}» como ${ROLE_LABEL[data.role ?? ""] ?? data.role}.`
      : `${data.invited_by ?? "Alguien"} te invita a Carrete.`
    : "Cargando…";
  return (
    <AuthLayout title="Te han invitado" intro={intro}>
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          accept.mutate();
        }}
      >
        {data?.space_name && data.role && (
          <>
            <RoleSummary role={data.role} />
            <p className={styles.note}>{ADMIN_NOTE}</p>
          </>
        )}
        {accept.isError && <Alert tone="danger">{errorMessage(accept.error)}</Alert>}
        {loggedIn ? (
          <p>
            Has iniciado sesión como {me.data?.display_name}. Al aceptar, el espacio se añadirá a tu cuenta.
          </p>
        ) : (
          <>
            <TextField
              label="Tu nombre"
              autoComplete="name"
              value={form.display_name}
              onChange={set("display_name")}
              required
            />
            <TextField
              label="Usuario"
              autoComplete="username"
              autoCapitalize="none"
              value={form.username}
              onChange={set("username")}
              required
            />
            <TextField
              label="Contraseña"
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={set("password")}
              hint={PASSWORD_HINT}
              minLength={12}
              required
            />
          </>
        )}
        <Button type="submit" variant="primary" disabled={accept.isPending || !data}>
          {loggedIn ? "Aceptar" : "Crear mi cuenta"}
        </Button>
      </form>
    </AuthLayout>
  );
}

export function ResetScreen() {
  const { token = "" } = useParams();
  const preview = useQuery({
    queryKey: ["reset", token],
    queryFn: () => api.resetPreview(token),
    retry: false,
  });
  const [password, setPassword] = useState("");
  const reset = useMutation({ mutationFn: () => api.useReset(token, password) });
  if (preview.isError) {
    return (
      <AuthLayout title="Enlace no válido" intro={errorMessage(preview.error)}>
        <Link to="/">Ir a Carrete</Link>
      </AuthLayout>
    );
  }
  if (reset.isSuccess) {
    return (
      <AuthLayout title="Contraseña cambiada" intro="Ya puedes entrar con tu nueva contraseña.">
        <Link to="/">Entrar</Link>
      </AuthLayout>
    );
  }
  return (
    <AuthLayout
      title="Nueva contraseña"
      intro={
        preview.data
          ? `Para la cuenta «${preview.data.username ?? ""}».${preview.data.reset_totp ? " Después tendrás que volver a activar la verificación en dos pasos." : ""}`
          : "Cargando…"
      }
    >
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          reset.mutate();
        }}
      >
        <TextField
          label="Nueva contraseña"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint={PASSWORD_HINT}
          error={reset.isError ? errorMessage(reset.error) : undefined}
          minLength={12}
          required
        />
        <Button type="submit" variant="primary" disabled={reset.isPending}>
          Guardar
        </Button>
      </form>
    </AuthLayout>
  );
}
