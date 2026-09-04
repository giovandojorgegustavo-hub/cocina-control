"""precios y descuentos: descuento por plato, promociones y descuento del pedido

Los precios de la carta se copiaron de Rappi cuando se armo el canal de
WhatsApp. En Rappi el precio de lista trae un descuento encima, pero ese
descuento lo pone Rappi y lo paga Rappi: no es nuestro. Al copiar solo el
numero, la carta de WhatsApp quedo con precios de lista y sin ninguna forma de
bajarlos. El asistente no podia ofrecer el 15 % de primera compra que se
promete en redes, y el dueno no podia tocar un precio sin pedirle a alguien que
edite la base a mano.

Se agregan tres cosas, y las tres viven en la base y no en el bot:

1. products.discount_percent — descuento por plato. NULL o 0 es "sin
   descuento". El precio final se calcula en el servidor:
   sale_price * (1 - discount_percent / 100), redondeado a centavos. El CHECK
   permite [0, 100): un descuento del 100 % es un regalo y se carga como
   precio 0, no como descuento.

2. promotions — un codigo con un porcentaje. La unica promo que existe hoy es
   `primera_compra` (15 %, solo primer pedido) y se siembra aca para que el
   asistente la encuentre desde el primer deploy. first_order_only la sostiene
   el servidor contando los pedidos no cancelados del mismo telefono.

3. sales_orders.discount_percent / discount_amount / promo_code — lo que se
   desconto en ESE pedido, congelado igual que unit_price. Si manana la promo
   baja al 10 %, lo cobrado ayer tiene que seguir diciendo 15.

POR QUE VIAJA UN CODIGO Y NO UN IMPORTE
---------------------------------------
La regla de sales_orders sigue intacta: el cliente NUNCA manda importes. Un
descuento tampoco. Si el bot pudiera mandar discount_amount, un token filtrado
crearia pedidos de S/ 1 con todos los CHECK cuadrando. Lo que viaja es
promo_code, un texto que el servidor valida contra promotions y convierte en
importe. El bot no decide cuanto se descuenta; solo dice que el cliente pidio
el descuento.

EL CHECK DEL TOTAL CAMBIA
-------------------------
ck_sales_orders_total_is_sum pasa de `total = items_total + delivery_fee` a
`total = items_total - discount_amount + delivery_fee`. Se agrega
ck_sales_orders_discount_ok para que el descuento no pueda ser negativo ni
mayor que los items: un descuento mayor que el pedido es un error de cuenta, no
una promo. Las filas existentes tienen discount_amount 0, asi que el CHECK
nuevo las acepta y el downgrade puede volver al original sin tocar datos.

Revision ID: 0022_precios_descuentos
Revises: 0021_viajes_reparto
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_precios_descuentos"
down_revision: str | None = "0021_viajes_reparto"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------- descuento por plato
    op.add_column(
        "products",
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=True),
    )
    op.create_check_constraint(
        "ck_products_discount_percent_range",
        "products",
        "discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent < 100)",
    )

    # ------------------------------------------------------------ promociones
    op.create_table(
        "promotions",
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("percent", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "first_order_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("code"),
        # Una promo del 0 % no descuenta nada y una del 100 % regala el pedido:
        # ninguna de las dos es una promocion, y cargarlas seria un error.
        sa.CheckConstraint(
            "percent > 0 AND percent < 100",
            name="ck_promotions_percent_range",
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO promotions (code, name, percent, first_order_only, is_active) "
            "VALUES ('primera_compra', 'Descuento de primera compra', 15.00, true, true)"
        )
    )

    # ------------------------------------------------- descuento del pedido
    op.add_column(
        "sales_orders",
        sa.Column(
            "discount_percent",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "sales_orders",
        sa.Column(
            "discount_amount",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "sales_orders",
        sa.Column("promo_code", sa.String(40), nullable=True),
    )
    op.create_foreign_key(
        "sales_orders_promo_code_fkey",
        "sales_orders",
        "promotions",
        ["promo_code"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("ck_sales_orders_total_is_sum", "sales_orders", type_="check")
    op.create_check_constraint(
        "ck_sales_orders_total_is_sum",
        "sales_orders",
        "total = items_total - discount_amount + delivery_fee",
    )
    op.create_check_constraint(
        "ck_sales_orders_discount_ok",
        "sales_orders",
        "discount_amount >= 0 AND discount_amount <= items_total",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sales_orders_discount_ok", "sales_orders", type_="check")
    op.drop_constraint("ck_sales_orders_total_is_sum", "sales_orders", type_="check")
    op.create_check_constraint(
        "ck_sales_orders_total_is_sum",
        "sales_orders",
        "total = items_total + delivery_fee",
    )
    op.drop_constraint("sales_orders_promo_code_fkey", "sales_orders", type_="foreignkey")
    op.drop_column("sales_orders", "promo_code")
    op.drop_column("sales_orders", "discount_amount")
    op.drop_column("sales_orders", "discount_percent")

    op.drop_table("promotions")

    op.drop_constraint("ck_products_discount_percent_range", "products", type_="check")
    op.drop_column("products", "discount_percent")
