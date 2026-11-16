/** Puente mínimo que expone la app Android: elegir fotos con el selector del sistema y
 * subirlas con su cola en segundo plano, que sigue aunque se apague la pantalla. */
interface CarreteAndroid {
  pickPhotos: (spaceId: string) => void;
  version: () => number;
  /** Desde la versión que corrige el cierre con más de 100 fotos; las anteriores no lo tienen. */
  pickLimit?: () => number;
  /** Carpeta entera con el selector de Android, sin límite y sin copiar (versiones nuevas). */
  pickFolder?: (spaceId: string) => void;
}

export function androidBridge(): CarreteAndroid | undefined {
  return (window as unknown as { CarreteAndroid?: CarreteAndroid }).CarreteAndroid;
}

/** Navegador de un móvil o tableta (sin la app): ahí no se pueden elegir carpetas desde una web. */
export function isMobileBrowser(): boolean {
  const ua = navigator.userAgent;
  return /Android|iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
}
