"""un solo administrador

Revisión: 0009
Anterior: 0008
Fecha: 2026-11-15

Garantiza en la base de datos que solo puede haber un administrador. Compatible con la versión
anterior: el asistente inicial ya creaba uno solo.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_users_single_admin",
        "users",
        ["is_admin"],
        unique=True,
        postgresql_where=sa.text("is_admin"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_single_admin", table_name="users", postgresql_where=sa.text("is_admin"))
