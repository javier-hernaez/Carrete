import type { components } from "./schema";

type S = components["schemas"];
export type InstanceInfo = S["InstanceInfo"];
export type Me = S["MeOut"];
export type Stage = Me["stage"];
export type SpaceOut = S["SpaceOut"];
export type Member = S["MemberOut"];
export type Invitation = S["InvitationOut"];
export type SessionInfo = S["SessionOut"];
export type AdminUser = S["UserOut"];
export type AuditPage = S["AuditPage"];
export type AdminNotice = S["NoticeOut"];
export type Role = SpaceOut["role"];

/** Error de la API en formato problem+json (RFC 9457). */
export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly detail: string | undefined;
  readonly requestId: string | undefined;
  readonly code: string | undefined;
  readonly extra: Record<string, unknown>;

  constructor(
    status: number,
    title: string,
    detail?: string,
    requestId?: string,
    code?: string,
    extra: Record<string, unknown> = {},
  ) {
    super(detail ?? title);
    this.name = "ApiError";
    this.status = status;
    this.title = title;
    this.detail = detail;
    this.requestId = requestId;
    this.code = code;
    this.extra = extra;
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
  code?: string;
  [key: string]: unknown;
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
      problem.code,
      problem,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });
const patch = (body: unknown): RequestInit => ({ method: "PATCH", body: JSON.stringify(body) });
const del: RequestInit = { method: "DELETE" };
const post: RequestInit = { method: "POST" };

export const api = {
  info: () => apiFetch<InstanceInfo>("/api/v1/info"),
  // Acceso
  setupState: () => apiFetch<{ needed: boolean }>("/api/v1/setup"),
  setup: (body: S["SetupIn"]) => apiFetch<{ stage: Stage }>("/api/v1/setup", json(body)),
  login: (username: string, password: string) =>
    apiFetch<{ stage: Stage }>("/api/v1/auth/login", json({ username, password })),
  verifyTotp: (code: string) => apiFetch<{ stage: Stage }>("/api/v1/auth/totp", json({ code })),
  totpSetup: () => apiFetch<S["TotpSetupOut"]>("/api/v1/auth/totp/setup", post),
  totpEnable: (code: string) =>
    apiFetch<{ recovery_codes: string[] }>("/api/v1/auth/totp/enable", json({ code })),
  totpDisable: () => apiFetch<undefined>("/api/v1/auth/totp/disable", post),
  regenerateCodes: () => apiFetch<{ recovery_codes: string[] }>("/api/v1/auth/recovery-codes", post),
  logout: () => apiFetch<undefined>("/api/v1/auth/logout", post),
  reauth: (password: string, code?: string) =>
    apiFetch<undefined>("/api/v1/auth/reauth", json({ password, code: code || null })),
  changePassword: (current_password: string, new_password: string) =>
    apiFetch<{ sessions_closed: number }>("/api/v1/auth/password", json({ current_password, new_password })),
  sessions: () => apiFetch<SessionInfo[]>("/api/v1/auth/sessions"),
  revokeSession: (id: string) => apiFetch<undefined>(`/api/v1/auth/sessions/${id}`, del),
  revokeOtherSessions: () =>
    apiFetch<{ sessions_closed: number }>("/api/v1/auth/sessions/revoke-others", post),
  me: () => apiFetch<Me>("/api/v1/me"),
  updateMe: (body: S["MeIn"]) => apiFetch<undefined>("/api/v1/me", patch(body)),
  // Espacios
  spaces: () => apiFetch<SpaceOut[]>("/api/v1/spaces"),
  createSpace: (name: string) => apiFetch<SpaceOut>("/api/v1/spaces", json({ name })),
  updateSpace: (id: string, body: S["SpacePatch"]) => apiFetch<SpaceOut>(`/api/v1/spaces/${id}`, patch(body)),
  members: (id: string) => apiFetch<Member[]>(`/api/v1/spaces/${id}/members`),
  changeRole: (space: string, user: string, role: Role) =>
    apiFetch<undefined>(`/api/v1/spaces/${space}/members/${user}`, patch({ role })),
  removeMember: (space: string, user: string) =>
    apiFetch<undefined>(`/api/v1/spaces/${space}/members/${user}`, del),
  invitations: (space: string) => apiFetch<Invitation[]>(`/api/v1/spaces/${space}/invitations`),
  invite: (space: string, role: Role) =>
    apiFetch<Invitation>(`/api/v1/spaces/${space}/invitations`, json({ role })),
  revokeInvitation: (id: string) => apiFetch<undefined>(`/api/v1/invitations/${id}`, del),
  invitationPreview: (token: string) =>
    apiFetch<S["InvitationPreview"]>(`/api/v1/invitations/by-token/${encodeURIComponent(token)}`),
  acceptInvitation: (token: string, body: S["AcceptIn"]) =>
    apiFetch<S["AcceptOut"]>(`/api/v1/invitations/by-token/${encodeURIComponent(token)}/accept`, json(body)),
  resetPreview: (token: string) =>
    apiFetch<S["ResetPreview"]>(`/api/v1/password-resets/${encodeURIComponent(token)}`),
  useReset: (token: string, password: string) =>
    apiFetch<{ stage: Stage }>(`/api/v1/password-resets/${encodeURIComponent(token)}`, json({ password })),
  // Administración
  adminUsers: () => apiFetch<AdminUser[]>("/api/v1/admin/users"),
  adminSetActive: (id: string, active: boolean) =>
    apiFetch<undefined>(`/api/v1/admin/users/${id}/active`, json({ active })),
  adminRevokeSessions: (id: string) => apiFetch<undefined>(`/api/v1/admin/users/${id}/revoke-sessions`, post),
  adminReset: (id: string, reset_totp: boolean) =>
    apiFetch<S["LinkOut"]>(`/api/v1/admin/users/${id}/reset`, json({ reset_totp })),
  adminInvite: () => apiFetch<S["LinkOut"]>("/api/v1/admin/invitations", post),
  adminAudit: (params: Record<string, string>) =>
    apiFetch<AuditPage>(`/api/v1/admin/audit?${new URLSearchParams(params).toString()}`),
  adminNotices: () => apiFetch<AdminNotice[]>("/api/v1/admin/notices"),
  adminAckNotice: (id: string) => apiFetch<undefined>(`/api/v1/admin/notices/${id}/ack`, post),
};
