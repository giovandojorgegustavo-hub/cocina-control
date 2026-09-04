"""Opciones de plato: grupos, opciones con precio y su asignacion por plato.

Hasta la migracion 0023 la unica forma de que una opcion de pedido tuviera
precio era ser un producto del catalogo, y ninguna tabla decia que opciones
admite cada plato. Estas tres tablas son esa lista: la edita el dueno desde el
panel, y el asistente de WhatsApp y la carta web la LEEN. Un solo lugar, para
que "Filete de pollo +S/ 8" diga lo mismo en todos lados.

Un pedido no apunta a estas filas para cobrar: cuando se crea, el nombre del
grupo, el de la opcion y el precio se copian a sales_order_item_options y
quedan congelados, igual que unit_price. option_item_id es un enlace hacia
atras para saber que se pidio, no una dependencia.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin

SELECTION_SINGLE = "single"
SELECTION_MULTIPLE = "multiple"


class OptionGroup(Base, TimestampMixin):
    """Un grupo de opciones: "Base", "Toppings (hasta 5)", "Proteína extra".

    required y min_choices se guardan los dos aunque se impliquen: required es
    lo que el panel muestra, min_choices lo que el servidor cuenta. La API
    garantiza que un grupo obligatorio tenga min_choices >= 1 y que un grupo
    'single' tenga max_choices = 1; el CHECK de la base se queda en lo simple.
    """

    __tablename__ = "option_groups"

    __table_args__ = (
        sa.CheckConstraint(
            "selection IN ('single', 'multiple')", name="ck_option_groups_selection"
        ),
        sa.CheckConstraint("min_choices >= 0", name="ck_option_groups_min_choices"),
        sa.CheckConstraint(
            "max_choices IS NULL OR max_choices >= 1", name="ck_option_groups_max_choices"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    selection: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    required: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    min_choices: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    max_choices: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    # NULL solo en las filas que sembro la migracion 0023: corre antes de que
    # exista el primer usuario y no hay a quien atribuirle la carga.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class OptionItem(Base, TimestampMixin):
    """Una opcion dentro de un grupo, con el precio que suma al plato.

    price 0 es "incluido". product_id enlaza la opcion con un producto del
    catalogo cuando la opcion ES ese producto (una bebida, el chucrut aparte),
    para que el consumo de insumos salga del pedido; pero lo que se cobra es
    price, no el precio del producto. Lo que cuesta un adicional dentro de un
    bowl lo decide el grupo.
    """

    __tablename__ = "option_items"

    __table_args__ = (
        sa.Index("ix_option_items_group_id", "group_id"),
        # Dos "Tilapia" en el mismo grupo son la misma opcion escrita dos veces.
        sa.Index(
            "ix_option_items_group_name_lower_unique",
            "group_id",
            sa.text("lower(name)"),
            unique=True,
        ),
        sa.CheckConstraint("price >= 0", name="ck_option_items_price_not_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("option_groups.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    price: Mapped[Decimal] = mapped_column(
        sa.Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)


class ProductOptionGroup(Base):
    """Que grupos admite cada plato, y en que orden se le preguntan al cliente."""

    __tablename__ = "product_option_groups"

    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("option_groups.id", ondelete="CASCADE"), primary_key=True
    )
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
