/** Puente mínimo que expone la app Android: elegir fotos con el selector del sistema y
 * subirlas con su cola en segundo plano, que sigue aunque se apague la pantalla. */
interface CarreteAndroid {
  pickPhotos: (spaceId: string) => void;
  version: () => number;
  /** Desde la versión que corrige el cierre con más de 100 fotos; las anteriores no lo tienen. */
  pickLimit?: () => number;
}

export function androidBridge(): CarreteAndroid | undefined {
  return (window as unknown as { CarreteAndroid?: CarreteAndroid }).CarreteAndroid;
}
