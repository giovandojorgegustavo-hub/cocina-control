import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin

_DELIVERY_ORDER_STATUS_ENUM = sa.Enum(
    "pending", "completed",
    name="delivery_order_status",
    create_type=True,
)


class DeliveryOrder(Base, TimestampMixin):
    __tablename__ = "delivery_orders"

    __table_args__ = (
        sa.Index("ix_delivery_orders_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(
        _DELIVERY_ORDER_STATUS_ENUM, nullable=False, default="pending"
    )
    photo_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    photo_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    photo_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    platform: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("delivery_orders.id", ondelete="RESTRICT"), nullable=True
    )


class DeliveryOrderItem(Base, TimestampMixin):
    __tablename__ = "delivery_order_items"

    __table_args__ = (
        sa.Index("ix_delivery_order_items_order_id", "delivery_order_id"),
        sa.Index("ix_delivery_order_items_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    delivery_order_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("delivery_orders.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("delivery_order_items.id", ondelete="RESTRICT"), nullable=True
    )
