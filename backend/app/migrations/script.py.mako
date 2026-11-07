"""${message}

Revisión: ${up_revision}
Anterior: ${down_revision | comma,n}
Fecha: ${create_date}

Recuerda el patrón expandir/contraer: la versión anterior de la aplicación tiene que seguir
funcionando con el esquema que deja esta migración.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
