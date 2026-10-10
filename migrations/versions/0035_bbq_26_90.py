"""BBQ Protein Salad sube a S/ 26.90

Pedido del negocio (10/10/2026). Es el plato de mayor costo (12.35) y a 24.90
dejaba el margen mas bajo de la carta; a 26.90 queda cerca del resto.

Revision ID: 0035_bbq_26_90
Revises: 0034_sin_descuento
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_bbq_26_90"
down_revision: str | None = "0034_sin_descuento"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _set(price: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE products SET sale_price = :price "
            "WHERE upper(name) = 'BBQ PROTEIN SALAD' AND is_sale = true"
        ),
        {"price": price},
    )


def upgrade() -> None:
    _set("26.90")


def downgrade() -> None:
    _set("24.90")
