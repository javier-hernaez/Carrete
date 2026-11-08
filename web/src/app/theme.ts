/** Aplica el tema elegido en Ajustes; «system» deja que mande prefers-color-scheme. */
export function applyTheme(theme: string | undefined) {
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}
