import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin

_UNIT_ENUM = sa.Enum("kg", "un", "lt", name="product_unit", create_type=True)


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    __table_args__ = (
        # Unique partial index: only one active product can share a name.
        # Mirrors the index created by migration 0002_products_name_unique_active.
        sa.Index(
            "ix_products_name_active_unique",
            "name",
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        ),
        sa.CheckConstraint(
            "low_stock_threshold IS NULL OR low_stock_threshold > 0",
            name="ck_products_low_stock_threshold_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    unit: Mapped[str] = mapped_column(_UNIT_ENUM, nullable=False)
    low_stock_threshold: Mapped[Decimal | None] = mapped_column(
        sa.Numeric, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Audit columns: set on every PATCH and soft-DELETE.
    # nullable because products created before this migration have no mutation history.
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
