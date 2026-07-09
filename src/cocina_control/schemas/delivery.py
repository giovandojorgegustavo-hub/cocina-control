"""Pydantic schemas for the deliveries domain (pre-load phase, issue #10)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class DeliveryItemCreate(BaseModel):
    product_id: uuid.UUID
    announced_qty: Annotated[Decimal, Field(gt=0)]


class DeliveryCreate(BaseModel):
    supplier_name: Annotated[str, Field(min_length=1, max_length=255)]
    items: Annotated[list[DeliveryItemCreate], Field(min_length=1)]

    @field_validator("supplier_name", mode="before")
    @classmethod
    def strip_supplier_name(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("supplier_name must be a string")
        stripped = v.strip()
        if not stripped:
            raise ValueError("supplier_name must not be blank or whitespace-only")
        return stripped

    @model_validator(mode="after")
    def no_duplicate_product_ids(self) -> "DeliveryCreate":
        ids = [item.product_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("items must not contain duplicate product_id values")
        return self


class DeliveryUpdate(BaseModel):
    """Partial update: at least one field must be provided."""

    supplier_name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = (
        None
    )
    items: list[DeliveryItemCreate] | None = None

    @field_validator("supplier_name", mode="before")
    @classmethod
    def strip_supplier_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("supplier_name must be a string")
        stripped = v.strip()
        if not stripped:
            raise ValueError("supplier_name must not be blank or whitespace-only")
        return stripped

    @model_validator(mode="after")
    def at_least_one_field(self) -> "DeliveryUpdate":
        if self.supplier_name is None and self.items is None:
            raise ValueError("at least one of supplier_name or items must be provided")
        return self

    @model_validator(mode="after")
    def no_duplicate_product_ids(self) -> "DeliveryUpdate":
        if self.items is None:
            return self
        ids = [item.product_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("items must not contain duplicate product_id values")
        return self

    @model_validator(mode="after")
    def items_min_one(self) -> "DeliveryUpdate":
        if self.items is not None and len(self.items) == 0:
            raise ValueError("items must contain at least one element when provided")
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class DeliveryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    announced_qty: Decimal
    received_qty: Decimal | None


class DeliveryListItem(BaseModel):
    """Lightweight response for GET /deliveries (inbox list)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_name: str
    status: str
    item_count: int
    created_at: datetime


class DeliveryDetailResponse(BaseModel):
    """Full response for POST, GET /{id}, and PATCH /{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_name: str
    status: str
    created_at: datetime
    created_by: uuid.UUID
    validated_at: datetime | None
    validated_by: uuid.UUID | None
    items: list[DeliveryItemResponse]
