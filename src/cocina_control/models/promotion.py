"""Promocion: un codigo que el servidor convierte en un porcentaje.

El bot de WhatsApp nunca manda importes (ver schemas/sales_order.py). Cuando un
cliente pide "el descuento de primera compra", lo que viaja en el pedido es el
codigo `primera_compra`; este modelo es lo que el servidor consulta para saber
cuanto vale y si aplica. El porcentaje vive aca, editable por el dueno, y no en
el prompt del bot, donde cambiarlo seria un deploy.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base


class Promotion(Base):
    __tablename__ = "promotions"

    __table_args__ = (
        # Mirrors migration 0022. 0 % no descuenta y 100 % regala: ninguna es promo.
        sa.CheckConstraint(
            "percent > 0 AND percent < 100",
            name="ck_promotions_percent_range",
        ),
    )

    code: Mapped[str] = mapped_column(sa.String(40), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    percent: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), nullable=False)
    # Solo el primer pedido del telefono. Lo verifica el servidor contando los
    # pedidos no cancelados del cliente antes de crear el nuevo.
    first_order_only: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
