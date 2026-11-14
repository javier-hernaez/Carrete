import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";

import type { Me } from "../api/client";
import { routes } from "../app/router";

export function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return {
    router,
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  };
}

export const SPACE_A = "11111111-1111-7111-8111-111111111111";
export const SPACE_B = "22222222-2222-7222-8222-222222222222";

export function makeMe(overrides: Partial<Me> = {}): Me {
  return {
    id: "00000000-0000-7000-8000-000000000001",
    username: "javier",
    display_name: "Javier",
    is_admin: true,
    stage: "full",
    has_totp: true,
    require_2fa: true,
    recovery_codes_left: 10,
    reauth_until: new Date(Date.now() + 600_000).toISOString(),
    current_space_id: SPACE_A,
    spaces: [
      { id: SPACE_A, name: "Pareja", role: "owner", archived: false },
      { id: SPACE_B, name: "Familia", role: "viewer", archived: false },
    ],
    preferences: {},
    ...overrides,
  };
}

type Handler = (init: RequestInit | undefined, url: URL) => unknown;
export type Routes = Record<string, unknown>;

function json(body: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export class HttpError {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {}
}

/**
 * Simula la API: «MÉTODO /ruta» → respuesta (valor o función). Las rutas sin método valen para GET.
 * Devuelve el espía de fetch para comprobar las llamadas.
 */
export function mockApi(routes: Routes = {}) {
  const table: Routes = {
    "GET /api/v1/info": { name: "Carrete", version: "1.2.3", map_enabled: false },
    "GET /api/v1/me": makeMe(),
    "PATCH /api/v1/me": undefined,
    ...Object.fromEntries(Object.entries(routes).map(([k, v]) => [k.includes(" ") ? k : `GET ${k}`, v])),
  };
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = new URL(
      typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
      "http://localhost",
    );
    const key = `${init?.method ?? "GET"} ${url.pathname}`;
    const entry = table[key];
    if (!(key in table) && key.startsWith("GET ")) {
      // Por defecto, un espacio vacío.
      if (url.pathname.endsWith("/assets")) return Promise.resolve(json({ items: [], next_cursor: null }));
      if (url.pathname.endsWith("/timeline")) return Promise.resolve(json({ total: 0, months: [] }));
      if (["/members", "/albums", "/suggestions", "/passkeys", "/map"].some((s) => url.pathname.endsWith(s)))
        return Promise.resolve(json([]));
    }
    if (!(key in table))
      return Promise.resolve(json({ title: "Not Found", detail: `Sin simular: ${key}` }, 404));
    try {
      const value = typeof entry === "function" ? (entry as Handler)(init, url) : entry;
      if (value instanceof HttpError) return Promise.resolve(json(value.body, value.status));
      return Promise.resolve(value === undefined ? json(null, 204) : json(value));
    } catch (error) {
      return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }
  });
}

export const unauthorized = new HttpError(401, { title: "Unauthorized", code: "not_authenticated" });
