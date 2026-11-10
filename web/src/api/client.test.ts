import { describe, expect, it, vi } from "vitest";

import { api, ApiError, apiFetch, NetworkError } from "./client";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  return new Response(JSON.stringify(body), { ...init, headers });
}

describe("apiFetch", () => {
  it("envía la cabecera anti-CSRF y la cookie del mismo origen", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch("/api/v1/algo", { method: "POST", body: JSON.stringify({ a: 1 }) });
    const [, init] = fetchMock.mock.calls[0]!;
    const headers = new Headers(init?.headers);
    expect(headers.get("X-Carrete-Request")).toBe("1");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init?.credentials).toBe("same-origin");
  });

  it("convierte problem+json en ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ title: "Not Found", detail: "No existe", request_id: "r1" }, { status: 404 }),
    );
    const error = await apiFetch("/api/v1/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, detail: "No existe", requestId: "r1", message: "No existe" });
  });

  it("tolera errores sin cuerpo JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<html>", { status: 502, statusText: "Bad Gateway", headers: { "X-Request-ID": "r2" } }),
    );
    const error = await apiFetch("/api/v1/x").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 502, title: "Bad Gateway", requestId: "r2" });
  });

  it("distingue los fallos de red", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(apiFetch("/api/v1/x")).rejects.toBeInstanceOf(NetworkError);
  });

  it("devuelve undefined en 204", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiFetch("/api/v1/x", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("no fija Content-Type en FormData", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}));
    await apiFetch("/api/v1/x", { method: "POST", body: new FormData() });
    expect(new Headers(fetchMock.mock.calls[0]![1]?.headers).has("Content-Type")).toBe(false);
  });

  it("consulta la información de la instancia", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ name: "Carrete", version: "1", map_enabled: false }),
    );
    await expect(api.info()).resolves.toEqual({ name: "Carrete", version: "1", map_enabled: false });
  });
});
