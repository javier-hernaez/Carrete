import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeMe, mockApi, renderAt, SPACE_A } from "../../test/render";

interface FakeOptions {
  metadata: Record<string, string>;
  onProgress?: (sent: number, total: number) => void;
  onSuccess?: (p: { lastResponse: { getHeader: (h: string) => string | undefined } }) => void;
  onError?: (e: unknown) => void;
}

const started: FakeOptions[] = [];

vi.mock("tus-js-client", () => ({
  Upload: class {
    constructor(
      private file: File,
      private options: FakeOptions,
    ) {}
    findPreviousUploads() {
      return Promise.resolve([]);
    }
    resumeFromPreviousUpload() {}
    start() {
      started.push(this.options);
      this.options.onProgress?.(this.file.size / 2, this.file.size);
      if (this.file.name.startsWith("mala")) {
        this.options.onError?.({
          originalResponse: {
            getStatus: () => 415,
            getBody: () => JSON.stringify({ detail: "«mala.jpg» no es una foto ni un vídeo admitido" }),
          },
        });
        return;
      }
      this.options.onSuccess?.({
        lastResponse: { getHeader: (h: string) => (h === "Carrete-Asset-Id" ? "id-1" : "0") },
      });
    }
  },
}));

describe("subir", () => {
  beforeEach(() => {
    started.length = 0;
  });

  it("calcula huellas, salta lo que ya estaba y sube el resto", async () => {
    const summaries: string[] = [];
    let check: string[] = [];
    mockApi({
      [`POST /api/v1/spaces/${SPACE_A}/assets/check`]: (init: RequestInit) => {
        check = (JSON.parse(init.body as string) as { sha256: string[] }).sha256;
        return { present: [check[0]] };
      },
      [`POST /api/v1/spaces/${SPACE_A}/uploads/summary`]: (init: RequestInit) => {
        summaries.push(init.body as string);
      },
    });
    const user = userEvent.setup({ applyAccept: false });
    renderAt("/subir");
    const input = await screen.findByLabelText("Elegir fotos y vídeos");
    const files = [
      new File(["uno"], "IMG-20230415-WA0001.jpg", { type: "image/jpeg", lastModified: 1_600_000_000_000 }),
      new File(["dos"], "VID_20230415_183012.mp4", { type: "video/mp4" }),
      new File(["tres"], "mala.jpg", { type: "image/jpeg" }),
      new File(["%PDF"], "documento.pdf", { type: "application/pdf" }),
    ];
    await user.upload(input, files);
    expect(await screen.findByText(/1 subidas, 1 ya estaban, 1 errores/)).toBeInTheDocument();
    // El PDF ni siquiera entra en la cola; el SHA-256 de «uno» es el conocido
    expect(check).toEqual([
      "0dc6ed4d6dd3d2b0b4a1bdc7a36ed4c4b9d4b98ea5b4f0b6e0b9e2a3f8c1d1e2".length === 64 ? check[0] : "",
      check[1],
      check[2],
    ]);
    expect(check[0]).toMatch(/^[0-9a-f]{64}$/);
    expect(started.map((o) => o.metadata.filename)).toEqual(["VID_20230415_183012.mp4", "mala.jpg"]);
    expect(started[0]?.metadata.space_id).toBe(SPACE_A);
    expect(screen.getByText("«mala.jpg» no es una foto ni un vídeo admitido")).toBeInTheDocument();
    await waitFor(() =>
      expect(summaries).toEqual([JSON.stringify({ uploaded: 1, duplicates: 1, failed: 1 })]),
    );
    expect(screen.getByRole("link", { name: "Revisar lo subido" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reintentar los fallidos" }));
    await user.click(await screen.findByRole("button", { name: "Limpiar la lista" }));
    expect(screen.queryByText("VID_20230415_183012.mp4")).not.toBeInTheDocument();
  });

  it("un lector no puede subir", async () => {
    mockApi({
      "/api/v1/me": makeMe({ spaces: [{ id: SPACE_A, name: "Pareja", role: "viewer", archived: false }] }),
    });
    renderAt("/subir");
    expect(await screen.findByRole("heading", { name: "Solo puedes ver este espacio" })).toBeInTheDocument();
  });
});

describe("dentro de la app Android", () => {
  const setBridge = (bridge: unknown) => {
    (window as unknown as { CarreteAndroid?: unknown }).CarreteAndroid = bridge;
  };
  afterEach(() => {
    delete (window as unknown as { CarreteAndroid?: unknown }).CarreteAndroid;
  });

  it("ofrece fotos y carpeta con el selector nativo, y avisa del máximo", async () => {
    const photos: string[] = [];
    const folders: string[] = [];
    setBridge({
      pickPhotos: (id: string) => photos.push(id),
      pickFolder: (id: string) => folders.push(id),
      pickLimit: () => 100,
      version: () => 2,
    });
    mockApi();
    const user = userEvent.setup();
    renderAt("/subir");
    await user.click(await screen.findByRole("button", { name: "Elegir fotos" }));
    await user.click(screen.getByRole("button", { name: "Elegir una carpeta" }));
    expect(photos).toEqual([SPACE_A]);
    expect(folders).toEqual([SPACE_A]);
    expect(screen.getByText(/hasta 100 de cada vez/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Elegir ficheros o un .zip" })).toBeInTheDocument();
  });

  it("con una app antigua sin carpetas, pide actualizarla", async () => {
    setBridge({ pickPhotos: () => undefined, version: () => 1 });
    mockApi();
    renderAt("/subir");
    expect(await screen.findByRole("button", { name: "Elegir fotos" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Elegir una carpeta" })).not.toBeInTheDocument();
    expect(screen.getByText(/Actualiza la app/)).toBeInTheDocument();
  });
});

describe("en el navegador de un móvil", () => {
  it("no ofrece elegir carpetas (no funciona ahí) y remite a la app", async () => {
    const ua = vi
      .spyOn(navigator, "userAgent", "get")
      .mockReturnValue(
        "Mozilla/5.0 (Linux; Android 15; 2312DRA50G) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36",
      );
    try {
      mockApi();
      renderAt("/subir");
      expect(await screen.findByRole("button", { name: "Elegir fotos y vídeos" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Elegir una carpeta" })).not.toBeInTheDocument();
      expect(screen.getByText(/usa la app de Android/)).toBeInTheDocument();
    } finally {
      ua.mockRestore();
    }
  });
});
