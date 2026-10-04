"""Salsas: salen palta, mayonesa y BBQ; entra el guacamole con costo extra

Pedido del negocio (04/10/2026):

- Se retiran de la carta la Salsa de palta proteica, la Mayonesa proteica y la
  Salsa BBQ. Se desactivan como opcion (hay pedidos historicos que las
  nombran, por eso no se borran).
- Entra el guacamole como opcion de salsa CON costo:
    * bowls y ensaladas: "Guacamole 4 oz" a +S/ 1.50
    * wraps:             "Guacamole 2 oz" a +S/ 1.00

El tamano y el precio dependen del tipo de plato, y hasta ahora los wraps
compartian el grupo "Salsa" con los bowls. Por eso se crea el grupo "Salsa
wrap" (mismas salsas sin costo + el guacamole de 2 oz) y los wraps pasan a
usarlo en la misma posicion donde tenian "Salsa". Los bowls y ensaladas siguen
con "Salsa", que suma el guacamole de 4 oz.

Quedan sin costo en ambos grupos: Honey Mustard proteica, Salsa Runch proteica
y Vinagreta.

Revision ID: 0028_salsas_y_guacamole
Revises: 0027_carta_precios_x2
Create Date: 2026-10-04
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_salsas_y_guacamole"
down_revision: str | None = "0027_carta_precios_x2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_GROUP = "Salsa"
_WRAP_GROUP = "Salsa wrap"
_RETIRED = ("Salsa de palta proteica", "Mayonesa proteica", "Salsa BBQ")
_KEPT = ("Honey Mustard proteica", "Salsa Runch proteica", "Vinagreta")
_GUACAMOLE_BOWL = ("Guacamole 4 oz", "1.50")
_GUACAMOLE_WRAP = ("Guacamole 2 oz", "1.00")
_WRAPS = ("WRAP FRESH", "WRAP MEDITERRÁNEO VERDE", "ARMA TU WRAP")


def _group_id(bind: sa.Connection, name: str) -> uuid.UUID | None:
    return bind.execute(
        sa.text("SELECT id FROM option_groups WHERE name = :n"), {"n": name}
    ).scalar()


def _upsert_item(
    bind: sa.Connection,
    group_id: uuid.UUID,
    name: str,
    price: str,
    sort_order: int,
    product_id: uuid.UUID | None = None,
) -> None:
    """Crea la opcion o la reactiva con su precio: la migracion se puede repetir."""
    existing = bind.execute(
        sa.text("SELECT id FROM option_items WHERE group_id = :g AND lower(name) = lower(:n)"),
        {"g": group_id, "n": name},
    ).scalar()
    if existing is not None:
        bind.execute(
            sa.text("UPDATE option_items SET is_active = true, price = :p WHERE id = :id"),
            {"p": price, "id": existing},
        )
        return
    bind.execute(
        sa.text(
            "INSERT INTO option_items "
            "(id, group_id, name, price, product_id, sort_order, is_active) "
            "VALUES (:id, :g, :n, :p, :product_id, :s, true)"
        ),
        {
            "id": uuid.uuid4(),
            "g": group_id,
            "n": name,
            "p": price,
            "product_id": product_id,
            "s": sort_order,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    salsa = _group_id(bind, _GROUP)
    if salsa is None:
        return

    # 1. Salen tres salsas del grupo comun.
    bind.execute(
        sa.text(
            "UPDATE option_items SET is_active = false "
            "WHERE group_id = :g AND name IN :names"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"g": salsa, "names": list(_RETIRED)},
    )

    # 2. Guacamole de 4 oz para bowls y ensaladas.
    _upsert_item(bind, salsa, _GUACAMOLE_BOWL[0], _GUACAMOLE_BOWL[1], sort_order=90)

    # 3. Grupo propio de los wraps: mismas salsas sin costo + guacamole de 2 oz.
    wrap_group = _group_id(bind, _WRAP_GROUP)
    if wrap_group is None:
        wrap_group = uuid.uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO option_groups "
                "(id, name, selection, required, min_choices, max_choices, sort_order, is_active) "
                "SELECT :id, :name, selection, required, min_choices, max_choices, sort_order, true "
                "FROM option_groups WHERE id = :src"
            ),
            {"id": wrap_group, "name": _WRAP_GROUP, "src": salsa},
        )
    else:
        bind.execute(
            sa.text("UPDATE option_groups SET is_active = true WHERE id = :id"),
            {"id": wrap_group},
        )
    kept = bind.execute(
        sa.text(
            "SELECT name, product_id, sort_order FROM option_items "
            "WHERE group_id = :g AND name IN :names ORDER BY sort_order, name"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"g": salsa, "names": list(_KEPT)},
    ).all()
    for row in kept:
        _upsert_item(bind, wrap_group, row.name, "0.00", row.sort_order, row.product_id)
    _upsert_item(bind, wrap_group, _GUACAMOLE_WRAP[0], _GUACAMOLE_WRAP[1], sort_order=90)

    # 4. Los wraps cambian "Salsa" por "Salsa wrap", en la misma posicion.
    bind.execute(
        sa.text(
            "UPDATE product_option_groups SET group_id = :wrap "
            "WHERE group_id = :salsa AND product_id IN "
            "(SELECT id FROM products WHERE upper(name) IN :names)"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"wrap": wrap_group, "salsa": salsa, "names": list(_WRAPS)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    salsa = _group_id(bind, _GROUP)
    if salsa is None:
        return
    wrap_group = _group_id(bind, _WRAP_GROUP)

    if wrap_group is not None:
        bind.execute(
            sa.text(
                "UPDATE product_option_groups SET group_id = :salsa WHERE group_id = :wrap"
            ),
            {"salsa": salsa, "wrap": wrap_group},
        )
        # Se apaga, no se borra: pudo quedar nombrado en algun pedido.
        bind.execute(
            sa.text("UPDATE option_groups SET is_active = false WHERE id = :id"),
            {"id": wrap_group},
        )

    bind.execute(
        sa.text(
            "UPDATE option_items SET is_active = false WHERE group_id = :g AND name = :n"
        ),
        {"g": salsa, "n": _GUACAMOLE_BOWL[0]},
    )
    bind.execute(
        sa.text(
            "UPDATE option_items SET is_active = true "
            "WHERE group_id = :g AND name IN :names"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"g": salsa, "names": list(_RETIRED)},
    )
