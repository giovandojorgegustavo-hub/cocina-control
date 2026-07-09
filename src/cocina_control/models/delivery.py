import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin

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


class DeliveryItem(Base, TimestampMixin):
    __tablename__ = "delivery_items"

    __table_args__ = (
        sa.Index("ix_delivery_items_delivery_id", "delivery_id"),
        sa.Index("ix_delivery_items_product_id", "product_id"),
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
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("delivery_items.id", ondelete="RESTRICT"), nullable=True
    )
