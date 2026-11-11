import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt, SPACE_A } from "../../test/render";
import { makeAsset } from "../photos/photos.test";
import { describe as phrase } from "./describe";

const NOW = new Date().toISOString();
const entry = (action: string, detail: Record<string, unknown>, actor: string | null = "Lucía") => ({
  id: action,
  occurred_at: NOW,
  actor,
  action,
  detail,
});

describe("actividad y descartadas", () => {
  it("redacta cada acción", () => {
    expect(phrase(entry("asset.uploaded", { uploaded: 34, duplicates: 2 }))).toBe(
      "Lucía subió 34 fotos (2 ya estaban)",
    );
    expect(phrase(entry("album.created", { name: "Asturias 2025" }, "Javier"))).toBe(
      "Javier creó el álbum «Asturias 2025»",
    );
    expect(phrase(entry("album.assets_added", { count: 1, album: "Boda" }))).toBe(
      "Lucía añadió 1 foto a «Boda»",
    );
    expect(phrase(entry("trash.emptied", { count: 3 }, null))).toBe("Alguien vació la papelera (3 fotos)");
    for (const action of [
      "asset.trashed",
      "asset.restored",
      "asset.purged",
      "asset.date_changed",
      "album.renamed",
      "album.deleted",
      "duplicates.resolved",
      "invitation.accepted",
      "space.created",
      "space.renamed",
      "export.created",
      "otra.cosa",
    ]) {
      expect(phrase(entry(action, {}))).not.toBe("");
    }
  });

  it("muestra la actividad del espacio", async () => {
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/activity`]: [entry("asset.uploaded", { uploaded: 34, duplicates: 0 })],
    });
    renderAt("/actividad");
    expect(await screen.findByText("Lucía subió 34 fotos")).toBeInTheDocument();
  });

  it("recupera descartadas", async () => {
    const calls: string[] = [];
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/assets`]: (_: RequestInit, url: URL) => {
        expect(url.searchParams.getAll("review")).toEqual(["discarded"]);
        return { items: [makeAsset(0, { review_state: "discarded" })], next_cursor: null };
      },
      [`POST /api/v1/spaces/${SPACE_A}/assets/batch`]: (init: RequestInit) => {
        calls.push(init.body as string);
        return { count: 1, undo: null };
      },
    });
    const user = userEvent.setup();
    renderAt("/descartadas");
    await user.click((await screen.findAllByRole("button", { name: /^Seleccionar: / }))[0]!);
    await user.click(screen.getByRole("button", { name: "Recuperar" }));
    await waitFor(() =>
      expect(JSON.parse(calls[0] ?? "{}")).toMatchObject({ action: "review", state: "pending" }),
    );
  });

  it("enseña lo que falta en la navegación", async () => {
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/counters`]: { pending_review: 312, duplicates: 8, discarded: 0, trash: 0 },
    });
    renderAt("/");
    expect(await screen.findByLabelText("312 sin revisar")).toBeInTheDocument();
    expect(screen.getByLabelText("8 grupos de repetidas")).toBeInTheDocument();
  });
});
