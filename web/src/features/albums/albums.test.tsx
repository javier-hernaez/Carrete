import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt, SPACE_A } from "../../test/render";
import { makeAsset } from "../photos/photos.test";
import { albumRange } from "./range";

const ALBUM = {
  id: "al1",
  name: "Asturias",
  description: "Verano",
  count: 2,
  cover_asset_id: makeAsset(0).id,
  sort_mode: "date",
  first: "2025-08-12T10:00:00",
  last: "2025-08-15T20:00:00",
};

describe("álbumes", () => {
  it("lista, crea y abre", async () => {
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/albums`]: [ALBUM],
      [`POST /api/v1/spaces/${SPACE_A}/albums`]: { ...ALBUM, id: "al2", name: "Boda", count: 0 },
      [`/api/v1/spaces/${SPACE_A}/albums/al2`]: { ...ALBUM, id: "al2", name: "Boda", count: 0 },
    });
    const user = userEvent.setup();
    renderAt("/albumes");
    expect(
      await screen.findByRole("link", {
        name: /Asturias\s*2 elementos · 12 de agosto de 2025 – 15 de agosto de 2025/,
      }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nuevo álbum"), "Boda");
    await user.click(screen.getByRole("button", { name: "Crear" }));
    expect(await screen.findByRole("heading", { name: "Este álbum está vacío" })).toBeInTheDocument();
  });

  it("edita, cambia el orden, quita fotos y se elimina sin borrar fotos", async () => {
    const patches: string[] = [];
    const batches: Record<string, unknown>[] = [];
    let deleted = false;
    let mode = "date";
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/albums/al1`]: () => ({ ...ALBUM, sort_mode: mode }),
      [`PATCH /api/v1/spaces/${SPACE_A}/albums/al1`]: (init: RequestInit) => {
        patches.push(init.body as string);
        const body = JSON.parse(init.body as string) as { sort_mode?: string };
        if (body.sort_mode) mode = body.sort_mode;
        return { ...ALBUM, sort_mode: mode };
      },
      [`DELETE /api/v1/spaces/${SPACE_A}/albums/al1`]: () => {
        deleted = true;
      },
      [`/api/v1/spaces/${SPACE_A}/assets`]: (_: RequestInit, url: URL) => {
        expect(url.searchParams.get("album_id")).toBe("al1");
        return { items: [makeAsset(0), makeAsset(1)], next_cursor: null };
      },
      [`POST /api/v1/spaces/${SPACE_A}/assets/batch`]: (init: RequestInit) => {
        batches.push(JSON.parse(init.body as string) as Record<string, unknown>);
        return { count: 1, undo: null };
      },
    });
    const user = userEvent.setup();
    renderAt("/albumes/al1");
    const name = await screen.findByLabelText("Nombre del álbum");
    await user.clear(name);
    await user.type(name, "Asturias 2025");
    await user.tab();
    await waitFor(() => expect(patches[0]).toBe(JSON.stringify({ name: "Asturias 2025" })));

    await user.click((await screen.findAllByRole("button", { name: /^Seleccionar: / }))[0]!);
    await user.click(screen.getByRole("button", { name: "Quitar del álbum" }));
    await waitFor(() => expect(batches[0]).toMatchObject({ action: "remove_album", album_id: "al1" }));

    await user.click(screen.getByLabelText("Manual"));
    await waitFor(() => expect(patches).toContain(JSON.stringify({ sort_mode: "manual" })));
    expect(await screen.findByRole("list", { name: "Fotos del álbum en orden manual" })).toBeInTheDocument();

    // Eliminar queda apartado en «Más opciones del álbum»
    expect(screen.queryByRole("button", { name: /Eliminar/ })).not.toBeVisible();
    await user.click(screen.getByText("Más opciones del álbum"));
    await user.click(screen.getByRole("button", { name: "Eliminar el álbum…" }));
    const dialog = await screen.findByRole("dialog", { name: "Eliminar el álbum" });
    expect(within(dialog).getByText(/Sus fotos no se borran/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Eliminar álbum" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("filtra dentro del álbum por sus etiquetas", async () => {
    const calls: URL[] = [];
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/albums/al1`]: ALBUM,
      [`/api/v1/spaces/${SPACE_A}/tags`]: (_: RequestInit, url: URL) => {
        expect(url.searchParams.get("album_id")).toBe("al1");
        return [{ id: "t1", name: "Personas", count: 1 }];
      },
      [`/api/v1/spaces/${SPACE_A}/assets`]: (_: RequestInit, url: URL) => {
        calls.push(url);
        return { items: [makeAsset(0)], next_cursor: null };
      },
    });
    const user = userEvent.setup();
    renderAt("/albumes/al1");
    const group = await screen.findByRole("group", { name: "Filtrar el álbum por etiqueta" });
    await user.click(await within(group).findByRole("button", { name: /Personas/ }));
    await waitFor(() =>
      expect(
        calls.some((u) => u.searchParams.get("album_id") === "al1" && u.searchParams.get("tag_id") === "t1"),
      ).toBe(true),
    );
  });

  it("formatea el rango de fechas", () => {
    expect(albumRange("2025-08-12T10:00:00", "2025-08-12T23:00:00")).toBe("12 de agosto de 2025");
    expect(albumRange(null, null)).toBe("");
  });
});
