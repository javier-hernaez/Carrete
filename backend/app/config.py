"""Configuración de la aplicación (estilo 12 factores).

Todo sale de variables de entorno con prefijo ``CARRETE_`` y se valida al arrancar: si algo falta o no
tiene sentido, la aplicación no arranca y explica qué variable corregir (ver ``describe_errors``).
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

GIB = 1024**3
GB = 1000**3

# 127.0.0.1 (el propio contenedor) y las redes privadas de Docker: por ahí llegan las peticiones que
# reenvía tailscaled desde el puerto publicado. A nadie más se le cree la cabecera X-Forwarded-For.
DEFAULT_TRUSTED_PROXIES = "127.0.0.1/32,::1/128,172.16.0.0/12"

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CARRETE_", extra="ignore", frozen=True)

    environment: Literal["production", "development", "test"] = "production"

    database_url: str = Field(description="URL de PostgreSQL, p. ej. postgresql+psycopg://u:c@db/carrete")
    secret_key: SecretStr = Field(description="Clave maestra; al menos 32 caracteres aleatorios")
    public_url: str = Field(description="Dirección pública, p. ej. https://equipo.tailnet.ts.net:10000")

    data_dir: Path = Path("/data")
    static_dir: Path | None = None

    trusted_proxies: Annotated[list[IPNetwork], NoDecode] = Field(
        default_factory=lambda: _parse_networks(DEFAULT_TRUSTED_PROXIES)
    )

    require_2fa: bool = True
    # Código del asistente inicial. Si no se define, se genera uno y se imprime en el registro.
    setup_token: SecretStr | None = None
    max_upload_bytes: int = Field(default=10 * GIB, gt=0)
    min_free_bytes: int = Field(default=20 * GB, ge=0)
    map_style_url: str | None = None

    premigration_dump: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "json"

    worker_poll_seconds: float = Field(default=2.0, gt=0)

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: str) -> str:
        scheme = urlsplit(value).scheme
        if not scheme.startswith("postgresql"):
            raise ValueError("debe ser una URL de PostgreSQL (postgresql+psycopg://usuario:clave@host/base)")
        return value

    @field_validator("secret_key")
    @classmethod
    def _check_secret_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("debe tener al menos 32 caracteres (genérala con: openssl rand -base64 48)")
        if len(set(secret)) < 10:
            raise ValueError("no parece aleatoria; genérala con: openssl rand -base64 48")
        return value

    @field_validator("public_url", "map_style_url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("debe ser una dirección http:// o https:// completa")
        return value.rstrip("/")

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def _split_networks(cls, value: object) -> object:
        if isinstance(value, str):
            return _parse_networks(value)
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> Settings:
        parts = urlsplit(self.public_url)
        if parts.path not in {"", "/"} or parts.query or parts.fragment:
            raise ValueError("CARRETE_PUBLIC_URL no puede llevar ruta, parámetros ni fragmento")
        if (
            self.environment == "production"
            and parts.scheme != "https"
            and parts.hostname not in _LOCAL_HOSTS
        ):
            raise ValueError("CARRETE_PUBLIC_URL debe usar https:// salvo que apunte a este mismo equipo")
        return self

    # --- Valores derivados -------------------------------------------------------------------------

    @property
    def public_origin(self) -> str:
        """Origen exacto (esquema, equipo y puerto) que se exige en la cabecera Origin."""
        parts = urlsplit(self.public_url)
        return f"{parts.scheme}://{parts.netloc}".lower()

    @property
    def cookie_name(self) -> str:
        # El prefijo __Host- obliga al navegador a exigir Secure, ruta / y ningún dominio.
        return "__Host-carrete" if self.is_https else "carrete"

    @property
    def is_https(self) -> bool:
        return urlsplit(self.public_url).scheme == "https"


def _parse_networks(raw: str) -> list[IPNetwork]:
    networks: list[IPNetwork] = []
    for raw_item in raw.split(","):
        item = raw_item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError as exc:
            raise ValueError(f"«{item}» no es una IP ni una red válida") from exc
    return networks


def describe_errors(exc: ValidationError) -> list[str]:
    """Convierte los errores de validación en líneas legibles que nombran la variable de entorno."""
    lines: list[str] = []
    for error in exc.errors():
        loc = [str(part) for part in error["loc"]]
        variable = f"CARRETE_{loc[0].upper()}" if loc else "configuración"
        message = error["msg"]
        if error["type"] == "missing":
            message = "falta; defínela en .env (ver deploy/.env.example)"
        message = message.removeprefix("Value error, ")
        lines.append(f"{variable}: {message}")
    return lines


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # los campos obligatorios vienen del entorno
