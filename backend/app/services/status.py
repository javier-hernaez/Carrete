"""Estado de la instancia y avisos automáticos."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import AppState, Asset, BackupRun, Blob, IntegrityRun, Space
from app.services.notices import raise_notice
from app.storage.files import Storage

DISK_WARN = 0.80
DISK_CRITICAL = 0.90
BACKUP_MAX_AGE = timedelta(hours=2)
ORIGINAL_BACKUP_DELAY = timedelta(minutes=15)


def put_state(db: Session, key: str, value: dict[str, Any]) -> None:
    db.execute(
        insert(AppState)
        .values(key=key, value=value)
        .on_conflict_do_update(index_elements=["key"], set_={"value": value, "updated_at": datetime.now(UTC)})
    )


def get_state(db: Session, key: str) -> dict[str, Any]:
    state = db.get(AppState, key)
    return dict(state.value) if state else {}


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def storage_report(db: Session, storage: Storage) -> dict[str, Any]:
    disk = shutil.disk_usage(storage.root)
    per_space = db.execute(
        select(Space.id, Space.name, func.count(Asset.id), func.coalesce(func.sum(Blob.size_bytes), 0))
        .join(Asset, Asset.space_id == Space.id, isouter=True)
        .join(Blob, Blob.id == Asset.blob_id, isouter=True)
        .group_by(Space.id, Space.name)
        .order_by(Space.name)
    ).all()
    originals = int(
        db.scalar(select(func.coalesce(func.sum(Blob.size_bytes), 0)).where(Blob.purged_at.is_(None))) or 0
    )
    report = {
        "computed_at": datetime.now(UTC).isoformat(),
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_free": disk.free,
        "originals": originals,
        "derivatives": _dir_size(storage.derivatives),
        "exports": _dir_size(storage.exports),
        "uploads": _dir_size(storage.uploads),
        # Los espacios se cuentan por separado, aunque compartan originales (por eso no suman exacto).
        "spaces": [{"id": str(i), "name": n, "count": int(c), "bytes": int(b)} for i, n, c, b in per_space],
    }
    put_state(db, "storage", report)
    return report


def health_checks(db: Session, storage: Storage) -> list[str]:
    """Avisos al administrador. Devuelve los tipos de aviso levantados (para las pruebas)."""
    raised: list[str] = []
    disk = shutil.disk_usage(storage.root)
    used = disk.used / disk.total if disk.total else 0
    if used >= DISK_CRITICAL:
        raise_notice(
            db,
            "disk_critical",
            f"El disco está al {used:.0%}. Las subidas se pararán al llegar a la reserva.",
            severity="critical",
            dedup_key="disk_critical",
        )
        raised.append("disk_critical")
    elif used >= DISK_WARN:
        raise_notice(
            db, "disk_warning", f"El disco está al {used:.0%}.", severity="warning", dedup_key="disk_warning"
        )
        raised.append("disk_warning")

    last_db = db.scalar(
        select(func.max(BackupRun.finished_at)).where(BackupRun.kind == "database", BackupRun.ok.is_(True))
    )
    if last_db is None or datetime.now(UTC) - last_db > BACKUP_MAX_AGE:
        raise_notice(
            db,
            "backup_late",
            "La copia de la base de datos está atrasada. Revisa el contenedor «backup».",
            severity="critical",
            dedup_key="backup_late",
        )
        raised.append("backup_late")

    pending = db.scalar(
        select(func.count()).where(
            Blob.backed_up_at.is_(None),
            Blob.purged_at.is_(None),
            Blob.created_at < datetime.now(UTC) - ORIGINAL_BACKUP_DELAY,
        )
    )
    if pending:
        raise_notice(
            db,
            "originals_not_backed_up",
            f"{pending} originales llevan más de 15 minutos sin copia.",
            severity="critical",
            dedup_key="originals_not_backed_up",
        )
        raised.append("originals_not_backed_up")
    return raised


def status(db: Session, storage: Storage) -> dict[str, Any]:
    from app.jobs.queue import counts_by_state

    def last(kind: str) -> dict[str, Any] | None:
        run = db.scalar(
            select(BackupRun).where(BackupRun.kind == kind).order_by(BackupRun.started_at.desc()).limit(1)
        )
        if run is None:
            return None
        return {
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "ok": run.ok,
            "detail": run.detail,
        }

    integrity = db.scalar(select(IntegrityRun).order_by(IntegrityRun.started_at.desc()).limit(1))
    disk = shutil.disk_usage(storage.root)
    pending = (
        db.scalar(select(func.count()).where(Blob.backed_up_at.is_(None), Blob.purged_at.is_(None))) or 0
    )
    from app.db.models import Job

    failed_jobs = db.execute(
        select(Job.kind, Job.last_error, Job.finished_at)
        .where(Job.state == "failed")
        .order_by(Job.finished_at.desc())
        .limit(20)
    ).all()
    return {
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
        "storage": get_state(db, "storage"),
        "backup": {
            "database": last("database"),
            "originals": last("originals"),
            "manifests": last("manifests"),
            "pending_originals": int(pending),
            "agent": get_state(db, "backup"),
        },
        "integrity": None
        if integrity is None
        else {
            "started_at": integrity.started_at,
            "finished_at": integrity.finished_at,
            "ok": integrity.ok,
            "checked": integrity.checked,
            "problems": integrity.problems[:50],
        },
        "queue": counts_by_state(db),
        "failed_jobs": [{"kind": k, "error": e, "at": t} for k, e, t in failed_jobs],
    }
