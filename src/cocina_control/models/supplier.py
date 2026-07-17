import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin


class Supplier(Base, TimestampMixin):
    """Registro de proveedores (issue #129 — paga la deuda de la decision P1).

    La orden de compra conserva supplier_name como texto (historial inmutable);
    esta tabla es el registro que alimenta el combobox de proveedores.
    """

    __tablename__ = "suppliers"

    __table_args__ = (
        # Unique partial index: only one active supplier can share a name.
        # Mirrors the products pattern (ix_products_name_active_unique).
        sa.Index(
            "ix_suppliers_name_active_unique",
            "name",
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
