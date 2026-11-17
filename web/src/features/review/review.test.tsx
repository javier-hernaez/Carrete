import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { makeMe, mockApi, renderAt, SPACE_A } from "../../test/render";
import { makeAsset } from "../photos/photos.test";

const ALBUMS = [
  {
    id: "al1",
    name: "Asturias",
    description: null,
    count: 3,
    cover_asset_id: null,
    sort_mode: "date",
    first: null,
    last: null,
  },
  {
    id: "al2",
    name: "Boda",
    description: null,
    count: 0,
    cover_asset_id: null,
    sort_mode: "date",
    first: null,
    last: null,
  },
];

describe("Revisar", () => {
  let calls: { action: string; ids: string[]; [k: string]: unknown }[];
  const items = [makeAsset(0), makeAsset(1), makeAsset(2, { kind: "video", duration_ms: 5000 })];

  beforeEach(() => {
    calls = [];
    localStorage.clear();
    localStorage.setItem("carrete:revisar-modo", "one");
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/assets`]: (_: RequestInit, url: URL) => {
        expect(url.searchParams.getAll("review")).toEqual(["pending"]);
        return { items, next_cursor: null };
      },
      [`/api/v1/spaces/${SPACE_A}/albums`]: ALBUMS,
      [`POST /api/v1/spaces/${SPACE_A}/assets/batch`]: (init: RequestInit) => {
        calls.push(JSON.parse(init.body as string) as (typeof calls)[number]);
        return { count: 1, undo: null };
      },
    });
  });

  it("decide con el teclado, deshace y termina con un resumen", async () => {
    renderAt("/revisar");
    expect(await screen.findByText("1 de 3")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByText("2 de 3")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "f" });
    expect(screen.getByText("2 de 3")).toBeInTheDocument(); // favorita no avanza
    fireEvent.keyDown(window, { key: "2" }); // segundo álbum reciente
    fireEvent.keyDown(window, { key: "x" });
    expect(screen.getByText("3 de 3")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "z" });
    expect(screen.getByText("2 de 3")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "x" });
    fireEvent.keyDown(window, { key: " " }); // saltar
    expect(await screen.findByRole("heading", { name: "¡Listo!" })).toBeInTheDocument();
    expect(screen.getByText(/1 valen y 1 descartados/)).toBeInTheDocument();
    await waitFor(() => expect(calls).toHaveLength(6));
    expect(calls.map((c) => [c.action, c.state ?? c.value ?? c.album_id])).toEqual([
      ["review", "kept"],
      ["favorite", true],
      ["add_album", "al2"],
      ["review", "discarded"],
      ["review", "pending"],
      ["review", "discarded"],
    ]);
  });

  it("decide con gestos y botones", async () => {
    const user = userEvent.setup();
    renderAt("/revisar");
    const stage = (await screen.findByRole("region", { name: "Revisar" })).querySelector("img")
      ?.parentElement as HTMLElement;
    fireEvent.pointerDown(stage, { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(stage, { clientX: 260, clientY: 110 });
    expect(screen.getByText("VALE")).toBeInTheDocument();
    fireEvent.pointerUp(stage);
    expect(screen.getByText("2 de 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /No vale/ }));
    await user.click(screen.getByRole("button", { name: /Deshacer/ }));
    expect(screen.getByText("2 de 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Álbum/ }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir a un álbum" });
    await user.click(within(dialog).getByRole("button", { name: /Asturias/ }));
    expect(await screen.findByText("Añadida a «Asturias»")).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.some((c) => c.action === "add_album" && c.album_id === "al1")).toBe(true),
    );
  });

  it("pone y quita etiquetas sin pasar a la siguiente", async () => {
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/assets`]: { items, next_cursor: null },
      [`/api/v1/spaces/${SPACE_A}/albums`]: [],
      [`/api/v1/spaces/${SPACE_A}/tags`]: [{ id: "t1", name: "Humor", count: 0 }],
      [`POST /api/v1/spaces/${SPACE_A}/assets/batch`]: (init: RequestInit) => {
        calls.push(JSON.parse(init.body as string) as (typeof calls)[number]);
        return { count: 1, undo: null };
      },
    });
    const user = userEvent.setup();
    renderAt("/revisar");
    const chips = await screen.findByRole("region", { name: "Revisar" });
    const humor = await within(chips).findByRole("button", { name: "Humor" });
    await user.click(humor);
    expect(within(chips).getByRole("button", { name: "✓ Humor" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("1 de 3")).toBeInTheDocument();
    await user.click(within(chips).getByRole("button", { name: "✓ Humor" }));
    await waitFor(() =>
      expect(calls.map((c) => [c.action, c.tag_id])).toEqual([
        ["add_tag", "t1"],
        ["remove_tag", "t1"],
      ]),
    );
  });

  it("en bloque: cuadrícula con casillas, día entero y decisión para todas", async () => {
    localStorage.removeItem("carrete:revisar-modo");
    const user = userEvent.setup();
    renderAt("/revisar");
    expect(await screen.findByRole("heading", { name: "Revisar" })).toBeInTheDocument();
    // Casillas a la vista y «Seleccionar el día» sin tener que empezar a seleccionar
    const boxes = await screen.findAllByRole("button", { name: /^Seleccionar: / });
    expect(boxes).toHaveLength(3);
    await user.click(screen.getAllByRole("button", { name: "Seleccionar el día" })[0]!);
    expect(screen.getByText("3 seleccionadas")).toBeInTheDocument();
    const bar = screen.getByRole("toolbar", { name: "Acciones sobre la selección" });
    await user.click(within(bar).getByRole("button", { name: "Descartar" }));
    await waitFor(() => expect(calls[0]).toMatchObject({ action: "review", state: "discarded" }));
    expect(calls[0]?.ids).toHaveLength(3);
    // Se recuerda el modo elegido
    await user.click(screen.getByRole("button", { name: "Una a una" }));
    expect(await screen.findByText("1 de 3")).toBeInTheDocument();
    expect(localStorage.getItem("carrete:revisar-modo")).toBe("one");
  });

  it("explica cuando no hay nada que revisar y bloquea a los lectores", async () => {
    mockApi({ [`/api/v1/spaces/${SPACE_A}/assets`]: { items: [], next_cursor: null } });
    const first = renderAt("/revisar");
    expect(await screen.findByRole("heading", { name: "Nada que revisar" })).toBeInTheDocument();
    first.unmount();
    mockApi({
      "/api/v1/me": makeMe({ spaces: [{ id: SPACE_A, name: "Pareja", role: "viewer", archived: false }] }),
    });
    renderAt("/revisar");
    expect(await screen.findByRole("heading", { name: "Solo puedes ver este espacio" })).toBeInTheDocument();
  });
});
