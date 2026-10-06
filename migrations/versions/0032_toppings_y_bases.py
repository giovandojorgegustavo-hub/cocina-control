"""Toppings y bases de los "Arma tu": salen pickles y cebolla, entran cuatro, champiñones +1

Pedido del negocio (06/10/2026):

- Toppings (en ambos grupos, "hasta 5" de bowl/salad y "hasta 6" de wrap):
    * salen Pickles y Cebolla roja (se desactivan: hay pedidos que los nombran)
    * entran Lechuga, Camote, Huevo y Piña dulce, sin costo
    * Champiñones salteados pasan a cobrar +S/ 1.00
- Base del Arma tu Bowl:
    * sale Lechuga orgánica (la lechuga ahora es topping)
    * se eligen entre 1 y 2 bases (antes exactamente 1), asi que el grupo pasa
      a seleccion multiple

Revision ID: 0032_toppings_y_bases
Revises: 0031_tilapia_extra_2_50
Create Date: 2026-10-06
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_toppings_y_bases"
down_revision: str | None = "0031_tilapia_extra_2_50"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TOPPING_GROUPS = ("Toppings (hasta 5)", "Toppings (hasta 6)")
_RETIRED = ("Pickles", "Cebolla roja")
_ADDED = ("Lechuga", "Camote", "Huevo", "Piña dulce")
_SURCHARGE = ("Champiñones salteados", "1.00")
_BASE_GROUP = "Base"
_BASE_RETIRED = "Lechuga orgánica"


def _group_ids(bind: sa.Connection, names: tuple[str, ...]) -> list[uuid.UUID]:
    return list(
        bind.execute(
            sa.text("SELECT id FROM option_groups WHERE name IN :names").bindparams(
                sa.bindparam("names", expanding=True)
            ),
            {"names": list(names)},
        ).scalars()
    )


def _set_active(
    bind: sa.Connection, group_ids: list[uuid.UUID], names: tuple[str, ...], active: bool
) -> None:
    if not group_ids:
        return
    bind.execute(
        sa.text(
            "UPDATE option_items SET is_active = :active "
            "WHERE group_id IN :groups AND name IN :names"
        ).bindparams(sa.bindparam("groups", expanding=True), sa.bindparam("names", expanding=True)),
        {"active": active, "groups": group_ids, "names": list(names)},
    )


def _set_price(bind: sa.Connection, group_ids: list[uuid.UUID], name: str, price: str) -> None:
    if not group_ids:
        return
    bind.execute(
        sa.text(
            "UPDATE option_items SET price = :price WHERE group_id IN :groups AND name = :name"
        ).bindparams(sa.bindparam("groups", expanding=True)),
        {"price": price, "groups": group_ids, "name": name},
    )


def upgrade() -> None:
    bind = op.get_bind()
    toppings = _group_ids(bind, _TOPPING_GROUPS)

    _set_active(bind, toppings, _RETIRED, False)
    _set_price(bind, toppings, *_SURCHARGE)

    for group_id in toppings:
        last = bind.execute(
            sa.text("SELECT COALESCE(MAX(sort_order), 0) FROM option_items WHERE group_id = :g"),
            {"g": group_id},
        ).scalar()
        for offset, name in enumerate(_ADDED, start=1):
            existing = bind.execute(
                sa.text(
                    "SELECT id FROM option_items WHERE group_id = :g AND lower(name) = lower(:n)"
                ),
                {"g": group_id, "n": name},
            ).scalar()
            if existing is not None:
                bind.execute(
                    sa.text("UPDATE option_items SET is_active = true, price = 0 WHERE id = :id"),
                    {"id": existing},
                )
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO option_items "
                    "(id, group_id, name, price, product_id, sort_order, is_active) "
                    "VALUES (:id, :g, :n, 0, NULL, :s, true)"
                ),
                {"id": uuid.uuid4(), "g": group_id, "n": name, "s": int(last) + offset},
            )

    base = _group_ids(bind, (_BASE_GROUP,))
    _set_active(bind, base, (_BASE_RETIRED,), False)
    bind.execute(
        sa.text(
            "UPDATE option_groups SET selection = 'multiple', min_choices = 1, max_choices = 2 "
            "WHERE name = :g"
        ),
        {"g": _BASE_GROUP},
    )


def downgrade() -> None:
    bind = op.get_bind()
    toppings = _group_ids(bind, _TOPPING_GROUPS)

    _set_active(bind, toppings, _RETIRED, True)
    _set_price(bind, toppings, _SURCHARGE[0], "0.00")
    # Los cuatro nuevos se apagan, no se borran: pudieron entrar en un pedido.
    _set_active(bind, toppings, _ADDED, False)

    base = _group_ids(bind, (_BASE_GROUP,))
    _set_active(bind, base, (_BASE_RETIRED,), True)
    bind.execute(
        sa.text(
            "UPDATE option_groups SET selection = 'single', min_choices = 1, max_choices = 1 "
            "WHERE name = :g"
        ),
        {"g": _BASE_GROUP},
    )
