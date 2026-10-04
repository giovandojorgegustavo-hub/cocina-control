"""Precios: el plato mas barato pasa a S/ 25 y el resto sube segun su costo

Ajuste del dueno (04/10/2026) sobre la carta de 0027. Con el precio en el
doble exacto del costo el margen quedaba muy justo, y un precio unico para
todo se veia raro. Se mantiene la escalera por costo, corrida S/ 5 hacia
arriba: el plato mas barato de producir queda en 25 y el mas caro en 30.

    Wrap Fresh 25 · Wrap Mediterráneo Verde 26 · Energy Bowl 27 ·
    Arma tu Wrap 27 · Crispy Salad 28 · Arma tu Salad 29 · Focus Bowl 29 ·
    Arma tu Bowl 29 · BBQ Protein Salad 30

Postres, bebidas y extras no cambian.

Revision ID: 0029_precios_minimo_25
Revises: 0028_salsas_y_guacamole
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_precios_minimo_25"
down_revision: str | None = "0028_salsas_y_guacamole"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# nombre en mayusculas -> (precio nuevo, precio de 0027)
_PRICES: dict[str, tuple[str, str]] = {
    "WRAP FRESH": ("25.00", "20.00"),
    "WRAP MEDITERRÁNEO VERDE": ("26.00", "21.00"),
    "ENERGY BOWL": ("27.00", "22.00"),
    "ARMA TU WRAP": ("27.00", "22.00"),
    "CRISPY SALAD": ("28.00", "23.00"),
    "ARMA TU SALAD": ("29.00", "24.00"),
    "FOCUS BOWL": ("29.00", "24.00"),
    "ARMA TU BOWL": ("29.00", "24.00"),
    "BBQ PROTEIN SALAD": ("30.00", "25.00"),
}


def _set_prices(index: int) -> None:
    bind = op.get_bind()
    for name, prices in _PRICES.items():
        bind.execute(
            sa.text(
                "UPDATE products SET sale_price = :price "
                "WHERE upper(name) = :name AND is_sale = true"
            ),
            {"price": prices[index], "name": name},
        )


def upgrade() -> None:
    _set_prices(0)


def downgrade() -> None:
    _set_prices(1)
