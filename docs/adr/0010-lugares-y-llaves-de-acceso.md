# 0010 — Lugares sin conexión, mapa por zonas y llaves de acceso

- **Estado**: aceptada
- **Fecha**: 2026-11-14

## Contexto

Faltan el mapa, el nombre del lugar sin servicios externos, la ubicación a mano,
las sugerencias de álbum y las llaves de acceso. Las coordenadas de las fotos son datos
personales: no deben salir del mini PC.

## Decisión

- **Lugares**: `backend/app/data/places.tsv.gz` (≈ 600 KB, 34 000 filas) sale de `cities15000.txt` y
  `admin1CodesASCII.txt` de GeoNames (CC BY 4.0, atribución en «Más»). En memoria, una cuadrícula de 1°;
  se elige la ciudad más cercana hasta 150 km. Se calcula al procesar la foto, al importar con datos de
  Takeout y al poner la ubicación a mano. La región viene en inglés («Andalusia»): se guarda para la
  búsqueda pero la web solo muestra ciudad y país (país con `Intl.DisplayNames` en español).
- **Mapa**: el servidor agrupa por celdas según el zoom (`GET /spaces/{id}/map`) y devuelve recuento,
  centro, límites y portada de cada zona; nunca la lista de coordenadas. MapLibre se carga solo al abrir
  el mapa (trozo aparte de ≈ 290 KB comprimido). Al tocar una zona se abre la cuadrícula con el filtro
  `zona=sur,oeste,norte,este`, que usan igual el listado y la línea temporal.
- **Proveedor de teselas**: `CARRETE_MAP_STYLE_URL`. En `docker-compose.yml`, sin definir vale
  OpenFreeMap (público y sin clave); definida y vacía oculta el mapa. La CSP solo
  admite el origen del estilo (estilo, teselas, fuentes e iconos de OpenFreeMap salen del mismo).
- **Sugerencias de álbum**: fotos de la bandeja de entrada (pendientes de revisar) que no están en
  ningún álbum, cortadas donde hay más de 18 h sin fotos o un salto de más de 80 km; se proponen los
  grupos de al menos 8, con el lugar más repetido. «Ahora no» se recuerda en el navegador
  (preferencia por persona, sin tabla nueva).
- **Llaves de acceso** con `webauthn` (py_webauthn): `rp_id` = nombre de la dirección pública,
  `origin` = `CARRETE_PUBLIC_URL`, verificación de usuario obligatoria (equivale a dos factores), llaves
  detectables (no hace falta escribir el usuario). Los retos se guardan en la base de datos con caducidad
  de 5 min y un solo uso. Quitar una llave pide reautenticación.

## Consecuencias

- Una llave creada en `http://127.0.0.1:8010` no vale en la dirección del Funnel (otro `rp_id`): hay que
  crearlas ya desde la dirección pública.
- Cambiar de proveedor de teselas con otro dominio para teselas o fuentes exige ampliar la CSP.
- Índice parcial `ix_assets_visible_timeline`: la primera página de la línea temporal con 50 000
  elementos tarda ≈ 23 ms (`tests/perf`, con `CARRETE_PERF=1`).
