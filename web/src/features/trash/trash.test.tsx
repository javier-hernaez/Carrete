import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { makeMe, mockApi, renderAt, SPACE_A } from "../../test/render";
import { makeAsset } from "../photos/photos.test";

const NOW = new Date().toISOString();

describe("papelera y eliminar", () => {
  it("elimina desde el visor y permite deshacer", async () => {
    const calls: string[] = [];
    const items = [makeAsset(0), makeAsset(1)];
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/assets`]: { items, next_cursor: null },
      [`POST /api/v1/spaces/${SPACE_A}/assets/batch`]: (init: RequestInit) => {
        calls.push(init.body as string);
        const { action } = JSON.parse(init.body as string) as { action: string };
        return { count: 1, undo: action === "trash" ? { action: "restore" } : { action: "trash" } };
      },
    });
    const user = userEvent.setup();
    renderAt(`/?ver=${items[0]?.id ?? ""}`);
    const viewer = await screen.findByRole("dialog", { name: "Visor de fotos" });
    await user.click(within(viewer).getByRole("button", { name: "Eliminar" }));
    expect(await screen.findByText("Enviada a la papelera")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deshacer" }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(JSON.parse(calls[0] ?? "{}")).toMatchObject({ action: "trash", ids: [items[0]?.id] });
    expect(JSON.parse(calls[1] ?? "{}")).toMatchObject({ action: "restore" });
  });

  it("un lector no ve «Eliminar»", async () => {
    const items = [makeAsset(0)];
    mockApi({
      "/api/v1/me": makeMe({ spaces: [{ id: SPACE_A, name: "Pareja", role: "viewer", archived: false }] }),
      [`/api/v1/spaces/${SPACE_A}/assets`]: { items, next_cursor: null },
    });
    renderAt(`/?ver=${items[0]?.id ?? ""}`);
    const viewer = await screen.findByRole("dialog", { name: "Visor de fotos" });
    expect(within(viewer).queryByRole("button", { name: "Eliminar" })).not.toBeInTheDocument();
  });

  it("recupera y vacía con confirmación escrita", async () => {
    const items = [makeAsset(0), makeAsset(1)];
    let emptied = "";
    const searches: string[] = [];
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/assets`]: (_: RequestInit, url: URL) => {
        searches.push(url.search);
        return { items, next_cursor: null };
      },
      [`POST /api/v1/spaces/${SPACE_A}/assets/batch`]: { count: 1, undo: { action: "trash" } },
      [`POST /api/v1/spaces/${SPACE_A}/trash/empty`]: (init: RequestInit) => {
        emptied = init.body as string;
        return { count: 2 };
      },
    });
    const user = userEvent.setup();
    renderAt("/papelera");
    expect(await screen.findByRole("heading", { name: "Papelera" })).toBeInTheDocument();
    await waitFor(() => expect(searches.some((s) => s.includes("trashed=true"))).toBe(true));
    await user.click((await screen.findAllByRole("button", { name: /^Foto del/ }))[0]!);
    await user.click(screen.getByRole("button", { name: "Recuperar" }));
    expect(await screen.findByText("Recuperada")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Vaciar papelera" }));
    const dialog = await screen.findByRole("dialog", { name: "Vaciar la papelera" });
    const confirm = within(dialog).getByRole("button", { name: "Borrar definitivamente" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Escribe «Pareja» para confirmar"), "Pareja");
    await user.click(confirm);
    expect(await screen.findByText("Se han borrado definitivamente 2 elementos")).toBeInTheDocument();
    expect(JSON.parse(emptied)).toEqual({ confirm_name: "Pareja" });
  });

  it("solo el propietario puede vaciarla", async () => {
    mockApi({
      "/api/v1/me": makeMe({
        spaces: [{ id: SPACE_A, name: "Pareja", role: "collaborator", archived: false }],
      }),
      [`/api/v1/spaces/${SPACE_A}/assets`]: { items: [makeAsset(0)], next_cursor: null },
    });
    renderAt("/papelera");
    await screen.findByRole("heading", { name: "Papelera" });
    expect(screen.queryByRole("button", { name: "Vaciar papelera" })).not.toBeInTheDocument();
  });

  it("muestra la papelera vacía", async () => {
    mockApi();
    renderAt("/papelera");
    expect(await screen.findByRole("heading", { name: "La papelera está vacía" })).toBeInTheDocument();
  });
});

describe("estado de la instancia", () => {
  it("muestra disco, copias, integridad y el aviso del mismo disco", async () => {
    mockApi({
      "/api/v1/admin/users": [],
      "/api/v1/admin/notices": [],
      "/api/v1/admin/audit": { items: [], next_cursor: null },
      "/api/v1/admin/status": {
        version: "abc123",
        open_notices: 0,
        disk: { total: 500e9, used: 100e9, free: 400e9 },
        storage: {
          originals: 30e9,
          derivatives: 3e9,
          exports: 0,
          spaces: [{ id: "s", name: "Pareja", count: 1200, bytes: 30e9 }],
        },
        backup: {
          database: { started_at: NOW, finished_at: NOW, ok: true, detail: {} },
          originals: null,
          manifests: null,
          pending_originals: 0,
          agent: { same_disk: true },
        },
        integrity: {
          started_at: NOW,
          finished_at: NOW,
          ok: false,
          checked: 1200,
          problems: [{ type: "corrupt_original" }],
        },
        queue: { done: 10, failed: 1 },
        library: { built_at: NOW, files: 1200 },
        failed_jobs: [{ kind: "process_asset", error: "MediaError", at: NOW }],
      },
    });
    renderAt("/admin");
    expect(await screen.findByText(/Las copias están en el mismo disco/)).toBeInTheDocument();
    expect(screen.getByText(/100 GB de 500 GB \(20 %\)/)).toBeInTheDocument();
    expect(screen.getByText("1200 elementos · 30 GB")).toBeInTheDocument();
    expect(screen.getByText(/correcta, hace un momento/)).toBeInTheDocument();
    expect(screen.getByText(/1 problemas \(1200 revisados/)).toBeInTheDocument();
    expect(screen.getByText("Tareas fallidas (1)")).toBeInTheDocument();
  });
});
