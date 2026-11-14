/* Service worker de Carrete: hace la web instalable (PWA) y arranca rápido.
 * - Guarda solo el armazón: index.html y los ficheros con hash de /assets/.
 * - NUNCA guarda nada de /api/ (fotos, miniaturas, datos): son privados y necesitan sesión.
 */
const CACHE = "carrete-armazon-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(["/", "/manifest.webmanifest", "/favicon.svg"])),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/healthz" || url.pathname === "/readyz") return;

  if (url.pathname.startsWith("/assets/")) {
    // Ficheros con hash: inmutables. Primero la caché.
    event.respondWith(
      caches.match(event.request).then(
        (hit) =>
          hit ||
          fetch(event.request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              void caches.open(CACHE).then((cache) => cache.put(event.request, copy));
            }
            return response;
          }),
      ),
    );
    return;
  }

  if (event.request.mode === "navigate") {
    // Páginas: primero la red (siempre la versión nueva); sin red, el armazón guardado.
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          void caches.open(CACHE).then((cache) => cache.put("/", copy));
          return response;
        })
        .catch(() => caches.match("/").then((hit) => hit || Response.error())),
    );
  }
});
