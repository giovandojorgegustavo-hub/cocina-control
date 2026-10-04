"""Proteínas de los "Arma tu": el pollo va incluido, las demas suman la diferencia

En 0027 todas las proteinas quedaron en S/ 0 (incluidas en el precio). Pero no
cuestan lo mismo: filete de pollo 2.80, pollo en BBQ 3.50, milanesa 4.00,
tilapia 4.50. Con el mismo precio para todas, quien elegia tilapia se llevaba
S/ 1.70 mas de costo que el plato no cobraba.

El precio del plato incluye el filete de pollo. Las otras suman lo que cuestan
de mas, redondeado a sol entero para que el cliente lo lea facil:

    Filete de pollo                        incluido
    Filete de pollo en salsa BBQ ahumada   + S/ 1
    Milanesa                               + S/ 2
    Tilapia                                + S/ 3

"Sin proteína" sigue en 0. El grupo sigue siendo de una sola eleccion.

Revision ID: 0030_proteinas_con_diferencia
Revises: 0029_precios_minimo_25
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_proteinas_con_diferencia"
down_revision: str | None = "0029_precios_minimo_25"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_GROUP = "Proteína"
_SURCHARGES: dict[str, str] = {
    "Filete de pollo en salsa BBQ ahumada": "1.00",
    "Milanesa": "2.00",
    "Tilapia": "3.00",
}


def _set(prices: dict[str, str]) -> None:
    bind = op.get_bind()
    for name, price in prices.items():
        bind.execute(
            sa.text(
                "UPDATE option_items SET price = :price "
                "WHERE name = :name "
                "AND group_id IN (SELECT id FROM option_groups WHERE name = :g)"
            ),
            {"price": price, "name": name, "g": _GROUP},
        )


def upgrade() -> None:
    _set(_SURCHARGES)


def downgrade() -> None:
    _set(dict.fromkeys(_SURCHARGES, "0.00"))
