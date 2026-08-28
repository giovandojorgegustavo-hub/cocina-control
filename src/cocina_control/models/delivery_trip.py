"""Viaje de reparto: un inDrive que lleva uno o varios pedidos.

El reparto lo hace un tercero. Bonabowl pide el viaje, paga su costo, y le
cobra al cliente la tarifa cotizada de delivery_zones. Son dos numeros
distintos y por eso el costo del viaje NO se reparte entre los pedidos: nadie
lo cobra por separado.

Lo que si aparece por primera vez es el margen del reparto — cobrado menos
pagado — que hasta ahora no existia en ningun lado.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from cocina_control.db import Base
from cocina_control.models.base import TimestampMixin


class DeliveryTrip(Base, TimestampMixin):
    __tablename__ = "delivery_trips"

    __table_args__ = (
        # Dos filas con el mismo link son el mismo viaje contado dos veces, y
        # el margen del reparto saldria mal sin que nada lo delate.
        sa.Index("ix_delivery_trips_url_unique", "tracking_url", unique=True),
        sa.Index("ix_delivery_trips_created_at", "created_at"),
        sa.CheckConstraint(
            "trip_cost IS NULL OR trip_cost >= 0",
            name="ck_delivery_trips_cost_not_negative",
        ),
        sa.CheckConstraint(
            r"tracking_url ~ '^https://sharetrip\.indrive\.com/'",
            name="ck_delivery_trips_url_es_sharetrip",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    tracking_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    provider: Mapped[str] = mapped_column(sa.Text, nullable=False, default="indrive")
    # NULL mientras no se pudo leer del link. Es preferible un pedido despachado
    # sin costo conocido a bloquear el despacho por un dato completable despues.
    trip_cost: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 2), nullable=True)
    # Texto libre a proposito: el vocabulario es de inDrive, no nuestro, y
    # pueden sumar valores sin avisarnos. Observados:
    # on_delivery -> reached_destination_point -> done.
    status: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status_checked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
