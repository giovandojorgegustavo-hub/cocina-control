"""composicion de platos: receta plantilla e ingredientes por pedido

El catalogo tiene dos islas sin puente: los insumos que entran por ordenes de
compra (is_purchase) y los platos que salen en pedidos (is_sale). Ninguna fila
dice que se lleva un FOCUS BOWL, asi que vender 12 no permite deducir cuanta
tilapia salio. El detector de fuga que motivo el catalogo de venta no puede
restar consumo esperado contra inventario real mientras falte ese puente.

Son dos tablas y no una porque Bonabowl vende dos clases de plato:

- Los fijos (FOCUS BOWL, WRAP FRESH) tienen receta constante. Se declara una
  vez en product_recipe y se multiplica por lo vendido.
- Los armables (ARMA TU BOWL, ARMA TU SALAD) los compone el cliente en el
  momento. No existe plantilla que declarar: la unica verdad es lo que dice el
  ticket de ese pedido, y va en delivery_order_item_ingredients.

quantity es NULL-able a proposito en ambas. Hoy nadie en la cocina sabe los
gramos exactos, e inventar un numero produciria un consumo esperado falso que
nadie volveria a cuestionar. Primero se captura QUE lleva cada plato; las
cantidades se completan cuando el registro acumulado las haga evidentes. Un
ingrediente sin cantidad ya sirve para contar frecuencia y para saber que
insumo toca cada plato.

status distingue el ingrediente que efectivamente salio del que se pidio y no
habia. Sin esa marca, un bowl servido sin palta porque se acabo es
indistinguible de un bowl que nunca la llevaba, y la compra pierde la unica
senal temprana de quiebre de stock que la cocina genera sola.

Que esta tabla NO resuelve, y queda para la capa de servicio: que product_id
apunte a un producto is_sale y ingredient_id a uno is_purchase. Postgres no
puede expresar esa condicion en un CHECK porque vive en otra fila; se valida
donde ya se valida el resto del catalogo (_validate_products en la API).

Revision ID: 0018_composicion_platos
Revises: 0017_service_principals
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_composicion_platos"
down_revision: str | None = "0017_service_principals"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------------- receta
    op.create_table(
        "product_recipe",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("ingredient_id", sa.Uuid(), nullable=False),
        # NULL = todavia no medido. Ver el docstring del modulo.
        sa.Column("quantity", sa.Numeric(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Misma pareja de columnas de auditoria que products: la receta se
        # corrige en el tiempo y hay que saber quien la toco.
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "product_id <> ingredient_id",
            name="ck_product_recipe_no_self_reference",
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_product_recipe_quantity_positive",
        ),
    )
    # Un insumo aparece una sola vez por receta. Dos filas de PALTA en el mismo
    # plato no son un caso valido: son una edicion que se guardo dos veces, y
    # duplicarian el consumo esperado sin que nada lo delate.
    op.create_index(
        "ix_product_recipe_product_ingredient_unique",
        "product_recipe",
        ["product_id", "ingredient_id"],
        unique=True,
    )
    op.create_index("ix_product_recipe_ingredient_id", "product_recipe", ["ingredient_id"])

    # ------------------------------------------- ingredientes de cada pedido
    op.create_table(
        "delivery_order_item_ingredients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("delivery_order_item_id", sa.Uuid(), nullable=False),
        sa.Column("ingredient_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "included",
                "out_of_stock",
                name="delivery_order_ingredient_status",
            ),
            nullable=False,
            server_default=sa.text("'included'"),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["delivery_order_item_id"],
            ["delivery_order_items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["ingredient_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="ck_doi_ingredients_quantity_positive",
        ),
        # Lo que no salio no consumio nada. Permitir cantidad en un ingrediente
        # agotado dejaria entrar consumo fantasma en la resta contra inventario.
        sa.CheckConstraint(
            "status <> 'out_of_stock' OR quantity IS NULL",
            name="ck_doi_ingredients_out_of_stock_has_no_quantity",
        ),
    )
    # Sin corrects_id, a diferencia del resto de tablas append-only: un
    # ingrediente mal cargado se corrige corrigiendo la linea de pedido
    # completa, que es la unidad que el operario ve y entiende.
    op.create_index(
        "ix_doi_ingredients_item_ingredient_unique",
        "delivery_order_item_ingredients",
        ["delivery_order_item_id", "ingredient_id"],
        unique=True,
    )
    op.create_index(
        "ix_doi_ingredients_ingredient_id",
        "delivery_order_item_ingredients",
        ["ingredient_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_doi_ingredients_ingredient_id",
        table_name="delivery_order_item_ingredients",
    )
    op.drop_index(
        "ix_doi_ingredients_item_ingredient_unique",
        table_name="delivery_order_item_ingredients",
    )
    op.drop_table("delivery_order_item_ingredients")
    sa.Enum(name="delivery_order_ingredient_status").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_product_recipe_ingredient_id", table_name="product_recipe")
    op.drop_index("ix_product_recipe_product_ingredient_unique", table_name="product_recipe")
    op.drop_table("product_recipe")
