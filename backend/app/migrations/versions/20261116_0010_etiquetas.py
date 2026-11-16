"""etiquetas

Revisión: 0010
Anterior: 0009
Fecha: 2026-11-16

Etiquetas por espacio («Personas», «Paisajes», «Humor»…) y su relación con los elementos. Solo añade
tablas nuevas (expandir): la versión anterior sigue funcionando sobre este esquema.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("space_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_tags_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["space_id"], ["spaces.id"], name=op.f("fk_tags_space_id_spaces"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("space_id", "key", name=op.f("uq_tags_space_id_key")),
    )
    op.create_table(
        "asset_tags",
        sa.Column("tag_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("added_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["added_by"], ["users.id"], name=op.f("fk_asset_tags_added_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name=op.f("fk_asset_tags_asset_id_assets"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], name=op.f("fk_asset_tags_tag_id_tags"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("tag_id", "asset_id", name=op.f("pk_asset_tags")),
    )
    op.create_index(op.f("ix_asset_tags_asset_id"), "asset_tags", ["asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_asset_tags_asset_id"), table_name="asset_tags")
    op.drop_table("asset_tags")
    op.drop_table("tags")
