# 0008 — Copias de originales con enlaces duros: carpeta raíz única y agente en Python

- **Estado**: aceptada
- **Fecha**: 2026-11-10

## Contexto

Hace falta un espejo de originales en la carpeta de copias, con enlaces duros si está en el
mismo sistema de ficheros, y que `app` y `worker` no tengan acceso a esa carpeta. Además está el
problema de `fs.protected_hardlinks=1`.

Al implementarlo apareció otra restricción: Linux no permite crear un enlace duro entre **dos montajes
distintos**, aunque estén en el mismo disco (`EXDEV`). Montar `datos` y `copias` por separado en el
contenedor de copias haría imposible el enlace.

## Decisión

- Una carpeta raíz `CARRETE_ROOT` (por defecto `/home/javier/carrete`) con `datos/` y `copias/`.
- `app` y `worker` montan solo `CARRETE_ROOT/datos` en `/data`: no ven las copias.
- El contenedor `backup` monta `CARRETE_ROOT` entero en `/storage` y puede enlazar.
- `protected_hardlinks`: todos los contenedores corren con el mismo UID que es dueño de los originales
  (`CARRETE_UID`), así que el núcleo permite el enlace sin capacidades extra (`cap_drop: [ALL]`).
- El agente está en Python (`app/backup/agent.py`, orden `carrete backup-agent`) y usa la misma imagen:
  sustituye al script de shell inicial. Así se prueba igual que el resto (`tests/test_conservation.py`).
- Si el enlace no es posible (otro disco montado dentro de `copias/`, un USB), se hace una copia real,
  verificada por SHA-256 y en solo lectura. Se detecta solo, fichero a fichero.

## Consecuencias

- El contenedor `backup` puede escribir en `datos/`. Es aceptable: no procesa ficheros de nadie (no está
  expuesto a contenido malicioso), no tiene red exterior y su código no borra originales (la prueba
  `test_only_purge_deletes_originals` lo vigila).
- Un enlace duro protege de borrados y de errores de la aplicación, **no** de la rotura del disco.
  El panel de administración lo recuerda siempre.
- Para una copia externa futura basta con montar el otro disco dentro de `copias/` o apuntar
  `CARRETE_ROOT/copias` a él con un enlace simbólico de directorio: el agente copiará en vez de enlazar.
