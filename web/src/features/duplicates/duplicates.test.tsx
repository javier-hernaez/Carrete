import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderAt, SPACE_A } from "../../test/render";
import { makeAsset } from "../photos/photos.test";

function member(n: number, extra: Record<string, unknown>) {
  return {
    ...makeAsset(n),
    size_bytes: 3_000_000,
    original_filename: `f${n}.jpg`,
    has_exif_date: true,
    best: false,
    ...extra,
  };
}

const GROUPS = [
  {
    id: "g1",
    distance: 1,
    members: [
      member(0, { best: true, width: 4000, height: 3000 }),
      member(1, { source: "whatsapp", width: 1600, height: 1200, has_exif_date: false, size_bytes: 200_000 }),
    ],
  },
  { id: "g2", distance: 5, members: [member(2, { best: true }), member(3, {})] },
];

describe("repetidas", () => {
  it("resuelve, deshace, elige a mano y descarta grupos", async () => {
    const calls: string[] = [];
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/duplicates`]: GROUPS,
      [`POST /api/v1/spaces/${SPACE_A}/duplicates/g1/resolve`]: (init: RequestInit) => {
        calls.push(`resolve g1 ${init.body as string}`);
        return { trashed: [GROUPS[0]?.members[1]?.id] };
      },
      [`POST /api/v1/spaces/${SPACE_A}/duplicates/g2/resolve`]: (init: RequestInit) => {
        calls.push(`resolve g2 ${init.body as string}`);
        return { trashed: [] };
      },
      [`POST /api/v1/spaces/${SPACE_A}/duplicates/g1/reopen`]: () => {
        calls.push("reopen g1");
      },
      [`POST /api/v1/spaces/${SPACE_A}/duplicates/g2/dismiss`]: () => {
        calls.push("dismiss g2");
      },
      [`POST /api/v1/spaces/${SPACE_A}/assets/batch`]: () => {
        calls.push("restore");
        return { count: 1, undo: null };
      },
    });
    const user = userEvent.setup();
    renderAt("/repetidas");
    const list = await screen.findByRole("list", { name: "Grupos de repetidas" });
    const first = (await within(list).findAllByRole("listitem"))[0]!;
    expect(within(first).getByRole("button", { name: /^Mejor Se queda/ })).toBeInTheDocument();
    expect(within(first).getByText(/4000×3000/)).toBeInTheDocument();
    expect(within(first).getByText(/WhatsApp/)).toBeInTheDocument();
    await user.click(within(first).getByRole("button", { name: "Quedarme con la mejor" }));
    await waitFor(() =>
      expect(calls[0]).toBe(`resolve g1 ${JSON.stringify({ keep: [GROUPS[0]?.members[0]?.id] })}`),
    );
    await user.click(await screen.findByRole("button", { name: "Deshacer" }));
    await waitFor(() => expect(calls.slice(1, 3)).toEqual(["restore", "reopen g1"]));

    const second = within(screen.getByRole("list", { name: "Grupos de repetidas" })).getAllByRole(
      "listitem",
    )[1]!;
    await user.click(within(second).getByRole("button", { name: /^Papelera: f3.jpg/ }));
    await user.click(within(second).getByRole("button", { name: "Quedarme con las marcadas" }));
    await waitFor(() => expect(calls[3]).toContain('"keep":['));
    await user.click(within(second).getByRole("button", { name: "No son repetidas" }));
    await waitFor(() => expect(calls).toContain("dismiss g2"));
  });

  it("resuelve los evidentes con resumen previo", async () => {
    const calls: string[] = [];
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/duplicates`]: GROUPS,
      [`POST /api/v1/spaces/${SPACE_A}/duplicates/resolve-obvious`]: (_: RequestInit, url: URL) => {
        calls.push(url.search);
        return url.search
          ? { groups: 1, keep: 1, trash: 1, trashed: ["x"], group_ids: ["g1"] }
          : { groups: 1, keep: 1, trash: 1, trashed: [], group_ids: [] };
      },
    });
    const user = userEvent.setup();
    renderAt("/repetidas");
    await user.click(await screen.findByRole("button", { name: "Resolver los evidentes" }));
    const dialog = await screen.findByRole("dialog", { name: "Resolver los grupos evidentes" });
    await user.click(within(dialog).getByRole("button", { name: "Resolver 1 grupos" }));
    expect(await screen.findByText("1 grupos resueltos; 1 a la papelera")).toBeInTheDocument();
    expect(calls).toEqual(["", "?apply=true"]);
  });

  it("vacío", async () => {
    mockApi({ [`/api/v1/spaces/${SPACE_A}/duplicates`]: [] });
    renderAt("/repetidas");
    expect(await screen.findByRole("heading", { name: "No hay repetidas" })).toBeInTheDocument();
  });
});
