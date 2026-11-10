import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // No se reintenta lo que el servidor ha rechazado a propósito (4xx); sí los fallos de red.
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
        refetchOnWindowFocus: false,
      },
    },
  });
}
