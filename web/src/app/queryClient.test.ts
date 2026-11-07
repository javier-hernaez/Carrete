import { describe, expect, it } from "vitest";

import { ApiError, NetworkError } from "../api/client";
import { createQueryClient } from "./queryClient";

describe("política de reintentos", () => {
  const retry = createQueryClient().getDefaultOptions().queries?.retry as (n: number, e: Error) => boolean;

  it("no reintenta rechazos del servidor", () => {
    expect(retry(0, new ApiError(403, "Forbidden"))).toBe(false);
  });

  it("reintenta fallos de red y del servidor, con límite", () => {
    expect(retry(0, new NetworkError(null))).toBe(true);
    expect(retry(1, new ApiError(503, "Unavailable"))).toBe(true);
    expect(retry(2, new NetworkError(null))).toBe(false);
  });
});
