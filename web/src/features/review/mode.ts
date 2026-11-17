export type ReviewMode = "grid" | "one";

const KEY = "carrete:revisar-modo";

/** Cuadrícula por defecto: decidir en bloque es lo más rápido con muchas fotos. */
export function readMode(): ReviewMode {
  try {
    return localStorage.getItem(KEY) === "one" ? "one" : "grid";
  } catch {
    return "grid";
  }
}

export function saveMode(mode: ReviewMode) {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    // Sin almacenamiento local: se recuerda solo mientras la página siga abierta.
  }
}
