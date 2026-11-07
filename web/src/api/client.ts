import type { components } from "./schema";

export type InstanceInfo = components["schemas"]["InstanceInfo"];

/** Error de la API en formato problem+json (RFC 9457). */
export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail: string | undefined;
  readonly requestId: string | undefined;

  constructor(status: number, title: string, detail?: string, requestId?: string) {
    super(detail ?? title);
    this.name = "ApiError";
    this.status = status;
    this.title = title;
    this.detail = detail;
    this.requestId = requestId;
  }
}

/** Error de red: el servidor no respondió. */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super("network", { cause });
    this.name = "NetworkError";
  }
}

interface Problem {
  title?: string;
  detail?: string;
  request_id?: string;
}

/**
 * Petición a la API del mismo origen. Toda petición lleva la cabecera X-Carrete-Request: el servidor
 * la exige en las que modifican (defensa CSRF), y un formulario de otro sitio no puede
 * ponerla.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Carrete-Request", "1");
  if (init.body !== undefined && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  } catch (error) {
    throw new NetworkError(error);
  }

  if (!response.ok) {
    let problem: Problem = {};
    try {
      problem = (await response.json()) as Problem;
    } catch {
      // Respuesta sin cuerpo JSON (p. ej. un proxy): basta con el código.
    }
    throw new ApiError(
      response.status,
      problem.title ?? response.statusText,
      problem.detail,
      problem.request_id ?? response.headers.get("X-Request-ID") ?? undefined,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  info: () => apiFetch<InstanceInfo>("/api/v1/info"),
};
