"""Los seis platos ya armados pasan a S/ 24.90; los "Arma tu" no cambian

Decision del dueno (06/10/2026): un solo precio para todo lo que sale listo
de cocina (bowls, ensaladas y wraps fijos). Los "Arma tu" conservan su
precio porque el cliente les suma proteina y toppings con costo.

Revision ID: 0033_platos_listos_24_90
Revises: 0032_toppings_y_bases
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_platos_listos_24_90"
down_revision: str | None = "0032_toppings_y_bases"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_NEW = "24.90"
# nombre en mayusculas -> precio de 0029 (para el downgrade)
_BEFORE: dict[str, str] = {
    "FOCUS BOWL": "27.00",
    "ENERGY BOWL": "26.00",
    "BBQ PROTEIN SALAD": "28.00",
    "CRISPY SALAD": "27.00",
    "WRAP FRESH": "25.00",
    "WRAP MEDITERRÁNEO VERDE": "26.00",
}


def _set(prices: dict[str, str]) -> None:
    bind = op.get_bind()
    for name, price in prices.items():
        bind.execute(
            sa.text(
                "UPDATE products SET sale_price = :price "
                "WHERE upper(name) = :name AND is_sale = true"
            ),
            {"price": price, "name": name},
        )


def upgrade() -> None:
    _set(dict.fromkeys(_BEFORE, _NEW))


def downgrade() -> None:
    _set(_BEFORE)
