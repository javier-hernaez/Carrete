import { createContext, useContext } from "react";

import type { Me } from "../api/client";

export type SpaceSummary = Me["spaces"][number];

export interface SessionValue {
  me: Me;
  space: SpaceSummary | null;
  setSpace: (id: string) => void;
  refresh: () => Promise<unknown>;
  /** Pide contraseña (y código) otra vez y reintenta la acción: para las acciones sensibles. */
  withReauth: <T>(action: () => Promise<T>) => Promise<T>;
}

export const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession fuera de AuthGate");
  return value;
}

export function canEdit(space: SpaceSummary | null): boolean {
  return space !== null && space.role !== "viewer";
}

export function isOwner(space: SpaceSummary | null): boolean {
  return space?.role === "owner";
}
