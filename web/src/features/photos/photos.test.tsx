import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AssetItem } from "../../api/client";
import {
  decodeBase64,
  thumbHashToApproximateAspectRatio,
  thumbHashToPlaceholder,
  thumbHashToRGBA,
} from "../../media/thumbhash";
import { mockApi, renderAt, SPACE_A } from "../../test/render";
import { activeCount, readFilters, toApiParams } from "./filters";
import { formatBytes, formatDateTime, formatDay, formatDuration } from "./format";

// ThumbHash de referencia (una puesta de sol) del sitio de ThumbHash.
const HASH = "1QcSHQRnh493V4dIh4eXh1h4kJUI";

export function makeAsset(n: number, overrides: Partial<AssetItem> = {}): AssetItem {
  return {
    id: `00000000-0000-7000-8000-${String(n).padStart(12, "0")}`,
    kind: "photo",
    taken_at: `2023-04-${String(15 - Math.floor(n / 3)).padStart(2, "0")}T18:30:${String(n % 60).padStart(2, "0")}`,
    taken_at_offset: 120,
    date_doubtful: false,
    width: 640,
    height: 480,
    duration_ms: null,
    thumbhash: HASH,
    review_state: "pending",
    is_favorite: false,
    processing_state: "ready",
    source: "camera",
    ...overrides,
  };
}

describe("ThumbHash", () => {
  it("descodifica la imagen de referencia", () => {
    const hash = decodeBase64(HASH);
    const ratio = thumbHashToApproximateAspectRatio(hash);
    expect(ratio).toBeGreaterThan(0);
    const { w, h, rgba } = thumbHashToRGBA(hash);
    expect(Math.max(w, h)).toBe(32);
    expect(w / h).toBeCloseTo(ratio, 0);
    expect(rgba.length).toBe(w * h * 4);
    expect(rgba[3]).toBe(255);
  });

  it("da un color medio aunque no haya canvas", () => {
    const placeholder = thumbHashToPlaceholder(HASH);
    expect(placeholder.color).toMatch(/^rgb\(\d+ \d+ \d+\)$/);
    expect(thumbHashToPlaceholder(null).url).toBeNull();
    expect(thumbHashToPlaceholder("@@no-es-base64@@").url).toBeNull();
  });
});

describe("formatos", () => {
  it("muestra la hora de pared y el desfase", () => {
    expect(formatDateTime("2023-04-15T18:30:12", 540)).toBe("sábado, 15 de abril de 2023, 18:30 (UTC+9)");
    expect(formatDateTime("2023-04-15T18:30:12", -210)).toContain("(UTC−3:30)");
    expect(formatDateTime("2023-04-15T18:30:12", null)).not.toContain("UTC");
    expect(formatDay(`${new Date().getFullYear()}-01-01`)).not.toMatch(/de \d{4}$/);
  });

  it("formatea duraciones y tamaños", () => {
    expect(formatDuration(65_000)).toBe("1:05");
    expect(formatDuration(3_725_000)).toBe("1:02:05");
    expect(formatDuration(null)).toBe("");
    expect(formatBytes(3_400_000)).toBe("3,4 MB");
    expect(formatBytes(512)).toBe("512 B");
  });
});

describe("filtros", () => {
  it("traduce la URL a parámetros de la API", () => {
    const f = readFilters(
      new URLSearchParams(
        "estado=todas&fav=1&tipo=video&origen=whatsapp&de=2023-01-01&dudosa=1&sin-album=1&q=playa",
      ),
    );
    expect(activeCount(f)).toBe(8);
    const p = toApiParams(f, { limit: "10" });
    expect(p.getAll("review")).toEqual(["pending", "kept", "discarded"]);
    expect(p.get("favorite")).toBe("true");
    expect(p.get("kind")).toBe("video");
    expect(p.get("source")).toBe("whatsapp");
    expect(p.get("date_from")).toBe("2023-01-01");
    expect(p.get("doubtful")).toBe("true");
    expect(p.get("no_album")).toBe("true");
    expect(p.get("q")).toBe("playa");
    expect(p.get("limit")).toBe("10");
    expect(activeCount(readFilters(new URLSearchParams()))).toBe(0);
  });
});

describe("línea temporal y visor", () => {
  const items = [
    makeAsset(0, { is_favorite: true }),
    makeAsset(1, { kind: "video", duration_ms: 12_000 }),
    makeAsset(4),
    makeAsset(5, { processing_state: "pending" }),
  ];

  function api(extra = {}) {
    return mockApi({
      [`/api/v1/spaces/${SPACE_A}/assets`]: { items, next_cursor: null },
      [`/api/v1/spaces/${SPACE_A}/timeline`]: {
        total: 4,
        months: [
          { year: 2023, month: 4, count: 3 },
          { year: 2022, month: 1, count: 1 },
        ],
      },
      [`/api/v1/spaces/${SPACE_A}/members`]: [],
      [`/api/v1/assets/${items[0]?.id ?? ""}`]: {
        ...items[0],
        space_id: SPACE_A,
        original_filename: "IMG_1.jpg",
        size_bytes: 2_000_000,
        mime: "image/jpeg",
        sha256: "a".repeat(64),
        uploaded_by: "Lucía",
        uploaded_at: "2023-04-16T10:00:00Z",
        uploaded_via: "web",
        taken_at_source: "exif",
        camera: "Pixel 8",
        lat: 43.36,
        lon: -5.85,
        description: null,
        video_codec: null,
        has_preview_video: false,
        processing_error: null,
        contributors: [],
        trashed_at: null,
        albums: [],
      },
      ...extra,
    });
  }

  it("agrupa por días y abre el visor", async () => {
    api();
    const user = userEvent.setup();
    renderAt("/");
    expect(await screen.findByText("4 elementos")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /15 de abril de 2023/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /14 de abril de 2023/i })).toBeInTheDocument();
    expect(screen.getByText("Procesando…")).toBeInTheDocument();
    expect(screen.getByText(/▶ 0:12/)).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: /Foto del sábado, 15 de abril de 2023/ })[0]!);
    const viewer = await screen.findByRole("dialog", { name: "Visor de fotos" });
    expect(within(viewer).getByText("1 de 4")).toBeInTheDocument();
    expect(within(viewer).getByRole("link", { name: "Descargar el original" })).toHaveAttribute(
      "href",
      `/api/v1/assets/${items[0]?.id ?? ""}/original`,
    );

    fireEvent.keyDown(window, { key: "i" });
    expect(await within(viewer).findByText("Pixel 8")).toBeInTheDocument();
    expect(within(viewer).getByText("Lucía")).toBeInTheDocument();
    expect(within(viewer).getByText("43.36000, -5.85000")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(within(viewer).getByText("2 de 4")).toBeInTheDocument();
    expect(viewer.querySelector("video")).not.toBeNull();
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(within(viewer).getByText("1 de 4")).toBeInTheDocument();

    // Deslizar con el dedo pasa a la siguiente
    const stage = viewer.querySelector("img")?.parentElement as HTMLElement;
    fireEvent.pointerDown(stage, { pointerId: 1, clientX: 300, clientY: 200 });
    fireEvent.pointerUp(stage, { pointerId: 1, clientX: 100, clientY: 205 });
    expect(within(viewer).getByText("2 de 4")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Visor de fotos" })).not.toBeInTheDocument(),
    );
  });

  it("filtra y salta a un mes", async () => {
    const calls: string[] = [];
    api({
      [`/api/v1/spaces/${SPACE_A}/assets`]: (_: RequestInit, url: URL) => {
        calls.push(url.search);
        return { items, next_cursor: null };
      },
    });
    const user = userEvent.setup();
    renderAt("/");
    await screen.findByText("4 elementos");
    await user.click(screen.getByText("Filtros"));
    await user.selectOptions(screen.getByLabelText("Tipo"), "video");
    await waitFor(() => expect(calls.some((c) => c.includes("kind=video"))).toBe(true));
    await user.click(screen.getByLabelText("Solo favoritas"));
    await waitFor(() => expect(calls.some((c) => c.includes("favorite=true"))).toBe(true));
    await user.click(screen.getByRole("button", { name: "Quitar filtros" }));
    await user.selectOptions(screen.getByLabelText("Ir a"), "2022-1");
    await waitFor(() => expect(calls.some((c) => c.includes("start=2022-01-31"))).toBe(true));
    expect(screen.getByText(/Mostrando desde 2022-01-31/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Volver a lo más reciente" }));
    expect(screen.queryByText(/Mostrando desde/)).not.toBeInTheDocument();
  });

  it("explica cuando no hay nada", async () => {
    mockApi({
      [`/api/v1/spaces/${SPACE_A}/assets`]: { items: [], next_cursor: null },
      [`/api/v1/spaces/${SPACE_A}/timeline`]: { total: 0, months: [] },
    });
    renderAt("/?tipo=video");
    expect(await screen.findByRole("heading", { name: "Nada con estos filtros" })).toBeInTheDocument();
  });
});
