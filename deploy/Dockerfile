# syntax=docker/dockerfile:1.7
# Imagen única para «app» y «worker». Se construye desde la raíz del repositorio:
#   docker build -f deploy/Dockerfile -t carrete .
# Funciona con BuildKit y con el constructor clásico (que construye en orden todas las etapas hasta la
# pedida: por eso la etapa «dev» va antes que la web).

# --- 1) Base de Python con las herramientas del sistema ----------------------------------------------
FROM python:3.13-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH
# postgresql-client: volcado de la base de datos antes de cada migración.
# libvips + libheif: imágenes (también HEIC y AVIF); ffmpeg: vídeo; exiftool: metadatos.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends postgresql-client-17 \
      libvips42t64 libheif1 libheif-plugin-libde265 libheif-plugin-dav1d libheif-plugin-aomdec \
      ffmpeg libimage-exiftool-perl \
 && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
WORKDIR /app

# --- 2) Dependencias de producción, verificadas por hash --------------------------------------------
FROM base AS deps
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes --no-deps -r /tmp/requirements.txt

# --- 3) Entorno de pruebas (CI y desarrollo); no se publica ------------------------------------------
FROM deps AS dev
COPY backend/requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --require-hashes --no-deps -r /tmp/requirements-dev.txt
WORKDIR /src/backend
CMD ["python", "-m", "pytest"]

# --- 4) Web: compila la interfaz (React + Vite) a ficheros estáticos ---------------------------------
FROM node:22-alpine AS web
WORKDIR /web
# Reintentos generosos: la red del mini PC a veces corta descargas largas.
ENV npm_config_fetch_retries=6 npm_config_fetch_retry_mintimeout=20000 npm_config_fetch_retry_maxtimeout=120000
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- 5) Imagen final ---------------------------------------------------------------------------------
FROM base AS runtime
ARG CARRETE_VERSION=dev
ENV CARRETE_VERSION=${CARRETE_VERSION} \
    CARRETE_STATIC_DIR=/app/static \
    CARRETE_DATA_DIR=/data
COPY --from=deps /opt/venv /opt/venv
COPY backend/app ./app
COPY --from=web /web/dist ./static
COPY deploy/carrete.sh /usr/local/bin/carrete
# El usuario real lo fija docker-compose.yml (el dueño de las carpetas de datos en el equipo); este es
# solo el valor por defecto, sin privilegios.
RUN useradd --system --uid 10001 --no-create-home carrete \
 && mkdir -p /data && chown carrete /data
USER carrete
EXPOSE 8000
LABEL org.opencontainers.image.title="Carrete" \
      org.opencontainers.image.description="Reunir, ordenar y conservar las fotos y vídeos de un grupo" \
      org.opencontainers.image.source="https://github.com/javier-hernaez/carrete"
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
STOPSIGNAL SIGTERM
CMD ["carrete", "serve"]
