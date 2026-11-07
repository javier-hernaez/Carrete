import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { routes } from "../app/router";

export function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return {
    router,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  };
}

export function mockInfo(info: { map_enabled: boolean; version?: string }) {
  return new Response(JSON.stringify({ name: "Carrete", version: info.version ?? "1.2.3", ...info }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
