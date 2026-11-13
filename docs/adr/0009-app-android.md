# 0009 — App Android: WebView, cola nativa propia y pruebas en la JVM

- **Estado**: aceptada
- **Fecha**: 2026-11-13

## Contexto

La app usa Kotlin, Gradle y WorkManager, con la interfaz principal en WebView y una capa nativa
para «Compartir», el selector del sistema, la cola de subida en segundo plano y las credenciales.

## Decisión

- **Proyecto Gradle** estándar (AGP 8.7, Kotlin 2.0, `compileSdk`/`targetSdk` 34, `minSdk` 28). En
  local se compila dentro de Docker con `android/build.sh`, usando volúmenes propios para el SDK y para
  Gradle (el SDK se copió del de Atalaya, sin tocarlo); en el CI, con `./gradlew`.
- **Dependencias mínimas**: `core-ktx`, `activity-ktx` (selector de fotos del sistema y permisos),
  `work-runtime-ktx` y OkHttp. Sin AppCompat ni Material: las tres pantallas nativas son sencillas y la
  interfaz de verdad es la web.
- **Cliente tus propio sobre OkHttp** (`Tus.kt`), igual que el servidor (ADR 0007): crear, consultar
  el desplazamiento (`HEAD`) y enviar trozos de 16 MB; la cola recuerda la dirección de cada subida para
  reanudarla tras un corte, un reinicio o que el sistema mate la app.
- **Cola persistente en ficheros** (`QueueStore`): un JSON por elemento y la copia del fichero en el
  almacenamiento privado (los permisos sobre URIs compartidas son temporales). Más simple que
  Room y suficiente para cientos de elementos.
- **Sesión**: *token* de dispositivo cifrado con una clave del Android Keystore; la WebView obtiene su
  propia cookie canjeando un código de un solo uso (60 s) en `/api/v1/auth/device/web`. La contraseña
  no se guarda nunca. El inicio de sesión de la app es la única ruta exenta de la defensa CSRF: no
  establece cookies.
- **Puente JavaScript mínimo** (`CarreteAndroid.pickPhotos`), que comprueba el origen en cada llamada.
- **Pruebas en la JVM** con JUnit y MockWebServer (cola, cliente tus con corte y reanudación, URL del
  servidor), en lugar de Robolectric: cubren la lógica que importa sin descargar Android entero para las
  pruebas. Lo que depende del sistema (Compartir, notificaciones, pantalla apagada) se prueba a mano.
- **QR**: la web muestra un QR con `carrete:https://…`; la cámara del móvil lo abre en la app, que se
  registra para ese esquema. Así no hace falta incluir un lector de códigos.

## Pendiente

- **Bloqueo con huella o PIN**: no incluido en esta versión.
- **Prueba guiada en un móvil real**: compartir 50 fotos desde WhatsApp con la
  pantalla apagada a mitad de proceso. Ver `docs/operacion.md`.
