"""Pydantic schemas for the suppliers registry (issue #129)."""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cocina_control.schemas.product import _validate_name


class SupplierCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    # telefono opcional: texto libre corto (celular, fijo, con o sin prefijo)
    phone: Annotated[str | None, Field(default=None, max_length=30)] = None

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, v: str) -> str:
        # misma normalizacion que productos: strip + collapse + UPPER
        return _validate_name(v)

    @field_validator("phone", mode="before")
    @classmethod
    def normalise_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str | None
    is_active: bool


class SupplierListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str | None
