import type { Role } from "../api/client";

export const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "owner", label: "Propietario" },
  { value: "collaborator", label: "Colaborador" },
  { value: "viewer", label: "Lector" },
];
