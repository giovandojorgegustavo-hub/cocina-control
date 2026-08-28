"""Pydantic schemas del viaje de reparto."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class DeliveryTripCreate(BaseModel):
    """Alta de un viaje con los pedidos que lleva.

    No se manda el costo: se lee del propio link. Quien despacha no tiene por
    que transcribir un numero que ya esta publicado, y transcribirlo abre la
    puerta a que no coincida con lo que inDrive cobro.
    """

    tracking_url: Annotated[str, Field(min_length=20, max_length=500)]
    sales_order_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=20)]

    @field_validator("tracking_url")
    @classmethod
    def _es_sharetrip(cls, v: str) -> str:
        limpio = v.strip()
        if not limpio.startswith("https://sharetrip.indrive.com/"):
            raise ValueError("el link debe ser de sharetrip.indrive.com")
        return limpio


class OrderInTrip(BaseModel):
    """Lo mínimo para que el asistente le avise a cada cliente del viaje."""

    id: uuid.UUID
    customer_phone: str
    customer_name: str | None = None
    district: str
    total: Decimal


class DeliveryTripResponse(BaseModel):
    id: uuid.UUID
    tracking_url: str
    provider: str
    trip_cost: Decimal | None = None
    status: str | None = None
    created_at: datetime
    orders: list[OrderInTrip] = Field(default_factory=list)

