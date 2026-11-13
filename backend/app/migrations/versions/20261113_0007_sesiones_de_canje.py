"""sesiones de canje

Revisión: 0007
Anterior: 0006
Fecha: 2026-11-13 16:48:59.731062

Recuerda el patrón expandir/contraer: la versión anterior de la aplicación tiene que seguir
funcionando con el esquema que deja esta migración.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Sesiones «exchange»: código de un solo uso con el que la WebView de la app Android obtiene su sesión.
    op.drop_constraint(op.f("ck_sessions_kind_valid"), "sessions", type_="check")
    op.create_check_constraint(
        op.f("ck_sessions_kind_valid"), "sessions", "kind IN ('web', 'device', 'exchange')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM sessions WHERE kind = 'exchange'")
    op.drop_constraint(op.f("ck_sessions_kind_valid"), "sessions", type_="check")
    op.create_check_constraint(op.f("ck_sessions_kind_valid"), "sessions", "kind IN ('web', 'device')")
