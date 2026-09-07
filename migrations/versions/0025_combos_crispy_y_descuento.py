"""Combos: Crispy Salad como bowl a elegir, y descuento corregido a 35%

Dos correcciones sobre los combos, pedidas por el dueno:

1. CRISPY SALAD COMO BOWL DEL COMBO. La migracion 0024 dejo elegir el bowl del
   combo solo entre Focus y Energy. Ahora el Crispy Salad tambien se puede elegir
   como el bowl — en el Combo Office (grupo "Elige tu bowl") y en el Combo Double
   (sus dos grupos "Primer bowl" y "Segundo bowl"). El Combo Wrapper NO se toca:
   ahi se elige wrap. Igual que en 0024, el bowl se elige YA HECHO: la opcion
   enlaza al producto por nombre, precio 0.00 (el precio del combo ya lo cubre).
   El producto en la base es "Bowl Crispy"; para el cliente la opcion se llama
   "Crispy Salad" (mismo alias que 0023/0024).

2. DESCUENTO AL 35%. Los combos se cargaron con 30% de descuento, pero el
   descuento real es 35%. Se corrige products.discount_percent de 30 a 35 en los
   tres combos, y solo si siguen en 30 (para no pisar un cambio manual posterior
   hecho desde el panel). El precio final lo recalcula el sistema:
   54 -> 35.10, 51 -> 33.15, 110 -> 71.50.

IDEMPOTENCIA Y DOWNGRADE
------------------------
La opcion solo se inserta si el grupo no la tiene; el descuento solo se sube si
esta en 30. El downgrade borra esa opcion de esos tres grupos y baja el
descuento de 35 a 30 en los combos: deshace exactamente lo que se hizo, sin
tocar Focus, Energy, los grupos ni el producto Crispy Salad.

Revision ID: 0025_combos_crispy_descuento
Revises: 0024_combos_y_cubiertos
Create Date: 2026-09-07
"""

import unicodedata
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_combos_crispy_descuento"
down_revision: str | None = "0024_combos_y_cubiertos"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


_OPTION_NAME = "Crispy Salad"
_PRODUCT_NAME = "Crispy Salad"
_PRODUCT_ALIAS = "Bowl Crispy"
# En produccion los combos se llaman en MAYUSCULA ("COMBO OFFICE"); se cruzan
# sin caja para no depender de como quedaron cargados.
_TARGET_GROUPS = ["Elige tu bowl", "Primer bowl", "Segundo bowl"]
_COMBOS = ["COMBO OFFICE", "COMBO WRAPPER", "COMBO DOUBLE"]


def _key(name: str) -> str:
    collapsed = " ".join(name.strip().split()).upper()
    decomposed = unicodedata.normalize("NFKD", collapsed)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _find_crispy(conn: sa.Connection) -> uuid.UUID | None:
    products = conn.execute(
        sa.text("SELECT id, name FROM products WHERE is_active = true AND is_sale = true")
    ).all()
    by_key: dict[str, uuid.UUID] = {}
    for row in products:
        by_key.setdefault(_key(row.name), row.id)
    return by_key.get(_key(_PRODUCT_NAME)) or by_key.get(_key(_PRODUCT_ALIAS))


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Crispy Salad como opcion de bowl en los grupos del Office y el Double.
    product_id = _find_crispy(conn)  # None en una base de tests sin ese producto
    insert_item = sa.text(
        "INSERT INTO option_items "
        "(id, group_id, name, price, product_id, sort_order, is_active) "
        "VALUES (:id, :group_id, :name, :price, :product_id, :sort_order, true)"
    )
    for group_name in _TARGET_GROUPS:
        group_id = conn.execute(
            sa.text("SELECT id FROM option_groups WHERE name = :name LIMIT 1"),
            {"name": group_name},
        ).scalar()
        if group_id is None:
            continue
        already = conn.execute(
            sa.text(
                "SELECT 1 FROM option_items "
                "WHERE group_id = :group_id AND lower(name) = lower(:name) LIMIT 1"
            ),
            {"group_id": group_id, "name": _OPTION_NAME},
        ).scalar()
        if already is not None:
            continue
        next_sort = (
            conn.execute(
                sa.text(
                    "SELECT COALESCE(MAX(sort_order), -1) FROM option_items "
                    "WHERE group_id = :group_id"
                ),
                {"group_id": group_id},
            ).scalar()
            or -1
        ) + 1
        conn.execute(
            insert_item,
            {
                "id": uuid.uuid4(),
                "group_id": group_id,
                "name": _OPTION_NAME,
                "price": "0.00",
                "product_id": product_id,
                "sort_order": next_sort,
            },
        )

    # 2) Descuento de los combos: 30% -> 35% (solo los que siguen en 30).
    conn.execute(
        sa.text(
            "UPDATE products SET discount_percent = 35 "
            "WHERE upper(name) IN :names AND discount_percent = 30"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": _COMBOS},
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            "UPDATE products SET discount_percent = 30 "
            "WHERE upper(name) IN :names AND discount_percent = 35"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": _COMBOS},
    )

    for group_name in _TARGET_GROUPS:
        group_id = conn.execute(
            sa.text("SELECT id FROM option_groups WHERE name = :name LIMIT 1"),
            {"name": group_name},
        ).scalar()
        if group_id is None:
            continue
        conn.execute(
            sa.text(
                "DELETE FROM option_items "
                "WHERE group_id = :group_id AND lower(name) = lower(:name)"
            ),
            {"group_id": group_id, "name": _OPTION_NAME},
        )
