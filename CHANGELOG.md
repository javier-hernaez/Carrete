# Cambios

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versiones semánticas.

## [Sin publicar]

### Añadido — Etiquetas y revisar en bloque

- Etiquetas en la web: «Etiquetas…» en el visor y en la selección (con «Personas», «Paisajes» y
  «Humor» como sugerencias para empezar), fichas para ponerlas y quitarlas en Revisar sin pasar a la
  siguiente, y página «Más → Etiquetas» para renombrarlas o eliminarlas (sin borrar fotos).
- Filtro por etiquetas con fichas en Fotos y dentro de cada álbum (solo las etiquetas que hay en él,
  con su recuento allí: `GET /tags?album_id=`). Varias a la vez: fotos que las tienen todas.
- Revisar en bloque: cuadrícula de lo pendiente con casillas y «Seleccionar el día» siempre a la vista,
  y las acciones de la selección para todas a la vez. Es el modo por defecto; «Una a una» sigue
  disponible y se recuerda el elegido.
- Seleccionar con el dedo: mantener pulsada una foto la selecciona y, sin soltar, deslizar marca todas
  las que hay entre medias (o las desmarca). Cerca del borde, la página se desplaza sola.
- «Un recuerdo»: una foto al azar de todo el espacio encima de la línea temporal, con «Otra» y
  «Ocultar» (`GET /assets/random`).
- Exportar «Todos los álbumes» y, en cualquier exportación, solo lo que tenga alguna de las etiquetas
  elegidas (`all_albums` y `tag_ids`).

### Cambiado — Selección y álbumes

- Ya no se pueden arrastrar fotos (sobre todo en el móvil, mantener pulsado las «cogía» para moverlas):
  la barra lateral solo enlaza los álbumes y se añade con «Álbum…».
- En Fotos, «Seleccionar el día» aparece solo con la selección en marcha.
- «Eliminar el álbum» pasa al final de la página, dentro de «Más opciones del álbum», con un botón
  rojo y confirmación con «Cancelar».

### Corregido — Móvil

- App Android: se cerraba al pulsar «Elegir del móvil» en móviles cuyo selector de fotos admite menos de
  200 elementos de una vez (normalmente 100). Ahora pide el máximo de cada móvil y la web lo indica.
- App Android: se cerraba al recibir las fotos del selector en Android 15 (no deja leer el original con
  ubicación de esas fotos). Ahora sube la foto tal cual y un fichero ilegible ya no tumba el lote.
- App Android: «Elegir una carpeta» con el selector de carpetas de Android, que sube la carpeta y sus
  subcarpetas sin límite y sin copiar las fotos al móvil.
- App Android: los botones de la web para elegir ficheros (también un .zip) no hacían nada dentro de la
  app.
- App Android: el resumen final de la subida a veces no aparecía (Android descartaba notificaciones por
  exceso de actualizaciones de progreso).
- Web en el navegador del móvil: ya no ofrece «Elegir una carpeta», que ahí no funciona, y remite a la app.
- Varias pantallas (Administración, Repetidas, Exportar, Espacio, Álbumes) se salían por la derecha en
  el móvil: la columna principal crecía con su contenido más ancho. Ahora nada desborda entre 320 y
  412 px de ancho.
- Revisar: en pantallas estrechas, «No vale» y «Vale» van en su propia fila y no quedan cortados.
- Barra de selección: «Todas» y «Cancelar» siempre a la vista; las acciones se deslizan si no caben.
  Ya no tapa la última fila de fotos.
- Auditoría en el móvil como fichas; panel de información del visor opaco; campos de formulario que
  ya no se salen de los diálogos; álbumes en dos columnas desde 320 px.
- Prueba de aislamiento que recorre todas las rutas con un usuario ajeno al espacio y con ids ajenos
  colados en peticiones sobre un espacio propio.

### Cambiado

- Hay un solo administrador (el responsable del servidor; la base de datos no admite un segundo)
  y tiene acceso de propietario a todos los espacios, aunque no sea miembro (los ve en el selector, y
  en la auditoría con todo el detalle). No se le añade como miembro.
- Explicación de lo que puede hacer cada rol: al elegir el rol de una invitación, en «¿Qué puede hacer
  cada rol?» de Miembros y en la pantalla de aceptar la invitación (que también avisa del acceso del
  administrador).

### Añadido — Mapa y lugares

- Nombre del lugar calculado en el servidor con GeoNames, sin servicios externos; búsqueda por lugar.
- Mapa del espacio con MapLibre, agrupado por zonas; al tocar una zona se abre la cuadrícula de ese
  lugar. OpenFreeMap por defecto (`CARRETE_MAP_STYLE_URL`, vacía para ocultarlo).
- «Lugar…» en la selección para poner o quitar la ubicación a mano, con deshacer.
- Sugerencias de álbum a partir de la bandeja de entrada (saltos de fecha y de lugar).
- Llaves de acceso (WebAuthn): entrar con huella, cara o PIN; alta y baja en Ajustes.
- Índice parcial para la línea temporal y prueba de rendimiento con 50 000 elementos.
- ADR 0010.

### Añadido — Funciones principales

- Acceso: asistente inicial, 2FA TOTP con códigos de recuperación, sesiones, invitaciones, roles por
  espacio, límites de intentos, auditoría y administración.
- Subir y ver: subida reanudable (tus), originales inmutables, miniaturas y vídeo, fechas de WhatsApp,
  línea temporal virtualizada, visor y filtros.
- Copias: agente con enlaces duros, volcados y manifiestos, integridad, restauración,
  papelera con purga, estado y avisos.
- Ordenar: revisar con teclado y gestos, selección múltiple, álbumes, favoritas, fechas, repetidas y
  actividad.
- Exportar e importar: ZIP por volúmenes con manifiesto, importación de ZIP y carpetas (WhatsApp, Takeout),
  biblioteca en disco, PWA y documentación de seguridad.
- App Android con «Compartir», cola en segundo plano y APK firmado.

### Añadido — Base del proyecto

- Estructura del repositorio, `Makefile` con todas las órdenes de desarrollo en Docker, `pre-commit`.
- Backend: configuración `CARRETE_*` validada al arrancar, PostgreSQL 17 + Alembic con migraciones al
  arrancar (bloqueo consultivo y volcado previo), cola de tareas sobre PostgreSQL y `worker`,
  `/healthz` y `/readyz`, errores `problem+json`, cabeceras de seguridad, registros JSON, orden
  `carrete`.
- Primera migración: cola de tareas y registro de auditoría de solo inserción.
- Web: armazón (barra inferior en móvil, lateral en escritorio), sistema de diseño con tema claro y
  oscuro, estados vacíos, cliente de la API con tipos generados de OpenAPI.
- Despliegue: `Dockerfile` multi-etapa, `docker-compose.yml` endurecido con redes separadas, copias
  horarias de la base de datos.
- CI: lint, tipos, pruebas con cobertura mínima, auditoría de dependencias, gitleaks, Semgrep, Trivy,
  SBOM y publicación en GHCR solo si todo pasa.
- Documentación: arquitectura, diseño, operación, seguridad y ADR 0001–0006.
