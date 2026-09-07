"""combos que se eligen de verdad, y cubiertos opcionales por plato

Los combos de la carta (Office, Wrapper, Double) prometian cosas que el cliente
no podia elegir. En carta.json el Combo Office dice "1 bowl a eleccion + 1
bebida", pero eso vivia como TEXTO: la migracion 0023 les asigno los mismos
grupos que a cualquier bowl (Proteina extra / Salsa / Adicionales) y nada mas.
No habia forma de que el asistente preguntara CUAL bowl ni CUAL bebida, porque
esos grupos no existian. El combo se vendia y despues, en la cocina, alguien
adivinaba.

El dueno quiere que el combo se arme eligiendo. Y lo importante: los combos se
arman con bowls YA HECHOS (Focus o Energy), no con "Arma tu Bowl". Por eso NO
hay configuracion anidada — no se eligen la base, los toppings ni la proteina
del bowl del combo. Se elige el bowl entero, como quien senala una foto en la
carta. La opcion enlaza al producto por nombre (product_id) para que el consumo
de insumos de ese bowl salga del pedido, pero su precio es 0.00: el precio del
combo ya cubre el bowl, y cobrar el bowl aparte lo contaria dos veces, el mismo
motivo por el que seed_sale_products dejo los combos fuera del catalogo.

LOS GRUPOS NUEVOS
-----------------
Ocho grupos, todos de una sola opcion (single):

- "Elige tu bowl" / "Elige tu wrap" — el pick del Combo Office / Wrapper.
  Obligatorio, uno solo. Sus opciones son los bowls/wraps ya armados, a 0.00,
  enlazados a su producto.
- "Bebida" — la bebida del Office / Wrapper. Obligatorio, uno. Hoy la unica
  bebida de la carta es el Maracuya 12 oz; el grupo queda listo para sumar mas.
- "Primer bowl" / "Segundo bowl" / "Primera bebida" / "Segunda bebida" — el
  Combo Double son dos bowls y dos bebidas, y cada pick es su propio grupo
  porque el modelo de opciones cuenta por grupo: dos grupos "bowl" separados es
  la unica forma de exigir exactamente dos elecciones sin permitir dos veces el
  mismo por accidente en un grupo de "elige 2".
- "Cubiertos" — la unica excepcion opcional. NO obligatorio, hasta uno. Sus
  opciones NO enlazan producto: "Sin cubiertos" 0.00, "1 cubierto" S/1.00,
  "2 cubiertos" S/2.00. El cliente que no quiere cubiertos elige "Sin
  cubiertos" o no elige nada; el que quiere paga S/1 por cubierto, hasta dos.

POR QUE LOS CUBIERTOS VAN POR PLATO
-----------------------------------
El dueno querria cobrarlos una vez por pedido. Pero el modelo de opciones es
por PLATO (product_option_groups): una opcion cuelga de un item del pedido, no
del pedido entero. No existe hoy un lugar donde poner un cargo a nivel de
pedido, asi que "Cubiertos" se asigna como grupo a cada plato que puede ir
solo — los bowls, las salads, los wraps y los tres combos. Es una limitacion
conocida del modelo, no una decision de producto: si manana hay un cargo por
pedido, los cubiertos se mudan ahi. Se asigna a los platos armables y a los
combos; se APENDEA al final del orden de grupos que 0023 ya les dio, sin tocar
Proteina extra / Salsa / Adicionales.

IDEMPOTENCIA Y DOWNGRADE
------------------------
La siembra solo inserta lo que falta: un grupo si no hay otro con ese nombre,
una opcion si no esta en su grupo, una asignacion si ese (plato, grupo) no
existe. Correrla dos veces no duplica nada. Los platos se cruzan por nombre sin
caja ni tildes, con los mismos alias que 0023 (BBQ Protein Salad -> BBQ Protein
Bowl, Crispy Salad -> Bowl Crispy); un plato que no existe como producto se
salta, igual que en una base de tests recien creada.

El downgrade deshace EXACTAMENTE lo que esta migracion creo: borra las
asignaciones de estos grupos, despues sus opciones, y al final los grupos por
nombre. Es seguro porque estas filas todavia no tienen historia de pedidos
apuntando — sales_order_item_options.option_item_id es SET NULL de todos modos,
pero aca no hace falta: nada las referencia aun. No se borra ningun combo ni
plato: son datos que 0023 y el catalogo ya administran.

Revision ID: 0024_combos_y_cubiertos
Revises: 0023_opciones_de_plato
Create Date: 2026-09-07
"""

import unicodedata
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_combos_y_cubiertos"
down_revision: str | None = "0023_opciones_de_plato"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Datos de siembra.
#
# Cada opcion: (nombre, precio, enlaza_a_producto). Cuando enlaza_a_producto es
# True, el nombre de la opcion ES el nombre del producto y se cruza por nombre
# igual que los platos; el bowl/wrap/bebida ya armado cuelga de su producto.
# Cuando es False (los cubiertos), la opcion no es un producto del catalogo.
#
# Cada grupo: (clave, nombre, min, max, [opciones]). max = 1 en todos, asi que
# todos son 'single'. required se deriva de min >= 1: obligatorios menos los
# cubiertos.
# ---------------------------------------------------------------------------

_BOWLS: list[tuple[str, str, bool]] = [
    ("Focus Bowl", "0.00", True),
    ("Energy Bowl", "0.00", True),
]
_BEBIDA: list[tuple[str, str, bool]] = [
    ("Maracuyá refrescante 12 oz", "0.00", True),
]

SEED_GROUPS: list[tuple[str, str, int, int, list[tuple[str, str, bool]]]] = [
    ("elige-bowl", "Elige tu bowl", 1, 1, list(_BOWLS)),
    (
        "elige-wrap",
        "Elige tu wrap",
        1,
        1,
        [
            ("Wrap Fresh", "0.00", True),
            ("Wrap Mediterráneo Verde", "0.00", True),
        ],
    ),
    ("bebida", "Bebida", 1, 1, list(_BEBIDA)),
    ("primer-bowl", "Primer bowl", 1, 1, list(_BOWLS)),
    ("segundo-bowl", "Segundo bowl", 1, 1, list(_BOWLS)),
    ("primera-bebida", "Primera bebida", 1, 1, list(_BEBIDA)),
    ("segunda-bebida", "Segunda bebida", 1, 1, list(_BEBIDA)),
    (
        "cubiertos",
        "Cubiertos",
        0,
        1,
        [
            ("Sin cubiertos", "0.00", False),
            ("1 cubierto", "1.00", False),
            ("2 cubiertos", "2.00", False),
        ],
    ),
]

# Que grupos se apendean a cada plato, en orden. Los combos reciben sus picks;
# todo plato que puede ir solo recibe "Cubiertos".
SEED_ASSIGNMENTS: list[tuple[str, list[str]]] = [
    ("Combo Office", ["elige-bowl", "bebida", "cubiertos"]),
    ("Combo Wrapper", ["elige-wrap", "bebida", "cubiertos"]),
    (
        "Combo Double",
        ["primer-bowl", "segundo-bowl", "primera-bebida", "segunda-bebida", "cubiertos"],
    ),
    ("Focus Bowl", ["cubiertos"]),
    ("Energy Bowl", ["cubiertos"]),
    ("Arma tu Bowl", ["cubiertos"]),
    ("BBQ Protein Salad", ["cubiertos"]),
    ("Crispy Salad", ["cubiertos"]),
    ("Arma tu Salad", ["cubiertos"]),
    ("Wrap Fresh", ["cubiertos"]),
    ("Wrap Mediterráneo Verde", ["cubiertos"]),
    ("Arma tu Wrap", ["cubiertos"]),
]

# Los mismos alias que 0023: carta.json -> products.
_DISH_ALIASES: dict[str, str] = {
    "BBQ Protein Salad": "BBQ Protein Bowl",
    "Crispy Salad": "Bowl Crispy",
}


def _key(name: str) -> str:
    """Sin tildes, sin caja, sin espacios de mas — igual que 0023."""
    collapsed = " ".join(name.strip().split()).upper()
    decomposed = unicodedata.normalize("NFKD", collapsed)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _seed(conn: sa.Connection) -> None:
    products = conn.execute(
        sa.text("SELECT id, name FROM products WHERE is_active = true AND is_sale = true")
    ).all()
    product_by_key: dict[str, uuid.UUID] = {}
    for row in products:
        product_by_key.setdefault(_key(row.name), row.id)

    def find_product(name: str) -> uuid.UUID | None:
        found = product_by_key.get(_key(name))
        if found is None and name in _DISH_ALIASES:
            found = product_by_key.get(_key(_DISH_ALIASES[name]))
        return found

    # Los grupos nuevos se ordenan despues de los que ya existen: sort_order es
    # solo un desempate en la carta, pero mantenerlo creciente evita que un
    # grupo nuevo se cuele entre los de 0023.
    next_group_sort = (
        conn.execute(sa.text("SELECT COALESCE(MAX(sort_order), -1) FROM option_groups")).scalar()
        or -1
    ) + 1

    insert_group = sa.text(
        "INSERT INTO option_groups "
        "(id, name, selection, required, min_choices, max_choices, sort_order, is_active) "
        "VALUES (:id, :name, :selection, :required, :min_choices, :max_choices, "
        ":sort_order, true)"
    )
    insert_item = sa.text(
        "INSERT INTO option_items "
        "(id, group_id, name, price, product_id, sort_order, is_active) "
        "VALUES (:id, :group_id, :name, :price, :product_id, :sort_order, true)"
    )
    insert_assignment = sa.text(
        "INSERT INTO product_option_groups (product_id, group_id, sort_order) "
        "VALUES (:product_id, :group_id, :sort_order)"
    )

    group_ids: dict[str, uuid.UUID] = {}
    for key, name, minimum, maximum, items in SEED_GROUPS:
        existing = conn.execute(
            sa.text("SELECT id FROM option_groups WHERE name = :name LIMIT 1"),
            {"name": name},
        ).scalar()
        if existing is not None:
            group_id = existing
        else:
            group_id = uuid.uuid4()
            conn.execute(
                insert_group,
                {
                    "id": group_id,
                    "name": name,
                    "selection": "single" if maximum == 1 else "multiple",
                    "required": minimum >= 1,
                    "min_choices": minimum,
                    "max_choices": maximum,
                    "sort_order": next_group_sort,
                },
            )
            next_group_sort += 1
        group_ids[key] = group_id

        for item_position, (item_name, price, linked) in enumerate(items):
            already = conn.execute(
                sa.text(
                    "SELECT 1 FROM option_items "
                    "WHERE group_id = :group_id AND lower(name) = lower(:name) LIMIT 1"
                ),
                {"group_id": group_id, "name": item_name},
            ).scalar()
            if already is not None:
                continue
            conn.execute(
                insert_item,
                {
                    "id": uuid.uuid4(),
                    "group_id": group_id,
                    "name": item_name,
                    "price": price,
                    "product_id": find_product(item_name) if linked else None,
                    "sort_order": item_position,
                },
            )

    for dish_name, option_keys in SEED_ASSIGNMENTS:
        product_id = find_product(dish_name)
        if product_id is None:
            continue
        # Apendear despues de lo que el plato ya tiene (los grupos de 0023).
        next_sort = (
            conn.execute(
                sa.text(
                    "SELECT COALESCE(MAX(sort_order), -1) FROM product_option_groups "
                    "WHERE product_id = :product_id"
                ),
                {"product_id": product_id},
            ).scalar()
            or -1
        ) + 1
        for key in option_keys:
            group_id = group_ids[key]
            already = conn.execute(
                sa.text(
                    "SELECT 1 FROM product_option_groups "
                    "WHERE product_id = :product_id AND group_id = :group_id LIMIT 1"
                ),
                {"product_id": product_id, "group_id": group_id},
            ).scalar()
            if already is not None:
                continue
            conn.execute(
                insert_assignment,
                {"product_id": product_id, "group_id": group_id, "sort_order": next_sort},
            )
            next_sort += 1


def _unseed(conn: sa.Connection) -> None:
    names = [name for _, name, *_ in SEED_GROUPS]
    ids = (
        conn.execute(
            sa.text("SELECT id FROM option_groups WHERE name IN :names").bindparams(
                sa.bindparam("names", expanding=True)
            ),
            {"names": names},
        )
        .scalars()
        .all()
    )
    if not ids:
        return
    # Orden: asignaciones, despues opciones, despues grupos. El CASCADE de las
    # FKs bastaria, pero hacerlo explicito deja claro que no queda nada colgado.
    for table in ("product_option_groups", "option_items"):
        conn.execute(
            sa.text(f"DELETE FROM {table} WHERE group_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": list(ids)},
        )
    conn.execute(
        sa.text("DELETE FROM option_groups WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": list(ids)},
    )


def upgrade() -> None:
    _seed(op.get_bind())


def downgrade() -> None:
    _unseed(op.get_bind())
