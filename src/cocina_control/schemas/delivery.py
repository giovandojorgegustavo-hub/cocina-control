"""Pydantic schemas for the deliveries domain.

Pre-load schemas (issue #10): DeliveryCreate, DeliveryUpdate.
Verification schemas (issue #11): DeliveryItemConfirm, DeliveryItemCorrect.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

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


# ---------------------------------------------------------------------------
# Verification request schemas (issue #11)
# ---------------------------------------------------------------------------


class DeliveryItemConfirm(BaseModel):
    """Body for POST /deliveries/{id}/items/{item_id}/confirm.

    received_qty == 0 is valid: it means the product was announced but did
    not arrive.  Negative values are rejected by the ge=0 constraint.
    """

    received_qty: Annotated[Decimal, Field(ge=0)]


class DeliveryItemCorrect(BaseModel):
    """Body for POST /deliveries/{id}/items/{item_id}/correct.

    reason is optional.  When provided it is persisted in the new correction
    row so the forensic CSV shows why the quantity was changed.  If omitted,
    the column is stored as NULL — no information is lost other than the
    operator's explanation.

    Design decision (issue #11): reason is persisted (option b) rather than
    ignored (option a) because it adds forensic value with no schema cost
    beyond a single nullable TEXT column (migration 0005).
    """

    received_qty: Annotated[Decimal, Field(ge=0)]
    reason: str | None = None


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
    corrects_id: uuid.UUID | None = None


class DeliveryListItem(BaseModel):
    """Lightweight response for GET /deliveries (inbox list)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_name: str
    status: Literal["no_leida", "en_verificacion", "validada"]
    item_count: int
    created_at: datetime


class DeliveryDetailResponse(BaseModel):
    """Full response for POST, GET /{id}, and PATCH /{id}.

    created_by is intentionally excluded: traceability lives in the DB, not
    in the public API.  The operator must not see the owner's UUID on every
    detail response.  If the owner ever needs audit information, a dedicated
    endpoint or query flag will be added — not exposed by default.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_name: str
    status: Literal["no_leida", "en_verificacion", "validada"]
    created_at: datetime
    validated_at: datetime | None
    validated_by: uuid.UUID | None
    items: list[DeliveryItemResponse]


class DeliveryItemCorrectionResponse(BaseModel):
    """Response for POST /deliveries/{id}/items/{item_id}/correct.

    Returns the new correction item.  corrects_id makes the append-only chain
    explicit: the caller does not need to infer it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    delivery_id: uuid.UUID
    product_id: uuid.UUID
    announced_qty: Decimal
    received_qty: Decimal
    corrects_id: uuid.UUID
    reason: str | None
    created_at: datetime
