import { ApiError, NetworkError } from "../api/client";
import { t } from "../i18n";

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail ?? error.title;
  if (error instanceof NetworkError) return t("error.network");
  return t("error.generic");
}

export function hasCode(error: unknown, code: string): boolean {
  return error instanceof ApiError && error.code === code;
}
