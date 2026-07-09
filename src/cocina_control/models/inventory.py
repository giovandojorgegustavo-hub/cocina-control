import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import AppendOnlyMixin, TimestampMixin

_INVENTORY_COUNT_STATUS_ENUM = sa.Enum(
    "in_progress", "completed",
    name="inventory_count_status",
    create_type=True,
)


class InventoryCount(Base, TimestampMixin):
    __tablename__ = "inventory_counts"

    __table_args__ = (
        sa.Index("ix_inventory_counts_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(
        _INVENTORY_COUNT_STATUS_ENUM, nullable=False, default="in_progress"
    )
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    started_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Audit: who last mutated this count session (complete, correction in session).
    # NULL until the first mutation after creation.
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class InventoryCountItem(Base, AppendOnlyMixin):
    __tablename__ = "inventory_count_items"

    __table_args__ = (
        sa.Index("ix_inventory_count_items_count_id", "inventory_count_id"),
        sa.Index("ix_inventory_count_items_product_id", "product_id"),
        sa.Index("ix_inventory_count_items_corrects_id", "corrects_id"),
        # Prevent chain bifurcation: each item can be corrected at most once.
        # If two concurrent corrections race past the leaf check, the second
        # INSERT will fail here with IntegrityError (uq_inventory_count_items_corrects_id).
        sa.UniqueConstraint("corrects_id", name="uq_inventory_count_items_corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_inventory_count_items_no_self_correction",
        ),
        sa.CheckConstraint(
            "quantity >= 0",
            name="ck_inventory_count_items_quantity_nonneg",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    inventory_count_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("inventory_counts.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric, nullable=False)
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("inventory_count_items.id", ondelete="RESTRICT"), nullable=True
    )
    # Optional explanation for corrections.  NULL on original items.
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
