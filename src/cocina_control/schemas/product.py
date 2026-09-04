"""Pydantic schemas for the products (catalogue) domain."""

import uuid
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UnitEnum(StrEnum):
    kg = "kg"
    un = "un"
    lt = "lt"


# ---------------------------------------------------------------------------
# Shared validator — applied in create and update to normalise name.
# ---------------------------------------------------------------------------


def _validate_name(value: str) -> str:
    """Normalise name: strip outer whitespace, collapse internal runs, upper-case.

    "palta  semilla" and "palta\tsemilla" both become "PALTA SEMILLA".
    A name composed entirely of whitespace is rejected (400-level error).
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError("name must not be blank or whitespace-only")
    collapsed = " ".join(stripped.split())
    return collapsed.upper()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ProductCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    unit: UnitEnum
    low_stock_threshold: Annotated[
        Decimal | None,
        Field(default=None, gt=0),
    ] = None
    # Flags independientes (issue #140): un producto puede ser de compra,
    # de venta, o ambos — nunca ninguno.
    is_purchase: bool = True
    is_sale: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, v: str) -> str:
        return _validate_name(v)

    @model_validator(mode="after")
    def purchase_or_sale(self) -> "ProductCreate":
        if not (self.is_purchase or self.is_sale):
            raise ValueError("product must be purchase, sale, or both — not neither")
        return self


class ProductUpdate(BaseModel):
    """All fields are optional — only provided fields are updated."""

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None
    unit: UnitEnum | None = None
    low_stock_threshold: Annotated[
        Decimal | None,
        Field(default=None, gt=0),
    ] = None
    is_purchase: bool | None = None
    is_sale: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalise_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_name(v)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProductUpdate":
        if (
            self.name is None
            and self.unit is None
            and self.low_stock_threshold is None
            and self.is_purchase is None
            and self.is_sale is None
        ):
            raise ValueError("at least one field must be provided")
        return self


class ProductPricingUpdate(BaseModel):
    """Precio de lista y descuento de un producto de venta.

    Va aparte de ProductUpdate a proposito: el precio lo tocan owner Y admin
    desde la pantalla de precios, mientras que el PATCH generico sigue siendo
    del owner. Cualquier subconjunto de campos; null borra el valor.
    """

    sale_price: Annotated[
        Decimal | None,
        Field(default=None, ge=0, max_digits=10, decimal_places=2),
    ] = None
    discount_percent: Annotated[
        Decimal | None,
        Field(default=None, ge=0, lt=100, max_digits=5, decimal_places=2),
    ] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProductPricingUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ProductListItem(BaseModel):
    """Lightweight response for GET /products (list)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str
    low_stock_threshold: Decimal | None
    is_purchase: bool
    is_sale: bool
    sale_price: Decimal | None = None
    discount_percent: Decimal | None = None


class ProductResponse(BaseModel):
    """Full response for POST, PATCH and implicit GET-by-id."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str
    low_stock_threshold: Decimal | None
    is_active: bool
    is_purchase: bool
    is_sale: bool
    sale_price: Decimal | None = None
    discount_percent: Decimal | None = None
