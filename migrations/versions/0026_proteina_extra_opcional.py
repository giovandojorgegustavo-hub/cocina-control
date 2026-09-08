"""Proteína extra deja de ser obligatoria

El grupo "Proteína extra" se sembro como obligatorio (min 1). En la carta web eso
bloqueaba el boton "Agregar al pedido" hasta que el cliente elegia algo en ese
grupo: como trae la opcion "Sin proteina extra", el que solo queria su bowl
normal quedaba trabado sin entender por que, y varios escribieron que "la carta
no sirve". Una proteina EXTRA, por definicion, es opcional: nadie deberia estar
obligado a agregarla.

Se cambia el grupo a NO obligatorio (required=false, min_choices=0). Sigue
siendo de eleccion multiple hasta 2, asi que quien quiera sumar una o dos
proteinas extra puede; quien no, agrega su plato sin tocar el grupo. No se toca
"Proteína" (la del bowl, que si es parte de armarlo y se satisface con "Sin
proteína").

El downgrade restaura el obligatorio (required=true, min_choices=1).

Revision ID: 0026_proteina_extra_opcional
Revises: 0025_combos_crispy_descuento
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_proteina_extra_opcional"
down_revision: str | None = "0025_combos_crispy_descuento"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_GROUP = "Proteína extra"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE option_groups SET required = false, min_choices = 0 WHERE name = :name"
        ),
        {"name": _GROUP},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE option_groups SET required = true, min_choices = 1 WHERE name = :name"
        ),
        {"name": _GROUP},
    )
