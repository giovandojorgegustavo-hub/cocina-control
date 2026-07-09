import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import AppendOnlyMixin, TimestampMixin

_DELIVERY_ORDER_STATUS_ENUM = sa.Enum(
    "pending", "completed",
    name="delivery_order_status",
    create_type=True,
)


class DeliveryOrder(Base, TimestampMixin):
    __tablename__ = "delivery_orders"

    __table_args__ = (
        sa.Index("ix_delivery_orders_status", "status"),
        sa.Index("ix_delivery_orders_corrects_id", "corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_delivery_orders_no_self_correction",
        ),
        sa.CheckConstraint(
            "(photo_at IS NULL) = (photo_by IS NULL)",
            name="ck_delivery_orders_photo_parity",
        ),
        sa.CheckConstraint(
            "(completed_at IS NULL) = (completed_by IS NULL)",
            name="ck_delivery_orders_completed_parity",
        ),
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
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class DeliveryOrderItem(Base, AppendOnlyMixin):
    __tablename__ = "delivery_order_items"

    __table_args__ = (
        sa.Index("ix_delivery_order_items_order_id", "delivery_order_id"),
        sa.Index("ix_delivery_order_items_product_id", "product_id"),
        sa.Index("ix_delivery_order_items_corrects_id", "corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_delivery_order_items_no_self_correction",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_delivery_order_items_quantity_positive",
        ),
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
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("delivery_order_items.id", ondelete="RESTRICT"), nullable=True
    )
