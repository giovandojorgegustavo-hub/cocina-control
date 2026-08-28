"""Pedido de venta: lo que el cliente compro, a cuanto y a donde va.

Se llama sales_order y no order a proposito. delivery_orders ya ocupa el nombre
corto y significa otra cosa — el acto de la cocina, con su foto y su
"completado por" — sin cliente, sin direccion y sin un solo importe. Dos tablas
que suenan igual y guardan cosas distintas es como nacen los bugs que nadie
encuentra hasta que alguien cuadra caja.

Divergencia deliberada del patron append-only del resto del repo: no hay
corrects_id. Un conteo de inventario o un despacho son capturas de un instante y
se corrigen escribiendo una captura nueva. Un pedido no: es una entidad con
ciclo de vida que avanza y puede cancelarse, y su historia vive en status.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin

_SALES_ORDER_CHANNEL_ENUM = sa.Enum(
    "whatsapp", "web", "rappi", "pedidosya", "phone",
    name="sales_order_channel",
    create_type=True,
)

_SALES_ORDER_STATUS_ENUM = sa.Enum(
    "draft", "confirmed", "in_kitchen", "dispatched", "delivered", "cancelled",
    name="sales_order_status",
    create_type=True,
)


class SalesOrder(Base, TimestampMixin):
    __tablename__ = "sales_orders"

    __table_args__ = (
        sa.Index("ix_sales_orders_status", "status"),
        sa.Index("ix_sales_orders_customer_id", "customer_id"),
        sa.Index("ix_sales_orders_created_at", "created_at"),
        sa.Index("ix_sales_orders_delivery_trip_id", "delivery_trip_id"),
        sa.CheckConstraint("items_total >= 0", name="ck_sales_orders_items_total_ok"),
        sa.CheckConstraint("delivery_fee >= 0", name="ck_sales_orders_fee_ok"),
        # El total no es un campo libre: es la suma, y la base lo verifica.
        sa.CheckConstraint(
            "total = items_total + delivery_fee",
            name="ck_sales_orders_total_is_sum",
        ),
        sa.CheckConstraint(
            "(cancelled_at IS NULL) = (cancelled_by IS NULL)",
            name="ck_sales_orders_cancelled_parity",
        ),
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

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    address_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("customer_addresses.id", ondelete="RESTRICT"), nullable=True
    )
    channel: Mapped[str] = mapped_column(_SALES_ORDER_CHANNEL_ENUM, nullable=False)
    status: Mapped[str] = mapped_column(
        _SALES_ORDER_STATUS_ENUM, nullable=False, default="draft"
    )
    items_total: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Viaje de inDrive en el que salio. NULL mientras no se despacho. Varios
    # pedidos pueden compartir viaje: pasa poco, pero pasa.
    delivery_trip_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("delivery_trips.id", ondelete="RESTRICT"), nullable=True
    )
    # Id de conversacion del gateway. Sin esto, un pedido raro no se puede
    # rastrear hasta el chat que lo origino, que es el unico lugar donde esta lo
    # que el cliente realmente dijo.
    conversation_ref: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    cancelled_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class SalesOrderItem(Base, TimestampMixin):
    __tablename__ = "sales_order_items"

    __table_args__ = (
        sa.Index("ix_sales_order_items_order_id", "sales_order_id"),
        sa.Index("ix_sales_order_items_product_id", "product_id"),
        sa.CheckConstraint(
            "quantity > 0", name="ck_sales_order_items_quantity_positive"
        ),
        sa.CheckConstraint("unit_price >= 0", name="ck_sales_order_items_price_ok"),
        sa.CheckConstraint("line_total >= 0", name="ck_sales_order_items_line_total_ok"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    sales_order_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # Congelado al crear el pedido. No se lee del catalogo al mostrar un pedido
    # viejo: si manana sube el Focus Bowl, lo cobrado ayer tiene que seguir
    # diciendo lo que se cobro.
    unit_price: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class SalesOrderItemOption(Base, TimestampMixin):
    """Modificador de una linea: crema, proteina extra, "sin palta".

    Una bebida NO va aca: es un producto que se vende solo, y por lo tanto una
    linea propia. La distincion importa para el consumo de insumos — la crema
    del bowl no se pidio aparte, salio con el bowl.
    """

    __tablename__ = "sales_order_item_options"

    __table_args__ = (
        sa.Index("ix_sales_order_item_options_item_id", "order_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("sales_order_items.id", ondelete="RESTRICT"), nullable=False
    )
    # NULL cuando la opcion no es un producto del catalogo ("sin palta", "poco
    # picante"). Una preferencia no consume insumo y no deberia obligar a
    # inventar una fila en products solo para poder anotarla.
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=True
    )
    option_group: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # Se guarda el texto ademas del product_id porque el nombre que el cliente
    # eligio tiene que sobrevivir a que alguien renombre o desactive el producto.
    # Mismo motivo que congelar unit_price.
    option_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    price_delta: Mapped[Decimal] = mapped_column(
        sa.Numeric(10, 2), nullable=False, default=0
    )
