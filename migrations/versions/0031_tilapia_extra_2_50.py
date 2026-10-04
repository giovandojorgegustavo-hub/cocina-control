"""La tilapia de los "Arma tu" suma S/ 2.50 en vez de S/ 3

Ajuste del dueno sobre 0030, el mismo dia: S/ 3 de extra se sentia mucho
frente a la milanesa (+2). La tilapia cuesta S/ 1.70 mas que el pollo, asi que
+2.50 sigue cubriendo la diferencia con margen.

Revision ID: 0031_tilapia_extra_2_50
Revises: 0030_proteinas_con_diferencia
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_tilapia_extra_2_50"
down_revision: str | None = "0030_proteinas_con_diferencia"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _set(price: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE option_items SET price = :price "
            "WHERE name = 'Tilapia' "
            "AND group_id IN (SELECT id FROM option_groups WHERE name = 'Proteína')"
        ),
        {"price": price},
    )


def upgrade() -> None:
    _set("2.50")


def downgrade() -> None:
    _set("3.00")
