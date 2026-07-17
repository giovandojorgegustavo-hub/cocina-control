"""suppliers

Tabla de proveedores (issue #129). Paga la deuda tecnica de la decision P1
(proveedor como texto libre): las ordenes conservan supplier_name como texto
historico inmutable; esta tabla es el registro que alimenta el combobox.

Revision ID: 0014_suppliers
Revises: 0013_three_roles
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_suppliers"
down_revision: str | None = "0013_three_roles"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
    )
    # Uniqueness only among active suppliers — mirrors products.
    op.create_index(
        "ix_suppliers_name_active_unique",
        "suppliers",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_suppliers_name_active_unique",
        table_name="suppliers",
        postgresql_where=sa.text("is_active = true"),
    )
    op.drop_table("suppliers")
