import { ApiError, NetworkError } from "../api/client";
import { t } from "../i18n";

/** Error con un mensaje ya pensado para la persona (p. ej. del navegador al usar una llave de acceso). */
export class UserError extends Error {}

export function errorMessage(error: unknown): string {
  if (error instanceof UserError) return error.message;
  if (error instanceof ApiError) return error.detail ?? error.title;
  if (error instanceof NetworkError) return t("error.network");
  return t("error.generic");
}

export function hasCode(error: unknown, code: string): boolean {
  return error instanceof ApiError && error.code === code;
}
