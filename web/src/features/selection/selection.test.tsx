import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

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

    // Día entero
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

  it("arrastra la selección a un álbum de la barra lateral", async () => {
    const calls: Record<string, unknown>[] = [];
    api(calls);
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/assets`]: { items, next_cursor: null },
      [`/api/v1/spaces/${SPACE_A}/albums`]: [
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
      ],
      [`POST /api/v1/spaces/${SPACE_A}/assets/batch`]: (init: RequestInit) => {
        calls.push(JSON.parse(init.body as string) as Record<string, unknown>);
        return { count: 2, undo: null };
      },
    });
    renderAt("/");
    const target = await screen.findByRole("link", { name: /Asturias/ });
    const data = new Map<string, string>([
      ["application/x-carrete-ids", JSON.stringify([items[0]?.id, items[1]?.id])],
    ]);
    const dataTransfer = {
      types: ["application/x-carrete-ids"],
      getData: (t: string) => data.get(t) ?? "",
      dropEffect: "none",
    };
    fireEvent.dragOver(target, { dataTransfer });
    fireEvent.drop(target, { dataTransfer });
    await waitFor(() =>
      expect(calls[0]).toMatchObject({
        action: "add_album",
        album_id: "al1",
        ids: [items[0]?.id, items[1]?.id],
      }),
    );
    expect(await screen.findByText("2 añadidas a «Asturias»")).toBeInTheDocument();
  });
});
