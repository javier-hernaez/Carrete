import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { makeMe, mockApi, renderAt, SPACE_B } from "../test/render";

describe("armazón de la aplicación", () => {
  it("abre en la línea temporal del último espacio", async () => {
    mockApi();
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "Todavía no hay fotos" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Secciones" });
    expect(within(nav).getByRole("link", { name: "Fotos" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Espacio")).toHaveValue(makeMe().current_space_id);
  });

  it("oculta el mapa si el servidor no tiene proveedor de teselas", async () => {
    mockApi();
    renderAt("/");
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    expect(within(nav).queryByRole("link", { name: "Mapa" })).not.toBeInTheDocument();
  });

  it("muestra el mapa si está configurado", async () => {
    mockApi({ "/api/v1/info": { name: "Carrete", version: "1", map_enabled: true } });
    renderAt("/");
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    expect(await within(nav).findByRole("link", { name: "Mapa" })).toBeInTheDocument();
  });

  it("navega entre secciones", async () => {
    mockApi({ "/api/v1/info": { name: "Carrete", version: "1", map_enabled: true } });
    const user = userEvent.setup();
    renderAt("/");
    const nav = await screen.findByRole("navigation", { name: "Secciones" });
    await user.click(within(nav).getByRole("link", { name: "Revisar" }));
    expect(screen.getByRole("heading", { name: "Nada que revisar" })).toBeInTheDocument();
    await user.click(within(nav).getByRole("link", { name: "Álbumes" }));
    expect(screen.getByRole("heading", { name: "Aún no hay álbumes" })).toBeInTheDocument();
    await user.click(await within(nav).findByRole("link", { name: "Mapa" }));
    expect(screen.getByRole("heading", { name: "El mapa está vacío" })).toBeInTheDocument();
    await user.click(screen.getAllByRole("link", { name: "Subir" })[0]!);
    expect(screen.getByRole("heading", { name: "La subida llega pronto" })).toBeInTheDocument();
  });

  it("muestra el resto de secciones y la versión en «Más»", async () => {
    mockApi({ "/api/v1/info": { name: "Carrete", version: "abc1234", map_enabled: false } });
    renderAt("/mas");
    expect(await screen.findByRole("heading", { name: "Más" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Administración" })).toHaveAttribute("href", "/admin");
    expect(screen.getByRole("link", { name: "Ajustes" })).toHaveAttribute("href", "/ajustes");
    expect(await screen.findByText("Versión abc1234")).toBeInTheDocument();
  });

  it("no enseña Administración a quien no es administrador", async () => {
    mockApi({ "/api/v1/me": makeMe({ is_admin: false }) });
    renderAt("/mas");
    await screen.findByRole("heading", { name: "Más" });
    expect(screen.queryByRole("link", { name: "Administración" })).not.toBeInTheDocument();
  });

  it("cambia de espacio desde la cabecera", async () => {
    const calls: string[] = [];
    mockApi({
      "PATCH /api/v1/me": (init: RequestInit) => {
        calls.push(init.body as string);
      },
    });
    const user = userEvent.setup();
    renderAt("/");
    await user.selectOptions(await screen.findByLabelText("Espacio"), SPACE_B);
    expect(screen.getByLabelText("Espacio")).toHaveValue(SPACE_B);
    expect(calls).toEqual([JSON.stringify({ last_space_id: SPACE_B })]);
  });

  it("con un solo espacio no muestra selector", async () => {
    mockApi({
      "/api/v1/me": makeMe({
        spaces: [{ id: makeMe().current_space_id ?? "", name: "Pareja", role: "owner", archived: false }],
      }),
    });
    renderAt("/");
    expect(await screen.findByText("Pareja")).toBeInTheDocument();
    expect(screen.queryByLabelText("Espacio")).not.toBeInTheDocument();
  });

  it("tiene enlace para saltar al contenido", async () => {
    mockApi();
    renderAt("/");
    expect(await screen.findByRole("link", { name: "Saltar al contenido" })).toHaveAttribute(
      "href",
      "#contenido",
    );
  });

  it("responde a rutas inexistentes", async () => {
    mockApi();
    const user = userEvent.setup();
    renderAt("/no-existe");
    expect(await screen.findByRole("heading", { name: "Esta página no existe" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Volver a las fotos" }));
    expect(screen.getByRole("heading", { name: "Todavía no hay fotos" })).toBeInTheDocument();
  });
});
