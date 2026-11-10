import { es, type MessageKey } from "./es";

export type { MessageKey };

/** Traduce una clave y sustituye las variables «{nombre}». Preparado para añadir idiomas. */
export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  const template: string = es[key];
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = vars[name];
    return value === undefined ? match : String(value);
  });
}
