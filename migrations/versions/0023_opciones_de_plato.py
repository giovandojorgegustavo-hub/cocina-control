"""opciones de plato: grupos de opciones con precio, asignados por plato

Hasta hoy una linea de pedido puede llevar opciones (sales_order_item_options),
pero son texto libre: un option_group y un option_name que el asistente de
WhatsApp escribe como le parece, y un product_id opcional que es la UNICA forma
de que una opcion tenga precio. No existe en ninguna parte la lista de que
opciones admite cada plato, cuales son obligatorias, si se elige una o varias,
ni cuanto cuesta "Filete de pollo +S/ 8". Esa lista vive hoy en dos lugares que
no se hablan: el carta.json de la web publica y el prompt del asistente. Cuando
el dueno cambia un precio, hay que tocar los dos a mano y rezar para que queden
iguales.

Se agregan tres tablas y una columna, y el criterio es el mismo que en 0022:
lo que el dueno edita vive en la base, y el bot y la carta LEEN de ahi.

1. option_groups — un grupo de opciones: "Base", "Toppings (hasta 5)",
   "Proteína extra". Tiene selection ('single' o 'multiple'), required, y los
   limites min_choices / max_choices. required y min_choices se guardan los dos
   aunque se impliquen: required es lo que el panel muestra como "Obligatorio"
   y min_choices es lo que el servidor cuenta; un grupo obligatorio tiene
   min_choices >= 1 y la API lo garantiza al escribir. El CHECK de la base se
   queda en lo simple (min >= 0, max >= 1) porque "single implica max = 1" se
   aplica en la API, donde el mensaje de error puede decir por que.

2. option_items — cada opcion con su precio. precio 0 es "incluido"; no hay
   NULL porque "a consultar" no es un importe que un pedido pueda sumar.
   product_id es opcional y se usa cuando la opcion ES un producto del
   catalogo (una bebida, el chucrut): asi el consumo de insumos de ese
   producto sigue saliendo del pedido. Pero el precio que se cobra es
   option_items.price, NO el del producto: lo que cuesta un adicional dentro de
   un bowl lo decide el grupo, no la carta general.

3. product_option_groups — que grupos admite cada plato, y en que orden. Es la
   asignacion que hoy vive en la lista `opciones` de cada item de carta.json.

4. sales_order_item_options.option_item_id — el enlace desde una opcion pedida
   hacia la opcion del catalogo. option_group, option_name y price_delta NO se
   tocan: siguen siendo la historia congelada de lo que el cliente eligio y a
   cuanto, igual que unit_price. Si el dueno renombra "Toppings (hasta 5)" o
   sube la proteina a 9, los pedidos de ayer siguen diciendo lo que dijeron.
   ON DELETE SET NULL por el mismo motivo: borrar una opcion del catalogo no
   puede borrar ni bloquear un pedido ya cobrado.

LA SIEMBRA
----------
La misma migracion carga los diez grupos de carta.json (los `catalogos`) con
sus opciones y precios, y los asigna a los platos que existen en products.
Los datos van EMBEBIDOS como literales de Python y no se leen de ningun
archivo: una migracion que depende de un JSON en disco corre distinto en cada
maquina, y la de produccion tiene que dar exactamente lo mismo que la de
tests.

Los nombres de los grupos son los `corto` de carta.json, desambiguados: en la
web hay dos "Base" y dos "Toppings" distintos (bowl y wrap; hasta 5 y hasta 6),
y un panel con dos filas que dicen lo mismo es un panel en el que el dueno
edita la equivocada.

La asignacion a platos cruza por nombre, sin caja ni tildes, con dos alias
declarados: en Cocina Control los productos se llaman "BBQ PROTEIN BOWL" y
"BOWL CRISPY" mientras que en Rappi (y en carta.json) son "BBQ Protein Salad"
y "Crispy Salad". Un plato que no existe como producto se salta. Las opciones
de "Adicionales" se enlazan a su producto cuando lo hay, por el mismo cruce.

LOS COMBOS
----------
Los tres combos de carta.json (Office, Wrapper, Double) no existen como
productos: seed_sale_products los dejo afuera a proposito porque un combo es
una combinacion de otros productos y registrarlo contaria dos veces el consumo
que el detector de mermas mide. El dueno los quiere igual, porque el asistente
tiene que poder venderlos con sus opciones, asi que esta migracion los crea
ANTES de asignar grupos: is_sale, sin compra, precio de lista de Rappi y
discount_percent 30 — Rappi los vende al -30 % (37.80 / 35.70 / 77.00) y el
dueno quiere cobrar lo mismo. Si el producto ya existe con ese nombre (sin
caja) no se duplica: solo se le pone el 30 % cuando no tiene descuento.

Un producto necesita created_by y la columna es NOT NULL: los combos se
atribuyen al owner mas antiguo de la base (si no hay, al primer admin; si no,
a cualquier usuario). Es una atribucion mas debil que la del seed script, que
pide la contrasena del owner, pero una migracion es codigo que el dueno reviso
y desplego. En una base sin usuarios — solo pasa en tests y en un entorno
recien creado — los combos NO se crean, y la asignacion los salta como a
cualquier plato que no existe.

El downgrade NO borra los combos: son datos, pueden tener pedidos apuntando
(sales_order_items.product_id es RESTRICT) y un producto se apaga, no se
borra. Solo se deshace el esquema que esta migracion creo.

created_by de los grupos es NULL en las filas sembradas: en una base recien
creada la migracion corre antes de que exista el primer usuario, y no hay a
quien atribuirle la carga. Es la unica tabla del repo donde created_by admite
NULL, y significa exactamente "lo cargo la migracion 0023".

Revision ID: 0023_opciones_de_plato
Revises: 0022_precios_descuentos
Create Date: 2026-09-04
"""

import unicodedata
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_opciones_de_plato"
down_revision: str | None = "0022_precios_descuentos"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Datos de siembra: los `catalogos` de carta.json (bonabowl.com, extraido de
# Rappi el 2026-08-18), en el orden en que aparecen ahi. Ese orden es el
# sort_order de los grupos.
#
# Cada grupo: (clave de carta.json, nombre, min, max, [(opcion, precio), ...]).
# Tildes y grafias son las de la carta publica: son las que el cliente lee.
# ---------------------------------------------------------------------------

_TOPPINGS: list[tuple[str, str]] = [
    ("Chucrut de col morada", "0"),
    ("Tomate", "0"),
    ("Zanahoria rallada", "0"),
    ("Pepino", "0"),
    ("Guacamole proteico", "0"),
    ("Choclo dulce", "0"),
    ("Champiñones salteados", "0"),
    ("Espinaca", "0"),
    ("Queso fresco", "0"),
    ("Pickles", "0"),
    ("Cebolla roja", "0"),
]

SEED_GROUPS: list[tuple[str, str, int, int, list[tuple[str, str]]]] = [
    (
        "base-bowl",
        "Base",
        1,
        1,
        [
            ("Camote", "0"),
            ("Quinua", "0"),
            ("Lentejas", "0"),
            ("Frejol negro", "0"),
            ("Lechuga orgánica", "0"),
        ],
    ),
    (
        "base-salad",
        "Bases (elige 2)",
        2,
        2,
        [
            ("Lechuga base", "0"),
            ("Quinua tricolor", "0"),
            ("Espinaca base", "0"),
        ],
    ),
    (
        "base-wrap",
        "Base wrap",
        1,
        1,
        [
            ("Lechuga orgánica", "0"),
            ("Espinaca", "0"),
            ("Quinua", "0"),
        ],
    ),
    ("toppings-5", "Toppings (hasta 5)", 1, 5, list(_TOPPINGS)),
    ("toppings-6", "Toppings (hasta 6)", 1, 6, list(_TOPPINGS)),
    (
        "semilla",
        "Semilla",
        1,
        1,
        [
            ("Ajonjolí", "0"),
            ("Sin semilla", "0"),
        ],
    ),
    (
        "proteina",
        "Proteína",
        1,
        2,
        [
            ("Sin proteína", "0"),
            ("Filete de pollo", "8.00"),
            ("Filete de pollo en salsa BBQ ahumada", "8.00"),
            ("Milanesa", "8.00"),
            ("Tilapia", "8.00"),
        ],
    ),
    (
        "salsa",
        "Salsa",
        1,
        1,
        [
            ("Honey Mustard proteica", "0"),
            ("Mayonesa proteica", "0"),
            ("Salsa de palta proteica", "0"),
            ("Salsa Runch proteica", "0"),
            ("Vinagreta", "0"),
            ("Salsa BBQ", "0"),
        ],
    ),
    (
        "complementos",
        "Adicionales",
        0,
        6,
        [
            ("Maracuyá refrescante 12 oz", "8.00"),
            ("Chucrut púrpura 4 oz", "8.00"),
            ("Mini Camote Burger", "15.00"),
        ],
    ),
    (
        "proteina-extra",
        "Proteína extra",
        1,
        2,
        [
            ("Sin proteína extra", "0"),
            ("200 gr Tilapia a la plancha", "8.00"),
            ("Milanesa", "7.00"),
            ("Filete de pollo", "7.00"),
            ("Filete de pollo en salsa BBQ ahumada", "8.00"),
        ],
    ),
]

# Grupos cuyas opciones se enlazan a un producto del catalogo si existe. Solo
# "Adicionales": una bebida o un chucrut aparte SON productos, y enlazarlos es
# lo que hace que su consumo de insumos salga del pedido.
_GROUPS_LINKED_TO_PRODUCTS = frozenset({"complementos"})

# Cada plato de carta.json con su lista `opciones`, en orden. El orden dentro
# de la lista es el sort_order de la asignacion: es el orden en que la web y
# el asistente le preguntan al cliente.
SEED_DISHES: list[tuple[str, list[str]]] = [
    ("Focus Bowl", ["proteina-extra", "salsa", "complementos"]),
    ("Energy Bowl", ["proteina-extra", "salsa", "complementos"]),
    (
        "Arma tu Bowl",
        ["base-bowl", "toppings-5", "proteina", "proteina-extra", "salsa", "complementos"],
    ),
    ("BBQ Protein Salad", ["proteina-extra", "salsa", "complementos"]),
    ("Crispy Salad", ["proteina-extra", "salsa", "complementos"]),
    (
        "Arma tu Salad",
        [
            "base-salad",
            "toppings-5",
            "semilla",
            "proteina",
            "proteina-extra",
            "salsa",
            "complementos",
        ],
    ),
    ("Wrap Fresh", ["proteina-extra", "salsa", "complementos"]),
    ("Wrap Mediterráneo Verde", ["proteina-extra", "salsa", "complementos"]),
    (
        "Arma tu Wrap",
        ["base-wrap", "toppings-6", "proteina", "proteina-extra", "salsa", "complementos"],
    ),
    # Los combos existen como productos desde esta misma migracion (ver
    # _seed_combos); en una base sin usuarios no se crean y se saltan solos.
    ("Combo Office", ["proteina-extra", "salsa", "complementos"]),
    ("Combo Wrapper", ["proteina-extra", "salsa", "complementos"]),
    ("Combo Double", ["proteina-extra", "salsa", "complementos"]),
]

# Nombre en carta.json -> nombre en products. Documentado en el propio
# carta.json ("NO CUADRA CON COCINA CONTROL"). Se prueban ambos.
_DISH_ALIASES: dict[str, str] = {
    "BBQ Protein Salad": "BBQ Protein Bowl",
    "Crispy Salad": "Bowl Crispy",
}


# Combos a crear como productos: (nombre, precio de lista). Los tres llevan
# discount_percent 30 (ver el docstring del modulo).
SEED_COMBOS: list[tuple[str, str]] = [
    ("COMBO OFFICE", "54.00"),
    ("COMBO WRAPPER", "51.00"),
    ("COMBO DOUBLE", "110.00"),
]
_COMBO_DISCOUNT = "30.00"


def _key(name: str) -> str:
    """Sin tildes, sin caja, sin espacios de mas — igual que seed_sale_products.

    products.name se guarda en mayusculas y sin garantia de tildes ("WRAP
    MEDITERRANEO VERDE"), mientras que carta.json las lleva. Comparar por esta
    llave es lo que hace que un plato cargado a mano se reconozca.
    """
    collapsed = " ".join(name.strip().split()).upper()
    decomposed = unicodedata.normalize("NFKD", collapsed)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _seed_combos(conn: sa.Connection) -> None:
    """Crea los combos como productos de venta, o les pone el descuento.

    Corre antes del cruce por nombre para que la asignacion de grupos los
    encuentre como a cualquier otro plato.
    """
    author = conn.execute(
        sa.text(
            # role::text y no role: 'admin' entro al enum en 0013 y, en una
            # subida de cero, esta migracion corre en la misma transaccion.
            # Postgres no deja usar un valor de enum nuevo sin commit, pero
            # comparar el texto si.
            "SELECT id FROM users "
            "ORDER BY CASE role::text WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, "
            "created_at, id LIMIT 1"
        )
    ).scalar()
    for name, price in SEED_COMBOS:
        existing = conn.execute(
            sa.text(
                "SELECT id, discount_percent FROM products "
                "WHERE lower(name) = lower(:name) AND is_active = true "
                "ORDER BY created_at LIMIT 1"
            ),
            {"name": name},
        ).first()
        if existing is not None:
            if existing.discount_percent is None:
                conn.execute(
                    sa.text(
                        "UPDATE products SET discount_percent = :discount WHERE id = :id"
                    ),
                    {"discount": _COMBO_DISCOUNT, "id": existing.id},
                )
            continue
        if author is None:
            # Sin usuarios no hay a quien atribuir el alta. Ver el docstring.
            continue
        conn.execute(
            sa.text(
                "INSERT INTO products (id, name, unit, is_active, is_purchase, is_sale, "
                "sale_price, discount_percent, created_by) "
                "VALUES (:id, :name, 'un', true, false, true, :price, :discount, :author)"
            ),
            {
                "id": uuid.uuid4(),
                "name": name,
                "price": price,
                "discount": _COMBO_DISCOUNT,
                "author": author,
            },
        )


def _seed(conn: sa.Connection) -> None:
    _seed_combos(conn)
    products = conn.execute(
        sa.text(
            "SELECT id, name FROM products WHERE is_active = true AND is_sale = true"
        )
    ).all()
    product_by_key: dict[str, uuid.UUID] = {}
    for row in products:
        # setdefault: si hubiera dos grafias del mismo nombre, gana la primera.
        product_by_key.setdefault(_key(row.name), row.id)

    def find_product(name: str) -> uuid.UUID | None:
        found = product_by_key.get(_key(name))
        if found is None and name in _DISH_ALIASES:
            found = product_by_key.get(_key(_DISH_ALIASES[name]))
        return found

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
    for position, (key, name, minimum, maximum, items) in enumerate(SEED_GROUPS):
        group_id = uuid.uuid4()
        group_ids[key] = group_id
        conn.execute(
            insert_group,
            {
                "id": group_id,
                "name": name,
                "selection": "single" if maximum == 1 else "multiple",
                "required": minimum >= 1,
                "min_choices": minimum,
                "max_choices": maximum,
                "sort_order": position,
            },
        )
        for item_position, (item_name, price) in enumerate(items):
            product_id = (
                find_product(item_name) if key in _GROUPS_LINKED_TO_PRODUCTS else None
            )
            conn.execute(
                insert_item,
                {
                    "id": uuid.uuid4(),
                    "group_id": group_id,
                    "name": item_name,
                    "price": price,
                    "product_id": product_id,
                    "sort_order": item_position,
                },
            )

    for dish_name, option_keys in SEED_DISHES:
        product_id = find_product(dish_name)
        if product_id is None:
            continue
        for position, key in enumerate(option_keys):
            conn.execute(
                insert_assignment,
                {
                    "product_id": product_id,
                    "group_id": group_ids[key],
                    "sort_order": position,
                },
            )


def upgrade() -> None:
    # --------------------------------------------------------------- grupos
    op.create_table(
        "option_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("selection", sa.String(10), nullable=False),
        sa.Column(
            "required", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "min_choices", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("max_choices", sa.Integer(), nullable=True),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # NULL = sembrado por esta migracion. Ver el docstring del modulo.
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "selection IN ('single', 'multiple')",
            name="ck_option_groups_selection",
        ),
        sa.CheckConstraint("min_choices >= 0", name="ck_option_groups_min_choices"),
        sa.CheckConstraint(
            "max_choices IS NULL OR max_choices >= 1",
            name="ck_option_groups_max_choices",
        ),
    )

    # ------------------------------------------------------------- opciones
    op.create_table(
        "option_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "price", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # CASCADE: una opcion no existe fuera de su grupo. Los pedidos no
        # dependen de la fila (option_item_id es SET NULL), asi que borrar un
        # grupo no puede romper nada cobrado.
        sa.ForeignKeyConstraint(
            ["group_id"], ["option_groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("price >= 0", name="ck_option_items_price_not_negative"),
    )
    op.create_index("ix_option_items_group_id", "option_items", ["group_id"])
    # lower(name) por el mismo motivo que ix_products_name_active_unique: dos
    # "Tilapia" en el mismo grupo son la misma opcion escrita dos veces.
    op.create_index(
        "ix_option_items_group_name_lower_unique",
        "option_items",
        ["group_id", sa.text("lower(name)")],
        unique=True,
    )

    # ---------------------------------------------------------- asignacion
    op.create_table(
        "product_option_groups",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["group_id"], ["option_groups.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("product_id", "group_id"),
    )

    # ------------------------------------------- enlace desde el pedido
    op.add_column(
        "sales_order_item_options",
        sa.Column("option_item_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "sales_order_item_options_option_item_id_fkey",
        "sales_order_item_options",
        "option_items",
        ["option_item_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _seed(op.get_bind())


def downgrade() -> None:
    op.drop_constraint(
        "sales_order_item_options_option_item_id_fkey",
        "sales_order_item_options",
        type_="foreignkey",
    )
    op.drop_column("sales_order_item_options", "option_item_id")

    # Las tres tablas son nuevas: borrarlas se lleva la siembra con ellas. Los
    # combos creados en products se quedan: son datos, no esquema.
    op.drop_table("product_option_groups")
    op.drop_index("ix_option_items_group_name_lower_unique", table_name="option_items")
    op.drop_index("ix_option_items_group_id", table_name="option_items")
    op.drop_table("option_items")
    op.drop_table("option_groups")
