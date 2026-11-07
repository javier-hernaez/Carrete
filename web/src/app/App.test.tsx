import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { mockInfo, renderAt } from "../test/render";

describe("armazón de la aplicación", () => {
  it("abre en la línea temporal con su estado vacío", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockInfo({ map_enabled: false }));
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "Todavía no hay fotos" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Secciones" });
    expect(within(nav).getByRole("link", { name: "Fotos" })).toHaveAttribute("aria-current", "page");
  });

  it("oculta el mapa si el servidor no tiene proveedor de teselas", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(mockInfo({ map_enabled: false }));
    renderAt("/");
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const nav = screen.getByRole("navigation", { name: "Secciones" });
    expect(within(nav).queryByRole("link", { name: "Mapa" })).not.toBeInTheDocument();
  });

  it("muestra el mapa si está configurado", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockInfo({ map_enabled: true }));
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: "Secciones" });
    expect(await within(nav).findByRole("link", { name: "Mapa" })).toBeInTheDocument();
  });

  it("navega entre secciones", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockInfo({ map_enabled: true }));
    const user = userEvent.setup();
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: "Secciones" });
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
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockInfo({ map_enabled: false, version: "abc1234" }));
    renderAt("/mas");
    expect(screen.getByRole("heading", { name: "Más" })).toBeInTheDocument();
    for (const name of ["Repetidas", "Descartadas", "Papelera", "Exportar", "Administración"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(await screen.findByText("Versión abc1234")).toBeInTheDocument();
  });

  it("tiene enlace para saltar al contenido", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockInfo({ map_enabled: false }));
    renderAt("/");
    expect(screen.getByRole("link", { name: "Saltar al contenido" })).toHaveAttribute("href", "#contenido");
  });

  it("responde a rutas inexistentes", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockInfo({ map_enabled: false }));
    const user = userEvent.setup();
    renderAt("/no-existe");
    expect(screen.getByRole("heading", { name: "Esta página no existe" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Volver a las fotos" }));
    expect(screen.getByRole("heading", { name: "Todavía no hay fotos" })).toBeInTheDocument();
  });
});
