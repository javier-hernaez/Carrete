import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderAt, SPACE_A } from "../../test/render";
import { makeAsset } from "../photos/photos.test";

describe("selección múltiple", () => {
  const items = [makeAsset(0), makeAsset(1), makeAsset(2), makeAsset(3)];

  function api(calls: Record<string, unknown>[]) {
    return mockApi({
      [`/api/v1/spaces/${SPACE_A}/assets`]: { items, next_cursor: null },
      [`/api/v1/spaces/${SPACE_A}/albums`]: [],
      [`POST /api/v1/spaces/${SPACE_A}/albums`]: {
        id: "nuevo",
        name: "Playa",
        description: null,
        count: 0,
        cover_asset_id: null,
        sort_mode: "date",
        first: null,
        last: null,
      },
      [`POST /api/v1/spaces/${SPACE_A}/assets/batch`]: (init: RequestInit) => {
        const body = JSON.parse(init.body as string) as Record<string, unknown>;
        calls.push(body);
        return { count: (body.ids as string[]).length, undo: { action: "revert", snapshot: {} } };
      },
    });
  }

  it("selecciona con casillas, rangos y días, y actúa sobre la selección", async () => {
    const calls: Record<string, unknown>[] = [];
    api(calls);
    const user = userEvent.setup();
    renderAt("/");
    const boxes = await screen.findAllByRole("button", { name: /^Seleccionar: / });
    await user.click(boxes[0]!);
    expect(screen.getByText("1 seleccionada")).toBeInTheDocument();
    // Mayús+clic: rango
    fireEvent.click(boxes[2]!, { shiftKey: true });
    expect(screen.getByText("3 seleccionadas")).toBeInTheDocument();
    // Con selección activa, tocar una miniatura la añade en vez de abrirla
    await user.click(screen.getAllByRole("button", { name: /^Foto del/ })[3]!);
    expect(screen.getByText("4 seleccionadas")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Visor de fotos" })).not.toBeInTheDocument();

    const bar = screen.getByRole("toolbar", { name: "Acciones sobre la selección" });
    await user.click(within(bar).getByRole("button", { name: "Vale" }));
    await waitFor(() => expect(calls[0]).toMatchObject({ action: "review", state: "kept" }));
    expect(await screen.findByText("4 marcadas como «vale»")).toBeInTheDocument();
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deshacer" }));
    await waitFor(() => expect(calls[1]).toMatchObject({ action: "revert", snapshot: {} }));

    // Día entero: el botón solo aparece con la selección en marcha
    expect(screen.queryByRole("button", { name: "Seleccionar el día" })).not.toBeInTheDocument();
    await user.click(boxes[0]!);
    await user.click(screen.getAllByRole("button", { name: "Seleccionar el día" })[0]!);
    expect(screen.getByText("3 seleccionadas")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Quitar el día" }));
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });

  it("añade a un álbum nuevo y cambia fechas", async () => {
    const calls: Record<string, unknown>[] = [];
    api(calls);
    const user = userEvent.setup();
    renderAt("/");
    const boxes = await screen.findAllByRole("button", { name: /^Seleccionar: / });
    await user.click(boxes[0]!);
    await user.click(boxes[1]!);
    await user.click(screen.getByRole("button", { name: "Álbum…" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir 2 a un álbum" });
    await user.type(within(dialog).getByLabelText("Nuevo álbum"), "Playa");
    await user.click(within(dialog).getByRole("button", { name: "Crear y añadir" }));
    await waitFor(() => expect(calls[0]).toMatchObject({ action: "add_album", album_id: "nuevo" }));

    const again = await screen.findAllByRole("button", { name: /^Seleccionar: / });
    await user.click(again[0]!);
    await user.click(screen.getByRole("button", { name: "Fecha…" }));
    const date = await screen.findByRole("dialog", { name: "Cambiar la fecha" });
    await user.click(within(date).getByLabelText("Mover"));
    await user.clear(within(date).getByLabelText("Cuánto"));
    await user.type(within(date).getByLabelText("Cuánto"), "2");
    await user.selectOptions(within(date).getByLabelText("Unidad"), "days");
    await user.click(within(date).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(calls[1]).toMatchObject({ action: "shift_date", minutes: -2880 }));

    await user.click((await screen.findAllByRole("button", { name: /^Seleccionar: / }))[0]!);
    await user.click(screen.getByRole("button", { name: "Fecha…" }));
    const set = await screen.findByRole("dialog", { name: "Cambiar la fecha" });
    fireEvent.change(within(set).getByLabelText("Fecha y hora de la foto"), {
      target: { value: "2020-05-01T10:30" },
    });
    await user.click(within(set).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(calls[2]).toMatchObject({ action: "set_date", taken_at: "2020-05-01T10:30:00" }),
    );
  });

  it("acciones del visor: vale, favorita y eliminar", async () => {
    const calls: Record<string, unknown>[] = [];
    api(calls);
    const user = userEvent.setup();
    renderAt(`/?ver=${items[0]?.id ?? ""}`);
    const viewer = await screen.findByRole("dialog", { name: "Visor de fotos" });
    await user.click(within(viewer).getByRole("button", { name: "✓ Vale" }));
    await user.click(within(viewer).getByRole("button", { name: "★ Favorita" }));
    await user.click(within(viewer).getByRole("button", { name: "✕ No vale" }));
    await waitFor(() => expect(calls.map((c) => c.action)).toEqual(["review", "favorite", "review"]));
    expect(calls[2]).toMatchObject({ state: "discarded" });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("mantener pulsado selecciona y, sin soltar, deslizar marca el rango", async () => {
    api([]);
    renderAt("/");
    const thumbs = await screen.findAllByRole("button", { name: /^Foto del/ });
    expect(thumbs[0]).not.toHaveAttribute("draggable", "true");
    const cell = (i: number) => thumbs[i]!.closest("[data-index]")!;
    // jsdom no calcula posiciones: «lo que hay bajo el dedo» es la miniatura según la x del toque.
    document.elementFromPoint = (x: number) => cell(Math.min(3, Math.floor(x / 100)));
    vi.useFakeTimers();
    fireEvent.touchStart(thumbs[0]!, { touches: [{ clientX: 10, clientY: 10 }] });
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(screen.getByText("1 seleccionada")).toBeInTheDocument();
    fireEvent.touchMove(thumbs[0]!, { touches: [{ clientX: 210, clientY: 10 }] });
    expect(screen.getByText("3 seleccionadas")).toBeInTheDocument();
    fireEvent.touchEnd(thumbs[0]!, { touches: [] });
    // El clic que sigue al soltar no abre el visor ni cambia la selección
    fireEvent.click(thumbs[2]!);
    expect(screen.getByText("3 seleccionadas")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Visor de fotos" })).not.toBeInTheDocument();

    // Mover el dedo antes de tiempo es desplazar la página: no selecciona
    fireEvent.touchStart(thumbs[3]!, { touches: [{ clientX: 310, clientY: 10 }] });
    fireEvent.touchMove(thumbs[3]!, { touches: [{ clientX: 310, clientY: 80 }] });
    act(() => {
      vi.advanceTimersByTime(500);
    });
    fireEvent.touchEnd(thumbs[3]!, { touches: [] });
    expect(screen.getByText("3 seleccionadas")).toBeInTheDocument();
  });

  it("pone etiquetas a la selección y crea una nueva", async () => {
    const calls: Record<string, unknown>[] = [];
    let created: Record<string, unknown> = {};
    api(calls);
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/assets`]: {
        items: items.map((a, i) => ({ ...a, tag_ids: i === 0 ? ["t1"] : [] })),
        next_cursor: null,
      },
      [`/api/v1/spaces/${SPACE_A}/albums`]: [],
      [`/api/v1/spaces/${SPACE_A}/tags`]: [{ id: "t1", name: "Personas", count: 1 }],
      [`POST /api/v1/spaces/${SPACE_A}/tags`]: (init: RequestInit) => {
        created = JSON.parse(init.body as string) as Record<string, unknown>;
        return { id: "t9", name: "Humor", count: 2 };
      },
      [`POST /api/v1/spaces/${SPACE_A}/assets/batch`]: (init: RequestInit) => {
        calls.push(JSON.parse(init.body as string) as Record<string, unknown>);
        return { count: 1, undo: null };
      },
    });
    const user = userEvent.setup();
    renderAt("/");
    const boxes = await screen.findAllByRole("button", { name: /^Seleccionar: / });
    await user.click(boxes[0]!);
    await user.click(boxes[1]!);
    await user.click(screen.getByRole("button", { name: "Etiquetas…" }));
    const dialog = await screen.findByRole("dialog", { name: "Etiquetas de 2" });
    // Una de las dos la tiene: estado mixto; al tocar, se pone a las dos
    const personas = await within(dialog).findByRole("button", { name: /Personas/ });
    expect(personas).toHaveAttribute("aria-pressed", "mixed");
    await user.click(personas);
    await waitFor(() => expect(calls[0]).toMatchObject({ action: "add_tag", tag_id: "t1" }));
    expect(personas).toHaveAttribute("aria-pressed", "true");
    // Sugerencias para empezar y crear una nueva
    expect(within(dialog).getByRole("button", { name: "+ Paisajes" })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "+ Humor" }));
    await waitFor(() => expect(created).toMatchObject({ name: "Humor" }));
    expect((created.asset_ids as string[]).length).toBe(2);
  });
});
