"""Agente de copias (contenedor ``backup``; ADR 0008).

Ve los datos y las copias en un mismo montaje (``/storage``) para poder usar enlaces duros. ``app`` y
``worker`` no tienen acceso a la carpeta de copias.

- Originales: espejo en ``copias/originals/`` en menos de 5 minutos. Enlace duro si está en el mismo
  sistema de ficheros (no ocupa espacio y sobrevive a un borrado en ``datos``); copia real verificada
  por SHA-256 si no (p. ej. un disco USB). Lo purgado se conserva 30 días más.
- Base de datos: ``pg_dump`` cada hora, verificado con ``pg_restore --list``; 48 horarias, 30 diarias y
  12 mensuales (las diarias y mensuales son enlaces duros a una horaria).
- Manifiestos: cada noche, un ``.jsonl`` por espacio para reconstruir la organización sin PostgreSQL.
- Configuración: ``docker-compose.yml`` y los NOMBRES de las variables de ``.env`` (nunca sus valores).
- Integridad: cada semana se recalcula el SHA-256 de cada original y de su copia.
"""

from __future__ import annotations

import contextlib
import errno
import json
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import FrameType
from typing import Any

from sqlalchemy import Engine, make_url, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Asset, BackupRun, Blob, IntegrityRun, Space, User
from app.services.notices import raise_notice
from app.services.status import get_state, put_state
from app.storage.files import Storage, sha256_file

log = logging.getLogger(__name__)

KEEP_HOURLY = 48
KEEP_DAILY = 30
KEEP_MONTHLY = 12
KEEP_MANIFESTS = 30
PURGED_RETENTION = timedelta(days=30)
HEALTH_FILE = Path("/tmp/backup-ok")  # noqa: S108  # nosec B108  # tmpfs del contenedor


@dataclass
class Schedule:
    database: timedelta = timedelta(hours=1)
    originals: timedelta = timedelta(minutes=2)
    manifests: timedelta = timedelta(hours=24)
    integrity: timedelta = timedelta(days=7)
    last: dict[str, float] = field(default_factory=dict)

    def due(self, name: str, every: timedelta) -> bool:
        now = time.monotonic()
        if now - self.last.get(name, -1e12) >= every.total_seconds():
            self.last[name] = now
            return True
        return False


class BackupAgent:
    def __init__(
        self,
        engine: Engine,
        sessions: sessionmaker[Session],
        *,
        source: Path,
        target: Path,
        config_dir: Path | None = None,
    ) -> None:
        self.engine = engine
        self.sessions = sessions
        self.data = Storage(source)
        self.target = target
        self.config_dir = config_dir
        self.stopping = threading.Event()

    # --- Rutas ---------------------------------------------------------------------------------------

    def backup_original_path(self, sha256: str, ext: str) -> Path:
        return self.target / "originals" / sha256[:2] / sha256[2:4] / f"{sha256}.{ext}"

    def same_filesystem(self) -> bool:
        self.target.mkdir(parents=True, exist_ok=True)
        self.data.root.mkdir(parents=True, exist_ok=True)
        return self.data.root.stat().st_dev == self.target.stat().st_dev

    def _record(self, db: Session, kind: str, ok: bool, started: datetime, detail: dict[str, Any]) -> None:
        db.add(BackupRun(kind=kind, ok=ok, started_at=started, finished_at=datetime.now(UTC), detail=detail))
        db.commit()

    # --- Originales ----------------------------------------------------------------------------------

    def mirror_originals(self, *, batch: int = 2000) -> dict[str, int]:
        started = datetime.now(UTC)
        counts = {"linked": 0, "copied": 0, "already": 0, "missing": 0, "released": 0}
        with self.sessions() as db:
            while True:
                blobs = list(
                    db.scalars(
                        select(Blob)
                        .where(Blob.backed_up_at.is_(None), Blob.purged_at.is_(None))
                        .order_by(Blob.created_at)
                        .limit(batch)
                    )
                )
                if not blobs:
                    break
                for blob in blobs:
                    counts[self._mirror_one(blob)] += 1
                db.commit()
                if all(b.backed_up_at is None for b in blobs):
                    break  # solo quedan originales ausentes: los señala la verificación de integridad
            counts["released"] = self._release_purged(db)
            ok = counts["missing"] == 0
            self._record(db, "originals", ok, started, counts)
            put_state(db, "backup", {**get_state(db, "backup"), "same_disk": self.same_filesystem()})
            db.commit()
        return counts

    def _mirror_one(self, blob: Blob) -> str:
        src = self.data.original_path(blob.sha256, blob.ext)
        dst = self.backup_original_path(blob.sha256, blob.ext)
        if dst.exists() and dst.stat().st_size == blob.size_bytes:
            blob.backed_up_at = datetime.now(UTC)
            return "already"
        if not src.exists():
            log.error("Original ausente al copiar", extra={"sha256": blob.sha256})
            return "missing"
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dst)
            result = "linked"
        except OSError as exc:
            if exc.errno not in (errno.EXDEV, errno.EPERM, errno.EMLINK, errno.EEXIST):
                raise
            tmp = dst.with_suffix(dst.suffix + ".partial")
            shutil.copyfile(src, tmp)
            if sha256_file(tmp) != blob.sha256:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"La copia de {blob.sha256} no coincide con el original") from exc
            tmp.chmod(0o444)
            tmp.replace(dst)
            result = "copied"
        blob.backed_up_at = datetime.now(UTC)
        return result

    def _release_purged(self, db: Session) -> int:
        """Borra de las copias los originales purgados hace más de 30 días (60 días en total)."""
        limit = datetime.now(UTC) - PURGED_RETENTION
        released = 0
        for blob in db.scalars(select(Blob).where(Blob.purged_at.is_not(None), Blob.purged_at <= limit)):
            path = self.backup_original_path(blob.sha256, blob.ext)
            if path.exists():
                path.unlink()
                released += 1
        return released

    # --- Base de datos -------------------------------------------------------------------------------

    def dump_database(self) -> Path | None:
        started = datetime.now(UTC)
        root = self.target / "db"
        hourly, daily, monthly = root / "horarias", root / "diarias", root / "mensuales"
        for folder in (hourly, daily, monthly):
            folder.mkdir(parents=True, exist_ok=True)
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        path = hourly / f"carrete-{stamp}.dump"
        partial = path.with_suffix(".dump.partial")
        url = make_url(self.engine.url)
        env = {**os.environ, "PGCONNECT_TIMEOUT": "10"}
        if url.password:
            env["PGPASSWORD"] = str(url.password)
        conninfo = url.set(drivername="postgresql", password=None).render_as_string(hide_password=False)
        pg_dump, pg_restore = shutil.which("pg_dump"), shutil.which("pg_restore")
        try:
            if pg_dump is None or pg_restore is None:
                raise RuntimeError("Faltan pg_dump/pg_restore")
            subprocess.run(  # noqa: S603  # nosec B603
                [pg_dump, "--format=custom", "--compress=6", f"--file={partial}", f"--dbname={conninfo}"],
                env=env,
                check=True,
                capture_output=True,
                timeout=3600,
            )
            subprocess.run([pg_restore, "--list", str(partial)], check=True, capture_output=True, timeout=600)  # noqa: S603
            partial.rename(path)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
            partial.unlink(missing_ok=True)
            message = (
                exc.stderr.decode(errors="replace")[-500:]
                if isinstance(exc, subprocess.CalledProcessError)
                else str(exc)
            )
            with self.sessions() as db:
                self._record(db, "database", False, started, {"error": message})
            log.error("Volcado fallido", extra={"error": message})
            return None
        day, month = started.strftime("%Y%m%d"), started.strftime("%Y%m")
        if not list(daily.glob(f"carrete-{day}T*.dump")):
            os.link(path, daily / path.name)
        if not list(monthly.glob(f"carrete-{month}*.dump")):
            os.link(path, monthly / path.name)
        for folder, keep in ((hourly, KEEP_HOURLY), (daily, KEEP_DAILY), (monthly, KEEP_MONTHLY)):
            for old in sorted(folder.glob("carrete-*.dump"))[:-keep]:
                old.unlink(missing_ok=True)
        with self.sessions() as db:
            self._record(db, "database", True, started, {"file": path.name, "bytes": path.stat().st_size})
        with contextlib.suppress(OSError):
            HEALTH_FILE.touch()
        return path

    # --- Manifiestos y configuración -----------------------------------------------------------------

    def write_manifests(self) -> int:
        started = datetime.now(UTC)
        from app.services import albums as album_service

        stamp = started.strftime("%Y-%m-%d")
        written = 0
        with self.sessions() as db:
            names = dict(db.execute(select(User.id, User.display_name)).tuples().all())
            for space in db.scalars(select(Space)):
                folder = self.target / "manifests" / str(space.id)
                folder.mkdir(parents=True, exist_ok=True)
                tmp = folder / f"{stamp}.jsonl.partial"
                album_map = album_service.album_names_by_asset(db, space.id)
                with tmp.open("w", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "space": space.name,
                                "space_id": str(space.id),
                                "generated_at": started.isoformat(),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    rows = db.execute(
                        select(Asset, Blob)
                        .join(Blob, Blob.id == Asset.blob_id)
                        .where(Asset.space_id == space.id)
                        .order_by(Asset.taken_at_local)
                    )
                    for asset, blob in rows.tuples():
                        f.write(
                            json.dumps(manifest_entry(asset, blob, names, album_map), ensure_ascii=False)
                            + "\n"
                        )
                        written += 1
                tmp.replace(folder / f"{stamp}.jsonl")
                for old in sorted(folder.glob("*.jsonl"))[:-KEEP_MANIFESTS]:
                    old.unlink(missing_ok=True)
            self._record(db, "manifests", True, started, {"entries": written})
        self.copy_config()
        return written

    def copy_config(self) -> None:
        if self.config_dir is None or not self.config_dir.is_dir():
            return
        out = self.target / "config"
        out.mkdir(parents=True, exist_ok=True)
        compose = self.config_dir / "docker-compose.yml"
        if compose.is_file():
            shutil.copyfile(compose, out / "docker-compose.yml")
        env = self.config_dir / ".env"
        if env.is_file():
            # Solo los nombres: los valores secretos se guardan en el gestor de contraseñas.
            names = [
                line.split("=", 1)[0].strip()
                for line in env.read_text().splitlines()
                if "=" in line and not line.lstrip().startswith("#")
            ]
            (out / "env-variables.txt").write_text("\n".join(names) + "\n")

    # --- Integridad ----------------------------------------------------------------------------------

    def verify_integrity(self) -> IntegrityRun:
        started = datetime.now(UTC)
        problems: list[dict[str, Any]] = []
        checked = 0
        with self.sessions() as db:
            known: set[str] = set()
            for blob in db.scalars(select(Blob).where(Blob.purged_at.is_(None))):
                checked += 1
                original = self.data.original_path(blob.sha256, blob.ext)
                known.add(original.name)
                copy = self.backup_original_path(blob.sha256, blob.ext)
                original_ok = original.exists() and sha256_file(original) == blob.sha256
                if not original.exists():
                    problems.append({"type": "missing_original", "sha256": blob.sha256})
                elif not original_ok:
                    problems.append({"type": "corrupt_original", "sha256": blob.sha256})
                if not copy.exists():
                    if blob.backed_up_at is not None:
                        problems.append({"type": "missing_backup", "sha256": blob.sha256})
                elif (
                    not (original.exists() and original.samefile(copy) and original_ok)
                    and sha256_file(copy) != blob.sha256
                ):
                    problems.append({"type": "corrupt_backup", "sha256": blob.sha256})
                if original_ok:
                    blob.verified_at = datetime.now(UTC)
            if self.data.originals.exists():
                for path in self.data.originals.rglob("*.*"):
                    if path.is_file() and path.name not in known and not path.name.endswith(".partial"):
                        problems.append(
                            {"type": "orphan_file", "file": str(path.relative_to(self.data.root))}
                        )
            run = IntegrityRun(
                started_at=started,
                finished_at=datetime.now(UTC),
                ok=not problems,
                checked=checked,
                problems=problems,
            )
            db.add(run)
            if problems:
                kinds = sorted({p["type"] for p in problems})
                raise_notice(
                    db,
                    "integrity",
                    f"La verificación de integridad ha encontrado {len(problems)} problemas "
                    f"({', '.join(kinds)}).",
                    severity="critical",
                    dedup_key="integrity",
                    detail={"count": len(problems)},
                )
            db.commit()
            db.refresh(run)
            return run

    # --- Bucle ---------------------------------------------------------------------------------------

    def run_once(self) -> None:
        self.dump_database()
        self.mirror_originals()
        self.write_manifests()

    def run_forever(self, schedule: Schedule | None = None) -> None:
        schedule = schedule or Schedule()
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        log.info("Copias en marcha", extra={"target": str(self.target), "same_disk": self.same_filesystem()})
        while not self.stopping.is_set():
            for name, every, action in (
                ("originals", schedule.originals, self.mirror_originals),
                ("database", schedule.database, self.dump_database),
                ("manifests", schedule.manifests, self.write_manifests),
                ("integrity", schedule.integrity, self.verify_integrity),
            ):
                if self.stopping.is_set():
                    break
                if schedule.due(name, every):
                    try:
                        action()
                    except Exception:
                        log.exception("Fallo en la copia", extra={"step": name})
            self.stopping.wait(30)

    def _stop(self, _signum: int, _frame: FrameType | None) -> None:
        self.stopping.set()


def manifest_entry(
    asset: Asset, blob: Blob, names: dict[Any, str], albums: dict[Any, list[str]]
) -> dict[str, Any]:
    return {
        "id": str(asset.id),
        "sha256": blob.sha256,
        "file": f"originals/{blob.sha256[:2]}/{blob.sha256[2:4]}/{blob.sha256}.{blob.ext}",
        "original_filename": asset.original_filename,
        "taken_at": asset.taken_at_local.isoformat(),
        "taken_at_offset": asset.taken_at_offset,
        "kind": asset.kind,
        "review_state": asset.review_state,
        "favorite": asset.is_favorite,
        "description": asset.description,
        "albums": albums.get(asset.id, []),
        "lat": asset.lat,
        "lon": asset.lon,
        "uploaded_by": names.get(asset.uploaded_by),
        "trashed": asset.trashed_at is not None,
    }


# --- Restauración ------------------------------------------------------------------------------------


def restore(
    engine: Engine, sessions: sessionmaker[Session], *, dump: Path, source: Path, target: Path
) -> dict[str, int]:
    """Restaura la base de datos de un volcado y los originales que falten desde las copias.

    Después hay que regenerar los derivados: se encolan las tareas de procesado que hagan falta.
    """
    url = make_url(engine.url)
    env = {**os.environ}
    if url.password:
        env["PGPASSWORD"] = str(url.password)
    conninfo = url.set(drivername="postgresql", password=None).render_as_string(hide_password=False)
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        raise RuntimeError("Falta pg_restore")
    engine.dispose()
    subprocess.run(  # noqa: S603  # nosec B603
        [
            pg_restore,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--single-transaction",
            f"--dbname={conninfo}",
            str(dump),
        ],
        env=env,
        check=True,
        capture_output=True,
        timeout=7200,
    )
    data = Storage(source)
    agent = BackupAgent(engine, sessions, source=source, target=target)
    counts = {"restored_originals": 0, "missing": 0, "reprocess": 0}
    from app.jobs import queue

    with sessions() as db:
        for blob in db.scalars(select(Blob).where(Blob.purged_at.is_(None))):
            original = data.original_path(blob.sha256, blob.ext)
            if original.exists():
                continue
            copy = agent.backup_original_path(blob.sha256, blob.ext)
            if not copy.exists() or sha256_file(copy) != blob.sha256:
                counts["missing"] += 1
                continue
            original.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(copy, original)
            except OSError:
                tmp = original.with_suffix(original.suffix + ".partial")
                shutil.copyfile(copy, tmp)
                tmp.chmod(0o444)
                tmp.replace(original)
            counts["restored_originals"] += 1
        for asset, blob in db.execute(select(Asset, Blob).join(Blob, Blob.id == Asset.blob_id)).tuples():
            if not (data.derivative_dir(blob.sha256) / "thumb.webp").exists():
                queue.enqueue(db, "process_asset", {"asset_id": str(asset.id)}, priority=150)
                counts["reprocess"] += 1
        db.commit()
    return counts
