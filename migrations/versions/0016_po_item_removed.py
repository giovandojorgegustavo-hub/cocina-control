"""po item removed flag

Columna removed en purchase_order_items (issue #101): quitar una linea de una
orden abierta se modela como una correccion append-only con removed=true
(la cantidad copia la anterior porque el CHECK exige expected_qty > 0).
get_active_items filtra las hojas removidas — unico punto de paso.

Revision ID: 0016_po_item_removed
Revises: 0015_product_flags
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_po_item_removed"
down_revision: str | None = "0015_product_flags"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "purchase_order_items",
        sa.Column("removed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("purchase_order_items", "removed")
