"""pedidos de venta: cliente, direccion, zona de reparto, pedido, opciones y pagos

Cocina Control sabe que se despacho pero no sabe que se vendio. delivery_orders
registra el acto de la cocina (foto, quien completo, a que plataforma salio) y no
tiene cliente, ni direccion, ni un solo importe: la consulta a information_schema
por cualquier columna de precio devuelve vacio en toda la base. Un pedido tomado
por WhatsApp necesita las dos mitades, y hoy solo existe la de la cocina.

Se llama sales_orders y no orders a proposito. delivery_orders ya ocupa el
nombre corto y significa otra cosa; dos tablas que suenan igual y guardan cosas
distintas es como nacen los bugs que nadie encuentra. sales_orders es la venta,
delivery_orders es el despacho, y un dia se van a enlazar.

Divergencia deliberada del patron append-only del resto del repo: estas tablas no
llevan corrects_id. Un conteo de inventario o un despacho son capturas de un
instante, y corregirlos significa escribir una captura nueva que apunta a la
vieja. Un pedido no: es una entidad con ciclo de vida que avanza de draft a
delivered y puede cancelarse. Su historia vive en status, no en una cadena de
correcciones.

unit_price se congela en la linea del pedido. No se lee del catalogo al mostrar
un pedido viejo: si manana sube el Focus Bowl, lo cobrado ayer tiene que seguir
diciendo lo que se cobro. Un pedido cuyo importe cambia solo no sirve para
contabilidad, y el error es invisible hasta que alguien cuadra caja.

products.sale_price entra NULL-able y no puede ser de otra forma: los insumos
(is_purchase) no tienen precio de venta, y los 20 productos is_sale que ya
existen no tienen ninguno cargado. Un NOT NULL reventaria la migracion contra la
base de produccion. La regla "una linea de pedido exige producto con precio" vive
en la capa de servicio, donde ya vive el resto de la validacion del catalogo.

Las opciones (cremas, proteina extra) son modificadores de una linea y no lineas
propias. Una bebida si es linea propia porque es un producto que se vende solo.
La distincion importa para el consumo de insumos: la crema del bowl no se pidio
aparte, salio con el bowl.

payments es tabla aparte y no columnas en sales_orders porque un pedido puede
pagarse en dos actos — la mitad por Yape y el resto en efectivo al recibir.

El CHECK que sostiene todo el diseno de seguridad es
ck_payments_verified_needs_human. El asistente de WhatsApp puede REGISTRAR un
pago y su foto; no puede darlo por verificado. Esa regla no se deja en la capa de
servicio, donde se olvida en el proximo refactor: vive en la base, y Postgres
rechaza la fila aunque alguien escriba SQL a mano a las 2 de la manana. Un token
del asistente filtrado puede ensuciar la bandeja con pedidos falsos; nunca puede
darse por pagado a si mismo.

Revision ID: 0019_pedidos_venta
Revises: 0018_composicion_platos
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_pedidos_venta"
down_revision: str | None = "0018_composicion_platos"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------------------- cliente
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        # El + no es cosmetico. Meta rechaza con (#131009) todo destinatario sin
        # prefijo internacional, y ese error explica la mayoria de los envios
        # fallidos historicos del gateway. Si el telefono entra mal aca, el
        # cliente nunca recibe la confirmacion de su propio pedido.
        sa.CheckConstraint(
            r"phone ~ '^\+[0-9]{8,15}$'",
            name="ck_customers_phone_e164",
        ),
    )
    # El telefono ES la cuenta: se descarto el login justamente porque el numero
    # ya identifica a la persona en el canal donde compra.
    op.create_index("ix_customers_phone_unique", "customers", ["phone"], unique=True)

    # ------------------------------------------------------------- direccion
    op.create_table(
        "customer_addresses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("district", sa.Text(), nullable=False),
        sa.Column("address_line", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_customer_addresses_customer_id", "customer_addresses", ["customer_id"]
    )
    # Una sola direccion por defecto por cliente. Dos convierten "a donde se lo
    # mando" en una moneda al aire.
    op.create_index(
        "ix_customer_addresses_one_default",
        "customer_addresses",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    # ------------------------------------------------------ zona de reparto
    # Por DISTRITO y no por kilometros, y no es una simplificacion: el asistente
    # no puede medir distancia en una conversacion de WhatsApp. Lo unico que el
    # cliente escribe es el nombre de un distrito. Una tarifa por sub-zona
    # ("la parte este de San Miguel") seria irresoluble en el chat y terminaria
    # en discusion con el cliente. Un distrito al que no se llega simplemente no
    # tiene fila, y el asistente responde que no hay cobertura.
    op.create_table(
        "delivery_zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("district", sa.Text(), nullable=False),
        sa.Column("fee", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("fee >= 0", name="ck_delivery_zones_fee_not_negative"),
    )
    # lower() por la misma razon que ix_users_email_lower: el cliente escribe
    # "magdalena", "Magdalena" y "MAGDALENA DEL MAR" y las tres son el distrito.
    op.create_index(
        "ix_delivery_zones_district_lower_unique",
        "delivery_zones",
        [sa.text("lower(district)")],
        unique=True,
    )

    # ---------------------------------------------------------------- pedido
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("address_id", sa.Uuid(), nullable=True),
        sa.Column(
            "channel",
            sa.Enum(
                "whatsapp",
                "web",
                "rappi",
                "pedidosya",
                "phone",
                name="sales_order_channel",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "confirmed",
                "in_kitchen",
                "dispatched",
                "delivered",
                "cancelled",
                name="sales_order_status",
            ),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("items_total", sa.Numeric(10, 2), nullable=False),
        sa.Column("delivery_fee", sa.Numeric(10, 2), nullable=False),
        sa.Column("total", sa.Numeric(10, 2), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # Id de conversacion del gateway de WhatsApp. Sin esto, un pedido raro no
        # se puede rastrear hasta el chat que lo origino, que es el unico lugar
        # donde esta lo que el cliente realmente dijo.
        sa.Column("conversation_ref", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Uuid(), nullable=True),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["address_id"], ["customer_addresses.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("items_total >= 0", name="ck_sales_orders_items_total_ok"),
        sa.CheckConstraint("delivery_fee >= 0", name="ck_sales_orders_fee_ok"),
        # El total no es un campo libre: es la suma, y la base lo verifica. Un
        # total que no cuadra con sus partes es un pedido que nadie va a poder
        # cuadrar despues contra la caja.
        sa.CheckConstraint(
            "total = items_total + delivery_fee",
            name="ck_sales_orders_total_is_sum",
        ),
        sa.CheckConstraint(
            "(cancelled_at IS NULL) = (cancelled_by IS NULL)",
            name="ck_sales_orders_cancelled_parity",
        ),
        # Cancelar sin decir por que deja un agujero justo donde hace falta
        # entender la perdida.
        sa.CheckConstraint(
            "status <> 'cancelled' OR cancelled_reason IS NOT NULL",
            name="ck_sales_orders_cancelled_needs_reason",
        ),
        # Un pedido que sale de borrador ya se le prometio a alguien: tiene que
        # saber a donde va.
        sa.CheckConstraint(
            "status = 'draft' OR status = 'cancelled' OR address_id IS NOT NULL",
            name="ck_sales_orders_confirmed_needs_address",
        ),
    )
    op.create_index("ix_sales_orders_status", "sales_orders", ["status"])
    op.create_index("ix_sales_orders_customer_id", "sales_orders", ["customer_id"])
    op.create_index("ix_sales_orders_created_at", "sales_orders", ["created_at"])

    # ------------------------------------------------------ linea del pedido
    op.create_table(
        "sales_order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        # Congelado al crear. Ver el docstring del modulo.
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(10, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["sales_order_id"], ["sales_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity > 0", name="ck_sales_order_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_sales_order_items_price_ok"),
        sa.CheckConstraint("line_total >= 0", name="ck_sales_order_items_line_total_ok"),
    )
    op.create_index(
        "ix_sales_order_items_order_id", "sales_order_items", ["sales_order_id"]
    )
    op.create_index("ix_sales_order_items_product_id", "sales_order_items", ["product_id"])

    # -------------------------------------------- opciones (cremas, extras)
    # option_name se guarda como texto ademas del product_id porque el nombre
    # que el cliente eligio tiene que sobrevivir a que alguien renombre o
    # desactive el producto. Es el mismo motivo por el que unit_price se congela.
    op.create_table(
        "sales_order_item_options",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        # NULL cuando la opcion no es un producto del catalogo ("sin palta",
        # "poco picante"). Una preferencia no consume insumo y no deberia
        # inventarse una fila en products para poder anotarla.
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("option_group", sa.Text(), nullable=False),
        sa.Column("option_name", sa.Text(), nullable=False),
        sa.Column(
            "price_delta",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"], ["sales_order_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sales_order_item_options_item_id",
        "sales_order_item_options",
        ["order_item_id"],
    )

    # ----------------------------------------------------------------- pagos
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column(
            "method",
            sa.Enum(
                "yape",
                "plin",
                "cash",
                "bank_transfer",
                "card",
                name="payment_method",
            ),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "verified", "rejected", name="payment_status"),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        # Foto del comprobante (Yape/Plin). El asistente la registra; leerla es
        # otro acto y firmarla es otro mas.
        sa.Column("proof_url", sa.Text(), nullable=True),
        sa.Column("proof_at", sa.DateTime(timezone=True), nullable=True),
        # Lo que el OCR creyo leer, crudo. Se guarda como propuesta, nunca como
        # veredicto: el mismo patron que el ERP ya usa para los comprobantes,
        # donde un OCR ilegible manda la orden a cola humana en vez de aprobarla.
        sa.Column("ocr_raw", sa.JSON(), nullable=True),
        sa.Column("ocr_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["sales_order_id"], ["sales_orders.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "(verified_at IS NULL) = (verified_by IS NULL)",
            name="ck_payments_verified_parity",
        ),
        # EL CHECK QUE SOSTIENE EL DISENO DE SEGURIDAD.
        # Un pago verificado exige un humano que lo firme. verified_by apunta a
        # users, y el endpoint que lo escribe exige JWT de persona con rol owner
        # — nunca un service token. Aunque manana alguien afloje la validacion en
        # la capa de servicio, o escriba SQL a mano, Postgres rechaza la fila.
        sa.CheckConstraint(
            "status <> 'verified' OR verified_by IS NOT NULL",
            name="ck_payments_verified_needs_human",
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR rejected_reason IS NOT NULL",
            name="ck_payments_rejected_needs_reason",
        ),
        sa.CheckConstraint(
            "(proof_at IS NULL) = (proof_url IS NULL)",
            name="ck_payments_proof_parity",
        ),
    )
    op.create_index("ix_payments_sales_order_id", "payments", ["sales_order_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    # ------------------------------------------------- precio de venta
    op.add_column(
        "products",
        sa.Column("sale_price", sa.Numeric(10, 2), nullable=True),
    )
    op.create_check_constraint(
        "ck_products_sale_price_not_negative",
        "products",
        "sale_price IS NULL OR sale_price >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_sale_price_not_negative", "products", type_="check")
    op.drop_column("products", "sale_price")

    op.drop_table("payments")
    op.drop_table("sales_order_item_options")
    op.drop_table("sales_order_items")
    op.drop_table("sales_orders")
    op.drop_table("delivery_zones")
    op.drop_table("customer_addresses")
    op.drop_table("customers")

    # Los enums declarados inline en create_table no se van con drop_table.
    bind = op.get_bind()
    for enum_name in (
        "payment_status",
        "payment_method",
        "sales_order_status",
        "sales_order_channel",
    ):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
