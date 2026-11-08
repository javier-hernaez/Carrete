import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { makeMe, mockApi, renderAt, SPACE_A } from "../test/render";

const NOW = new Date().toISOString();

describe("ajustes", () => {
  it("cambia el nombre, la contraseña y cierra otras sesiones", async () => {
    const bodies: Record<string, string> = {};
    mockApi({
      "PATCH /api/v1/me": (init: RequestInit) => {
        bodies.me = init.body as string;
      },
      "POST /api/v1/auth/password": { sessions_closed: 2 },
      "/api/v1/auth/sessions": [
        {
          id: "s1",
          kind: "web",
          device_name: null,
          user_agent: "Mozilla/5.0 (Linux; Android 14) Chrome/130",
          ip: null,
          created_at: NOW,
          last_seen_at: NOW,
          current: true,
        },
        {
          id: "s2",
          kind: "web",
          device_name: null,
          user_agent: "Mozilla/5.0 (Windows NT 10.0) Firefox/130",
          ip: null,
          created_at: NOW,
          last_seen_at: NOW,
          current: false,
        },
      ],
      "DELETE /api/v1/auth/sessions/s2": undefined,
      "POST /api/v1/auth/sessions/revoke-others": { sessions_closed: 1 },
    });
    const user = userEvent.setup();
    renderAt("/ajustes");
    const name = await screen.findByLabelText("Nombre");
    await user.clear(name);
    await user.type(name, "Javi");
    await user.click(screen.getAllByRole("button", { name: "Guardar" })[0]!);
    await waitFor(() => expect(bodies.me).toBe(JSON.stringify({ display_name: "Javi" })));

    await user.type(screen.getByLabelText("Contraseña actual"), "vieja contraseña");
    await user.type(screen.getByLabelText("Nueva contraseña"), "nueva contraseña larga");
    await user.click(screen.getByRole("button", { name: "Cambiar contraseña" }));
    expect(await screen.findByText(/Se han cerrado 2 sesiones/)).toBeInTheDocument();

    expect(await screen.findByText("Chrome en Android")).toBeInTheDocument();
    expect(screen.getByText("Firefox en Windows")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cerrar" }));
    await user.click(screen.getByRole("button", { name: "Cerrar todas las demás" }));
    await user.selectOptions(screen.getByLabelText("Apariencia"), "dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});

describe("espacio", () => {
  it("gestiona miembros e invitaciones", async () => {
    let invited = false;
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/members`]: [
        { user_id: "u1", username: "javier", display_name: "Javier", role: "owner", is_you: true },
        { user_id: "u2", username: "lucia", display_name: "Lucía", role: "collaborator", is_you: false },
      ],
      [`/api/v1/spaces/${SPACE_A}/invitations`]: () =>
        invited ? [{ id: "i1", role: "viewer", created_at: NOW, expires_at: NOW, url: null }] : [],
      [`POST /api/v1/spaces/${SPACE_A}/invitations`]: () => {
        invited = true;
        return {
          id: "i1",
          role: "viewer",
          created_at: NOW,
          expires_at: NOW,
          url: "https://x/invitacion/abc",
        };
      },
      [`PATCH /api/v1/spaces/${SPACE_A}/members/u2`]: undefined,
      "DELETE /api/v1/invitations/i1": undefined,
      [`PATCH /api/v1/spaces/${SPACE_A}`]: {
        id: SPACE_A,
        name: "Nosotros",
        role: "owner",
        archived: false,
        created_at: NOW,
      },
      "POST /api/v1/spaces": { id: "nuevo", name: "Amigos", role: "owner", archived: false, created_at: NOW },
    });
    const user = userEvent.setup();
    renderAt("/espacio");
    expect(await screen.findByRole("heading", { name: "Espacio «Pareja»" })).toBeInTheDocument();
    expect(await screen.findByText("Lucía")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Rol de Lucía"), "viewer");
    await user.selectOptions(screen.getByLabelText("Rol"), "viewer");
    await user.click(screen.getByRole("button", { name: "Crear enlace" }));
    expect(await screen.findByText("https://x/invitacion/abc")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Anular" }));
    await user.clear(screen.getByLabelText("Nombre del espacio"));
    await user.type(screen.getByLabelText("Nombre del espacio"), "Nosotros");
    await user.click(screen.getAllByRole("button", { name: "Guardar" })[0]!);
    await user.type(screen.getByPlaceholderText("Familia"), "Amigos");
    await user.click(screen.getByRole("button", { name: "Crear" }));
  });

  it("un lector solo ve los miembros", async () => {
    mockApi({
      "/api/v1/me": makeMe({ spaces: [{ id: SPACE_A, name: "Pareja", role: "viewer", archived: false }] }),
      [`/api/v1/spaces/${SPACE_A}/members`]: [
        { user_id: "u1", username: "javier", display_name: "Javier", role: "viewer", is_you: true },
      ],
    });
    renderAt("/espacio");
    expect(await screen.findByText("Javier")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crear enlace" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Rol de Javier")).not.toBeInTheDocument();
  });
});

describe("administración", () => {
  it("lista personas, avisos y auditoría", async () => {
    mockApi({
      "/api/v1/admin/users": [
        {
          id: "u2",
          username: "lucia",
          display_name: "Lucía",
          is_admin: false,
          is_active: true,
          has_totp: true,
          spaces: 2,
          last_login_at: NOW,
          created_at: NOW,
        },
      ],
      "/api/v1/admin/notices": [
        {
          id: "n1",
          kind: "auth_burst",
          severity: "warning",
          message: "Muchos intentos fallidos",
          detail: {},
          created_at: NOW,
          acknowledged_at: null,
        },
      ],
      "POST /api/v1/admin/notices/n1/ack": undefined,
      "/api/v1/admin/audit": {
        items: [
          {
            id: "a1",
            occurred_at: NOW,
            actor_id: null,
            actor_name: "Javier",
            space_id: null,
            action: "auth.login",
            target_type: null,
            target_id: null,
            ip: "10.0.0.1",
            detail: {},
          },
        ],
        next_cursor: "a1",
      },
      "POST /api/v1/admin/users/u2/reset": { url: "https://x/restablecer/zzz", expires_at: NOW },
      "POST /api/v1/admin/users/u2/active": undefined,
      "POST /api/v1/admin/invitations": { url: "https://x/invitacion/yyy", expires_at: NOW },
    });
    const user = userEvent.setup();
    renderAt("/admin");
    expect(await screen.findByText("Muchos intentos fallidos")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Entendido" }));
    expect(await screen.findByText("auth.login")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Más antiguos" }));
    await user.click(screen.getByText("Acciones"));
    await user.click(screen.getByRole("button", { name: "Restablecer contraseña y 2FA" }));
    expect(await screen.findByText("https://x/restablecer/zzz")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Desactivar cuenta" }));
    await user.click(screen.getByRole("button", { name: "Invitar sin espacio" }));
    expect(await screen.findByText("https://x/invitacion/yyy")).toBeInTheDocument();
  });

  it("no se muestra a quien no es administrador", async () => {
    mockApi({ "/api/v1/me": makeMe({ is_admin: false }) });
    renderAt("/admin");
    expect(await screen.findByText("Solo el administrador puede ver esta página.")).toBeInTheDocument();
  });
});
