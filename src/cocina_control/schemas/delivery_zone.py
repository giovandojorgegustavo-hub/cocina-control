"""Pydantic schemas para tarifas de reparto.

Dos direcciones: lo que el asistente y el panel leen (DeliveryZoneResponse) y
lo que el dueno escribe (Create/Update). La tarifa entra como Decimal y sale
como string con dos decimales, igual que el resto de los importes de la API.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _strip_district(value: object) -> object:
    """Sin espacios en los bordes: "Lince " y "Lince" son el mismo distrito.

    Se recorta ANTES de validar el largo, para que "   " no pase como un nombre
    de tres caracteres y termine guardado vacio.
    """
    return value.strip() if isinstance(value, str) else value


class DeliveryZoneCreate(BaseModel):
    # Un distrito de Lima no pasa de 30 letras; 80 deja margen para una
    # aclaracion tipo "Cercado de Lima (centro)" sin aceptar un parrafo.
    district: Annotated[str, Field(min_length=1, max_length=80)]
    fee: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]

    @field_validator("district", mode="before")
    @classmethod
    def trim_district(cls, value: object) -> object:
        return _strip_district(value)


class DeliveryZoneUpdate(BaseModel):
    """Cualquier subconjunto de campos; al menos uno."""

    district: Annotated[str | None, Field(default=None, min_length=1, max_length=80)] = None
    fee: Annotated[
        Decimal | None,
        Field(default=None, ge=0, max_digits=10, decimal_places=2),
    ] = None
    is_active: bool | None = None

    @field_validator("district", mode="before")
    @classmethod
    def trim_district(cls, value: object) -> object:
        return _strip_district(value)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "DeliveryZoneUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class DeliveryZoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    district: str
    fee: Decimal
    is_active: bool
    updated_at: datetime | None = None


class DeliveryQuoteResponse(BaseModel):
    """Respuesta de cotizacion para un distrito.

    covered=False no es un error: es la respuesta legitima a "reparten a Los
    Olivos?". Devolverlo como 404 obligaria al asistente a tratar una respuesta
    de negocio como una falla tecnica.
    """

    district: str
    covered: bool
    fee: Decimal | None = None
