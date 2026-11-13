#!/bin/sh
# Compila la app Android dentro de Docker (sin instalar nada en el equipo).
#
#   ./build.sh                → pruebas + lint + APK firmado en build/carrete.apk
#   ./build.sh test           → solo las pruebas unitarias
#   CARRETE_PUBLIC_URL=https://…:10000 ./build.sh   → la app ya trae esa dirección
#
# Volúmenes de Docker: carrete-android-sdk (SDK de Android) y carrete-gradle (Gradle y dependencias).
# La firma (keystore.jks) se crea la primera vez: GUÁRDALA con tus copias. Sin ella no se puede
# actualizar la app ya instalada en los móviles (Android exige la misma firma).
set -eu
# (en CI se usa ./gradlew; aquí, el Gradle del volumen para no descargarlo dos veces)
cd "$(dirname "$0")"

if [ -z "${IN_DOCKER:-}" ]; then
  exec docker run --rm -e IN_DOCKER=1 -e CARRETE_PUBLIC_URL="${CARRETE_PUBLIC_URL:-}" \
    -e CARRETE_APK_VERSION_CODE="${CARRETE_APK_VERSION_CODE:-$(( $(date +%s) / 60 ))}" \
    -e CARRETE_APK_VERSION_NAME="${CARRETE_APK_VERSION_NAME:-0.1.0}" \
    -e CARRETE_KEYSTORE_PASSWORD="${CARRETE_KEYSTORE_PASSWORD:-}" \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    -v "$PWD":/app -v carrete-android-sdk:/sdk -v carrete-gradle:/g -w /app eclipse-temurin:17-jdk sh build.sh "$@"
fi

export ANDROID_HOME=/sdk GRADLE_USER_HOME=/g/home
GRADLE=/g/gradle-8.10.2/bin/gradle
[ -x "$GRADLE" ] || { echo "Falta Gradle en el volumen carrete-gradle" >&2; exit 1; }
yes | /sdk/cmdline-tools/latest/bin/sdkmanager --licenses >/dev/null 2>&1 || true

if [ "${1:-}" = "test" ]; then
  "$GRADLE" --no-daemon -q :app:testReleaseUnitTest
  exit 0
fi

if [ -z "${CARRETE_KEYSTORE_PASSWORD}" ]; then
  if [ -f .keystore-password ]; then CARRETE_KEYSTORE_PASSWORD="$(cat .keystore-password)"; else
    CARRETE_KEYSTORE_PASSWORD="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
    printf '%s' "$CARRETE_KEYSTORE_PASSWORD" > .keystore-password
  fi
fi
if [ ! -f keystore.jks ]; then
  keytool -genkeypair -keystore keystore.jks -storepass "$CARRETE_KEYSTORE_PASSWORD" -keypass "$CARRETE_KEYSTORE_PASSWORD" \
    -alias carrete -keyalg RSA -keysize 3072 -validity 10000 -dname "CN=Carrete" 2>/dev/null
  echo "Creada la firma android/keystore.jks (contraseña en android/.keystore-password). Guárdalas con tus copias."
fi
export CARRETE_KEYSTORE=/app/keystore.jks CARRETE_KEYSTORE_PASSWORD

"$GRADLE" --no-daemon -q :app:testReleaseUnitTest :app:lintRelease :app:assembleRelease
mkdir -p build
cp app/build/outputs/apk/release/app-release.apk build/carrete.apk
printf '{"version_code": %s, "version_name": "%s"}\n' "$CARRETE_APK_VERSION_CODE" "$CARRETE_APK_VERSION_NAME" > build/carrete-apk.json
chown -R "${HOST_UID:-0}:${HOST_GID:-0}" build app/build .gradle keystore.jks .keystore-password 2>/dev/null || true
echo "Lista: android/build/carrete.apk ($(du -h build/carrete.apk | cut -f1))"
