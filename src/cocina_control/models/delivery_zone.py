"""Tarifa de reparto por distrito.

Por distrito y no por distancia, y no es una simplificacion perezosa: el
asistente de WhatsApp no puede medir kilometros en una conversacion. Lo unico
que el cliente escribe es el nombre de un distrito, asi que esa es la unica
llave con la que se puede cotizar sin preguntarle una direccion exacta antes de
saber si siquiera hay cobertura.

Un distrito sin fila es un distrito sin cobertura. No hace falta una columna
"cubierto": la ausencia ya lo dice, y una tarifa nula seria un tercer estado que
alguien tendria que recordar interpretar.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin


class DeliveryZone(Base, TimestampMixin):
    __tablename__ = "delivery_zones"

    __table_args__ = (
        # lower() por el mismo motivo que ix_users_email_lower: el cliente
        # escribe "magdalena", "Magdalena" y "MAGDALENA DEL MAR", y las tres
        # tienen que resolver a la misma tarifa.
        sa.Index(
            "ix_delivery_zones_district_lower_unique",
            sa.text("lower(district)"),
            unique=True,
        ),
        sa.CheckConstraint("fee >= 0", name="ck_delivery_zones_fee_not_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    district: Mapped[str] = mapped_column(sa.Text, nullable=False)
    fee: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2), nullable=False)
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
