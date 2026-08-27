"""Cliente y sus direcciones de entrega.

El telefono ES la cuenta. Se descarto el login con usuario y contrasena porque
el numero ya identifica a la persona en el canal donde compra: fabricar una
identidad paralela habria dejado dos nociones de "quien es este" que se separan
sola la primera vez que alguien cambia de correo.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    __table_args__ = (
        sa.Index("ix_customers_phone_unique", "phone", unique=True),
        # El + no es cosmetico: Meta rechaza con (#131009) todo destinatario sin
        # prefijo internacional. Un telefono mal guardado aca no rompe nada
        # visible al crear el pedido — rompe la confirmacion que el cliente
        # nunca recibe, que es mucho mas dificil de notar.
        sa.CheckConstraint(
            r"phone ~ '^\+[0-9]{8,15}$'",
            name="ck_customers_phone_e164",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(sa.Text, nullable=False)
    name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class CustomerAddress(Base, TimestampMixin):
    __tablename__ = "customer_addresses"

    __table_args__ = (
        sa.Index("ix_customer_addresses_customer_id", "customer_id"),
        # Una sola direccion por defecto por cliente. Dos convierten "a donde se
        # lo mando" en una moneda al aire, y el repartidor se entera tarde.
        sa.Index(
            "ix_customer_addresses_one_default",
            "customer_id",
            unique=True,
            postgresql_where=sa.text("is_default"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    district: Mapped[str] = mapped_column(sa.Text, nullable=False)
    address_line: Mapped[str] = mapped_column(sa.Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
