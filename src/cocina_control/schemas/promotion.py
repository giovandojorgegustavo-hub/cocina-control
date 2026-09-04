"""Pydantic schemas de las promociones.

Dos vistas de la misma fila: la publica (lo que el asistente necesita para
ofrecer la promo) y la completa (lo que el dueno edita). Ninguna acepta un
importe: una promocion es un porcentaje que el servidor aplica, nunca un monto
que el cliente manda.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PromotionUpdate(BaseModel):
    """Cualquier subconjunto de campos; al menos uno."""

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=120)] = None
    percent: Annotated[
        Decimal | None,
        Field(default=None, gt=0, lt=100, max_digits=5, decimal_places=2),
    ] = None
    first_order_only: bool | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PromotionUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class PromotionPublic(BaseModel):
    """Lo que ve el asistente en GET /catalog/promotions."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    percent: Decimal
    first_order_only: bool


class PromotionResponse(BaseModel):
    """Fila completa, para la pantalla del dueno."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    percent: Decimal
    first_order_only: bool
    is_active: bool
    updated_at: datetime | None = None
