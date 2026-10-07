"""Se apaga la promocion de primera compra (15%)

Decision del dueno (06/10/2026): con la carta a S/ 24.90 ya no hay descuento
de ningun tipo. La promo se desactiva, no se borra: los pedidos historicos la
referencian por codigo y el reporte de ventas la necesita.

Con is_active = false, /catalog/promotions deja de listarla (el asistente deja
de ofrecerla) y /sales-orders rechaza el codigo si alguien lo manda igual.

Revision ID: 0034_sin_descuento
Revises: 0033_platos_listos_24_90
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_sin_descuento"
down_revision: str | None = "0033_platos_listos_24_90"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_CODE = "primera_compra"


def _set(active: bool) -> None:
    op.get_bind().execute(
        sa.text("UPDATE promotions SET is_active = :a WHERE code = :c"),
        {"a": active, "c": _CODE},
    )


def upgrade() -> None:
    _set(False)


def downgrade() -> None:
    _set(True)
