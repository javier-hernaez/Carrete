import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { api } from "../../api/client";
import { makeMe, mockApi, renderAt, SPACE_A } from "../../test/render";
import { makeAsset } from "../photos/photos.test";
import { downloadSelection, volumeUrl } from "./download";

const NOW = new Date().toISOString();
const job = (state: string, extra: Record<string, unknown> = {}) => ({
  id: "e1",
  state,
  progress: state === "ready" ? 1 : 0.4,
  total_items: 120,
  total_bytes: 3e9,
  files:
    state === "ready"
      ? [
          { number: 1, name: "Pareja (1 de 2).zip", size: 2e9 },
          { number: 2, name: "Pareja (2 de 2).zip", size: 1e9 },
        ]
      : [],
  params: {},
  error: null,
  created_at: NOW,
  expires_at: NOW,
  mine: true,
  ...extra,
});

describe("exportar", () => {
  it("prepara una exportación del espacio y descarga sus volúmenes", async () => {
    let body = "";
    let state = "running";
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/albums`]: [],
      [`/api/v1/spaces/${SPACE_A}/exports`]: () => [job(state)],
      [`POST /api/v1/spaces/${SPACE_A}/exports`]: (init: RequestInit) => {
        body = init.body as string;
        state = "ready";
        return job("queued");
      },
      [`DELETE /api/v1/spaces/${SPACE_A}/exports/e1`]: undefined,
    });
    const user = userEvent.setup();
    renderAt("/exportar");
    expect(await screen.findByText("Preparando")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Carpetas"), "date");
    await user.selectOptions(screen.getByLabelText("Qué incluir"), "all");
    await user.click(screen.getByRole("button", { name: "Preparar la exportación" }));
    await waitFor(() =>
      expect(JSON.parse(body)).toMatchObject({
        target: "zip",
        structure: "date",
        include: "all",
        album_ids: [],
        volume_bytes: 4 * 1024 ** 3,
      }),
    );
    const link = await screen.findByRole("link", { name: "Pareja (1 de 2).zip" });
    expect(link).toHaveAttribute("href", volumeUrl(SPACE_A, "e1", 1));
    await user.click(screen.getByRole("button", { name: "Borrar" }));
  });

  it("quien no es propietario solo exporta álbumes", async () => {
    mockApi({
      "/api/v1/me": makeMe({ spaces: [{ id: SPACE_A, name: "Pareja", role: "viewer", archived: false }] }),
      [`/api/v1/spaces/${SPACE_A}/albums`]: [
        {
          id: "al1",
          name: "Boda",
          description: null,
          count: 4,
          cover_asset_id: null,
          sort_mode: "date",
          first: null,
          last: null,
        },
      ],
      [`/api/v1/spaces/${SPACE_A}/exports`]: [],
    });
    const user = userEvent.setup();
    renderAt("/exportar");
    const scope = await screen.findByLabelText("Qué exportar");
    expect(within(scope).queryByRole("option", { name: /Todo el espacio/ })).not.toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Preparar la exportación" });
    expect(button).toBeDisabled();
    await user.click(await screen.findByLabelText(/Boda/));
    expect(button).toBeEnabled();
  });

  it("descarga una selección cuando el ZIP está listo", async () => {
    const states = ["queued", "running", "ready"];
    vi.spyOn(api, "createExport").mockResolvedValue(job("queued"));
    vi.spyOn(api, "exportJob").mockImplementation(() =>
      Promise.resolve(job(states.shift() ?? "ready") as never),
    );
    const clicks: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push(this.getAttribute("href") ?? "");
    });
    await downloadSelection(SPACE_A, [makeAsset(0).id, makeAsset(1).id], () => Promise.resolve());
    expect(clicks).toEqual([volumeUrl(SPACE_A, "e1", 1), volumeUrl(SPACE_A, "e1", 2)]);
  });
});
