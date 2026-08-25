"""Pydantic schemas para tarifas de reparto."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class DeliveryZoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    district: str
    fee: Decimal


class DeliveryQuoteResponse(BaseModel):
    """Respuesta de cotizacion para un distrito.

    covered=False no es un error: es la respuesta legitima a "reparten a Los
    Olivos?". Devolverlo como 404 obligaria al asistente a tratar una respuesta
    de negocio como una falla tecnica.
    """

    district: str
    covered: bool
    fee: Decimal | None = None
