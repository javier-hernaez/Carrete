import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { HttpError, makeMe, mockApi, renderAt, unauthorized } from "../../test/render";

describe("acceso", () => {
  it("pide el asistente inicial si no hay cuentas", async () => {
    let created = false;
    mockApi({
      "/api/v1/me": () => (created ? makeMe({ stage: "enroll" }) : unauthorized),
      "/api/v1/setup": { needed: true },
      "POST /api/v1/setup": (init: RequestInit) => {
        const body = JSON.parse(init.body as string) as Record<string, string>;
        if (body.token !== "abc")
          return new HttpError(403, { detail: "El código de arranque no es correcto" });
        created = true;
        return { stage: "enroll" };
      },
      "POST /api/v1/auth/totp/setup": {
        secret: "SECRETO",
        otpauth_uri: "otpauth://x",
        qr_svg: "<svg></svg>",
      },
    });
    const user = userEvent.setup();
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "Bienvenido a Carrete" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Código de arranque"), "mal");
    await user.type(screen.getByLabelText("Tu nombre"), "Javier");
    await user.type(screen.getByLabelText("Usuario"), "javier");
    await user.type(screen.getByLabelText("Contraseña"), "una frase larga y segura");
    await user.click(screen.getByRole("button", { name: "Crear cuenta" }));
    expect(await screen.findByText("El código de arranque no es correcto")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Código de arranque"));
    await user.type(screen.getByLabelText("Código de arranque"), "abc");
    await user.click(screen.getByRole("button", { name: "Crear cuenta" }));
    expect(await screen.findByRole("heading", { name: "Protege tu cuenta" })).toBeInTheDocument();
    expect(await screen.findByText("SECRETO")).toBeInTheDocument();
  });

  it("inicia sesión con contraseña y código", async () => {
    let stage: "none" | "totp" | "full" = "none";
    mockApi({
      "/api/v1/me": () => (stage === "none" ? unauthorized : makeMe({ stage })),
      "/api/v1/setup": { needed: false },
      "POST /api/v1/auth/login": (init: RequestInit) => {
        const { password } = JSON.parse(init.body as string) as { password: string };
        if (password !== "buena contraseña")
          return new HttpError(401, { detail: "Usuario o contraseña incorrectos" });
        stage = "totp";
        return { stage };
      },
      "POST /api/v1/auth/totp": (init: RequestInit) => {
        const { code } = JSON.parse(init.body as string) as { code: string };
        if (code !== "123456") return new HttpError(401, { detail: "Código incorrecto" });
        stage = "full";
        return { stage };
      },
    });
    const user = userEvent.setup();
    renderAt("/");
    await user.type(await screen.findByLabelText("Usuario"), "javier");
    await user.type(screen.getByLabelText("Contraseña"), "mala");
    await user.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText("Usuario o contraseña incorrectos")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Contraseña"));
    await user.type(screen.getByLabelText("Contraseña"), "buena contraseña");
    await user.click(screen.getByRole("button", { name: "Entrar" }));
    await user.type(await screen.findByLabelText("Código"), "000000");
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByText("Código incorrecto")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Código"));
    await user.type(screen.getByLabelText("Código"), "123456");
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByRole("heading", { name: "Todavía no hay fotos" })).toBeInTheDocument();
  });

  it("activa el segundo factor y muestra los códigos de recuperación", async () => {
    let enabled = false;
    mockApi({
      "/api/v1/me": () => makeMe({ stage: enabled ? "full" : "enroll" }),
      "POST /api/v1/auth/totp/setup": { secret: "S", otpauth_uri: "otpauth://x", qr_svg: "<svg></svg>" },
      "POST /api/v1/auth/totp/enable": () => {
        enabled = true;
        return { recovery_codes: ["aaaaa-bbbbb", "ccccc-ddddd"] };
      },
    });
    const user = userEvent.setup();
    renderAt("/");
    await user.type(await screen.findByLabelText("Código de 6 cifras"), "123456");
    await user.click(screen.getByRole("button", { name: "Activar" }));
    expect(await screen.findByText("aaaaa-bbbbb")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ya los he guardado" }));
    expect(await screen.findByRole("heading", { name: "Todavía no hay fotos" })).toBeInTheDocument();
  });

  it("acepta una invitación creando la cuenta", async () => {
    let accepted = false;
    mockApi({
      "/api/v1/me": () => (accepted ? makeMe({ stage: "enroll" }) : unauthorized),
      "/api/v1/invitations/by-token/tok": {
        space_name: "Familia",
        role: "viewer",
        invited_by: "Lucía",
        expires_at: "2030-01-01T00:00:00Z",
      },
      "POST /api/v1/invitations/by-token/tok/accept": () => {
        accepted = true;
        return { stage: "enroll", space_id: null };
      },
      "POST /api/v1/auth/totp/setup": { secret: "S", otpauth_uri: "otpauth://x", qr_svg: "<svg></svg>" },
    });
    const user = userEvent.setup();
    renderAt("/invitacion/tok");
    expect(await screen.findByText("Lucía te invita al espacio «Familia» como lector.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Tu nombre"), "Ana");
    await user.type(screen.getByLabelText("Usuario"), "ana");
    await user.type(screen.getByLabelText("Contraseña"), "una frase larga y segura");
    await user.click(screen.getByRole("button", { name: "Crear mi cuenta" }));
    expect(await screen.findByRole("heading", { name: "Protege tu cuenta" })).toBeInTheDocument();
  });

  it("avisa de invitaciones caducadas", async () => {
    mockApi({
      "/api/v1/me": unauthorized,
      "/api/v1/invitations/by-token/vieja": new HttpError(404, {
        detail: "Este enlace no es válido o ha caducado. Pide uno nuevo.",
      }),
    });
    renderAt("/invitacion/vieja");
    expect(await screen.findByRole("heading", { name: "Invitación no válida" })).toBeInTheDocument();
  });

  it("restablece la contraseña con un enlace", async () => {
    mockApi({
      "/api/v1/password-resets/r1": { username: "lucia", reset_totp: true },
      "POST /api/v1/password-resets/r1": { stage: "full" },
    });
    const user = userEvent.setup();
    renderAt("/restablecer/r1");
    expect(await screen.findByText(/Para la cuenta «lucia»/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nueva contraseña"), "otra frase muy segura");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByRole("heading", { name: "Contraseña cambiada" })).toBeInTheDocument();
  });

  it("pide reautenticación para acciones sensibles y reintenta", async () => {
    let fresh = false;
    mockApi({
      "POST /api/v1/auth/recovery-codes": () =>
        fresh
          ? { recovery_codes: ["nuevo-codigo"] }
          : new HttpError(403, { code: "reauth_required", detail: "Vuelve a introducir tu contraseña" }),
      "POST /api/v1/auth/reauth": () => {
        fresh = true;
      },
      "/api/v1/auth/sessions": [],
    });
    const user = userEvent.setup();
    renderAt("/ajustes");
    await user.click(await screen.findByRole("button", { name: "Generar nuevos códigos de recuperación" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirma que eres tú" });
    expect(dialog).toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Contraseña", { selector: "input[type=password]" }),
      "mi contraseña",
    );
    await user.type(screen.getByLabelText("Código de verificación"), "123456");
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(screen.getByText("nuevo-codigo")).toBeInTheDocument());
  });
});
