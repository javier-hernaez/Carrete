/** Une nombres de clase descartando los vacíos. Siempre devuelve una cadena. */
export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
