import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import AppendOnlyMixin, TimestampMixin

# Re-export for convenience in API layer.
__all__ = ["Delivery", "DeliveryItem"]

_DELIVERY_STATUS_ENUM = sa.Enum(
    "no_leida", "en_verificacion", "validada",
    name="delivery_status",
    create_type=True,
)


class Delivery(Base, TimestampMixin):
    __tablename__ = "deliveries"

    __table_args__ = (
        sa.Index("ix_deliveries_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    supplier_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        _DELIVERY_STATUS_ENUM, nullable=False, default="no_leida"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    validated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    validated_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class DeliveryItem(Base, AppendOnlyMixin):
    __tablename__ = "delivery_items"

    __table_args__ = (
        sa.Index("ix_delivery_items_delivery_id", "delivery_id"),
        sa.Index("ix_delivery_items_product_id", "product_id"),
        sa.Index("ix_delivery_items_corrects_id", "corrects_id"),
        # Prevent chain bifurcation: each item can be corrected at most once.
        # If two concurrent corrections race past the leaf check, the second
        # INSERT will fail here with IntegrityError (uq_delivery_items_corrects_id).
        sa.UniqueConstraint("corrects_id", name="uq_delivery_items_corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_delivery_items_no_self_correction",
        ),
        sa.CheckConstraint(
            "announced_qty > 0",
            name="ck_delivery_items_announced_qty_positive",
        ),
        sa.CheckConstraint(
            "received_qty IS NULL OR received_qty >= 0",
            name="ck_delivery_items_received_qty_nonneg",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("deliveries.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    announced_qty: Mapped[Decimal] = mapped_column(sa.Numeric, nullable=False)
    received_qty: Mapped[Decimal | None] = mapped_column(sa.Numeric, nullable=True)
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("delivery_items.id", ondelete="RESTRICT"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Audit: who confirmed this item and when.  Set by confirm_item(); NULL on
    # pre-load rows and on correction rows (those are created_by, not confirmed).
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
