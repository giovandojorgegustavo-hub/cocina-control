"""product purchase/sale flags

Flags independientes por producto (issue #140): is_purchase (insumo que se
compra) e is_sale (item que se vende en pedidos). Un producto puede ser ambos
(ej. gaseosa que se compra y se vende tal cual). Al menos uno debe ser true.

Los productos existentes quedan como compra (server_default true/false):
decision del dueño — "ahorita todos los productos deberian tener de compras".

Revision ID: 0015_product_flags
Revises: 0014_suppliers
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_product_flags"
down_revision: str | None = "0014_suppliers"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("is_purchase", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "products",
        sa.Column("is_sale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_check_constraint(
        "ck_products_purchase_or_sale",
        "products",
        "is_purchase OR is_sale",
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_purchase_or_sale", "products", type_="check")
    op.drop_column("products", "is_sale")
    op.drop_column("products", "is_purchase")
