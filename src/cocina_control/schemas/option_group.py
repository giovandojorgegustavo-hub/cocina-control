"""Pydantic schemas de los grupos de opciones y sus opciones.

Dos direcciones, como en delivery_zone: lo que el panel escribe (Create/Update)
y lo que el panel y la carta leen (Response). Los precios entran como Decimal
y salen como string con dos decimales, igual que el resto de los importes.

Las reglas entre campos (single implica max 1, obligatorio implica min >= 1,
min <= max) NO viven aca sino en api/option_groups.py: un PATCH manda un
subconjunto y la regla se evalua sobre el grupo ya mezclado, no sobre el body.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SelectionMode(StrEnum):
    single = "single"
    multiple = "multiple"


def _strip(value: object) -> object:
    """Se recorta ANTES de validar el largo: "   " no es un nombre."""
    return value.strip() if isinstance(value, str) else value


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------


class OptionGroupCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    selection: SelectionMode
    required: bool = False
    min_choices: Annotated[int | None, Field(default=None, ge=0)] = None
    max_choices: Annotated[int | None, Field(default=None, ge=1)] = None
    sort_order: Annotated[int, Field(default=0, ge=0)] = 0

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return _strip(value)


class OptionGroupUpdate(BaseModel):
    """Cualquier subconjunto de campos; al menos uno."""

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=80)] = None
    selection: SelectionMode | None = None
    required: bool | None = None
    min_choices: Annotated[int | None, Field(default=None, ge=0)] = None
    max_choices: Annotated[int | None, Field(default=None, ge=1)] = None
    sort_order: Annotated[int | None, Field(default=None, ge=0)] = None
    is_active: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return _strip(value)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "OptionGroupUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


# ---------------------------------------------------------------------------
# Opciones
# ---------------------------------------------------------------------------


class OptionItemCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    price: Annotated[Decimal, Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)]
    product_id: uuid.UUID | None = None
    sort_order: Annotated[int, Field(default=0, ge=0)] = 0

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return _strip(value)


class OptionItemUpdate(BaseModel):
    """Cualquier subconjunto de campos; al menos uno. product_id null desenlaza."""

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=120)] = None
    price: Annotated[
        Decimal | None, Field(default=None, ge=0, max_digits=10, decimal_places=2)
    ] = None
    product_id: uuid.UUID | None = None
    sort_order: Annotated[int | None, Field(default=None, ge=0)] = None
    is_active: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return _strip(value)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "OptionItemUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class OptionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    price: Decimal
    product_id: uuid.UUID | None = None
    sort_order: int
    is_active: bool


class OptionGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    selection: SelectionMode
    required: bool
    min_choices: int
    max_choices: int | None = None
    sort_order: int
    is_active: bool
    updated_at: datetime | None = None
    items: list[OptionItemResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Asignacion plato -> grupos
# ---------------------------------------------------------------------------


class ProductOptionGroupsPut(BaseModel):
    """Reemplaza la asignacion completa, en el orden de la lista."""

    group_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_duplicates(self) -> "ProductOptionGroupsPut":
        if len(set(self.group_ids)) != len(self.group_ids):
            raise ValueError("group_ids must not repeat a group")
        return self


class ProductOptionGroupResponse(BaseModel):
    group_id: uuid.UUID
    name: str
    sort_order: int


# ---------------------------------------------------------------------------
# Lo que ve la carta (/catalog/menu) — sin campos de administracion
# ---------------------------------------------------------------------------


class MenuOptionResponse(BaseModel):
    id: uuid.UUID
    name: str
    price: Decimal


class MenuOptionGroupResponse(BaseModel):
    id: uuid.UUID
    name: str
    selection: SelectionMode
    required: bool
    min_choices: int
    max_choices: int | None = None
    options: list[MenuOptionResponse] = Field(default_factory=list)
