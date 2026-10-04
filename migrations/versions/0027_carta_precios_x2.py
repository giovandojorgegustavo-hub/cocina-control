"""Carta nueva: precios al doble del costo, sin combos, proteína incluida

Decision del dueno (04/10/2026), como ultima estrategia para que entre gente:

1. PRECIOS. El precio de venta pasa a ser el doble del costo real del plato
   (el costo real ya incluye S/ 2 de empaque), redondeado a sol entero:

       Wrap Fresh 20 · Wrap Mediterráneo Verde 21 · Energy Bowl 22 ·
       Crispy Salad 23 · Arma tu Salad 24 · Focus Bowl 24 ·
       BBQ Protein Salad 25 · Arma tu Bowl 24 · Arma tu Wrap 22

2. PROTEÍNA INCLUIDA. En los "Arma tu ..." la proteina se cobraba aparte
   (+S/ 8) y el cliente descubria el precio real recien al final. Ahora el
   precio del plato ya la incluye: todas las opciones del grupo "Proteína"
   quedan en S/ 0.

3. SIN "PROTEÍNA EXTRA". El grupo confundia (se leia como obligatorio y como
   un segundo cobro). Se desactiva el grupo entero; los enlaces con los platos
   se conservan, asi el downgrade es reactivarlo y nada mas.

4. FUERA DE CARTA. Los tres combos (con los precios nuevos salian mas caros
   que pedir por separado) y el Mini Camote Burger. Se desactivan, no se
   borran: hay pedidos historicos que los referencian.

5. POSTRES. Se crean "Chocobrownie Frutos Rojos" (S/ 15) y "Pack 3
   Chocobrownies Frutos Rojos" (S/ 33), con cubiertos opcionales. Como en 0023,
   se atribuyen al owner mas antiguo; en una base sin usuarios (tests) no hay a
   quien atribuirlos y se omiten.

Todo se busca por nombre sin distinguir mayusculas: en produccion los combos
estan en mayusculas y los platos no. Lo que no exista se ignora.

Revision ID: 0027_carta_precios_x2
Revises: 0026_proteina_extra_opcional
Create Date: 2026-10-04
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_carta_precios_x2"
down_revision: str | None = "0026_proteina_extra_opcional"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# nombre en mayusculas -> (precio nuevo, precio anterior)
_PRICES: dict[str, tuple[str, str]] = {
    "WRAP FRESH": ("20.00", "28.00"),
    "WRAP MEDITERRÁNEO VERDE": ("21.00", "28.00"),
    "ENERGY BOWL": ("22.00", "33.00"),
    "CRISPY SALAD": ("23.00", "34.00"),
    "ARMA TU SALAD": ("24.00", "24.90"),
    "FOCUS BOWL": ("24.00", "33.00"),
    "BBQ PROTEIN SALAD": ("25.00", "36.00"),
    "ARMA TU BOWL": ("24.00", "24.90"),
    "ARMA TU WRAP": ("22.00", "21.90"),
}

_RETIRED = ("COMBO OFFICE", "COMBO WRAPPER", "COMBO DOUBLE", "MINI CAMOTE BURGER")

_PROTEIN_GROUP = "Proteína"
_PROTEIN_FREE_ITEM = "Sin proteína"
_PROTEIN_OLD_PRICE = "8.00"
_EXTRA_GROUP = "Proteína extra"
_RETIRED_EXTRA_ITEM = "Mini Camote Burger"

_NEW_PRODUCTS: tuple[tuple[str, str], ...] = (
    ("Chocobrownie Frutos Rojos", "15.00"),
    ("Pack 3 Chocobrownies Frutos Rojos", "33.00"),
)
_CUTLERY_GROUP = "Cubiertos"


def _set_prices(bind: sa.Connection, index: int) -> None:
    for name, prices in _PRICES.items():
        bind.execute(
            sa.text(
                "UPDATE products SET sale_price = :price "
                "WHERE upper(name) = :name AND is_sale = true"
            ),
            {"price": prices[index], "name": name},
        )


def _set_active(bind: sa.Connection, names: tuple[str, ...], active: bool) -> None:
    bind.execute(
        sa.text(
            "UPDATE products SET is_active = :active "
            "WHERE upper(name) IN :names AND is_sale = true"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"active": active, "names": list(names)},
    )


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Precios nuevos.
    _set_prices(bind, 0)

    # 2. La proteina va incluida en el precio del plato.
    bind.execute(
        sa.text(
            "UPDATE option_items SET price = 0 "
            "WHERE group_id IN (SELECT id FROM option_groups WHERE name = :g)"
        ),
        {"g": _PROTEIN_GROUP},
    )

    # 3. Sin "Proteína extra".
    bind.execute(
        sa.text("UPDATE option_groups SET is_active = false WHERE name = :g"),
        {"g": _EXTRA_GROUP},
    )

    # 4. Combos y Mini Camote Burger fuera de carta (plato y adicional).
    _set_active(bind, _RETIRED, False)
    bind.execute(
        sa.text("UPDATE option_items SET is_active = false WHERE name = :n"),
        {"n": _RETIRED_EXTRA_ITEM},
    )

    # 5. Postres nuevos.
    owner = bind.execute(
        sa.text(
            "SELECT id FROM users "
            "ORDER BY CASE role::text WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, "
            "created_at, id LIMIT 1"
        )
    ).scalar()
    if owner is None:
        return
    cutlery = bind.execute(
        sa.text("SELECT id FROM option_groups WHERE name = :g"), {"g": _CUTLERY_GROUP}
    ).scalar()
    for name, price in _NEW_PRODUCTS:
        existing = bind.execute(
            sa.text("SELECT id FROM products WHERE upper(name) = upper(:n)"), {"n": name}
        ).scalar()
        if existing is not None:
            bind.execute(
                sa.text(
                    "UPDATE products SET is_active = true, is_sale = true, sale_price = :p "
                    "WHERE id = :id"
                ),
                {"p": price, "id": existing},
            )
            continue
        product_id = uuid.uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO products (id, name, unit, is_active, is_purchase, is_sale, "
                "sale_price, created_by) "
                "VALUES (:id, :name, 'un', true, false, true, :price, :owner)"
            ),
            {"id": product_id, "name": name, "price": price, "owner": owner},
        )
        if cutlery is not None:
            bind.execute(
                sa.text(
                    "INSERT INTO product_option_groups (product_id, group_id, sort_order) "
                    "VALUES (:pid, :gid, 0)"
                ),
                {"pid": product_id, "gid": cutlery},
            )


def downgrade() -> None:
    bind = op.get_bind()

    _set_prices(bind, 1)

    bind.execute(
        sa.text(
            "UPDATE option_items SET price = :price "
            "WHERE name <> :free "
            "AND group_id IN (SELECT id FROM option_groups WHERE name = :g)"
        ),
        {"price": _PROTEIN_OLD_PRICE, "free": _PROTEIN_FREE_ITEM, "g": _PROTEIN_GROUP},
    )

    bind.execute(
        sa.text("UPDATE option_groups SET is_active = true WHERE name = :g"),
        {"g": _EXTRA_GROUP},
    )

    _set_active(bind, _RETIRED, True)
    bind.execute(
        sa.text("UPDATE option_items SET is_active = true WHERE name = :n"),
        {"n": _RETIRED_EXTRA_ITEM},
    )

    # Los postres no se borran: pudo haberse vendido alguno. Salen de la carta.
    _set_active(bind, tuple(name.upper() for name, _ in _NEW_PRODUCTS), False)
