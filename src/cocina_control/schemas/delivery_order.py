"""Pydantic schemas for the delivery_orders domain (issue #12).

Request schemas
---------------
DeliveryOrderCompleteItem  — one product line when completing an order.
DeliveryOrderComplete      — body for POST /delivery-orders/{id}/complete.
DeliveryOrderCorrect       — body for POST /delivery-orders/{id}/correct.
DeliveryOrderCancel        — body for POST /delivery-orders/{id}/cancel.

Response schemas
----------------
DeliveryOrderCreatedResponse  — minimal response after POST (create).
DeliveryOrderListItem         — row in GET /delivery-orders (inbox).
DeliveryOrderItemResponse     — one product line in a detail response.
DeliveryOrderDetailResponse   — full detail for GET /delivery-orders/{id}.
DeliveryOrderCancelResponse   — response after cancel (shows corrects_id).
DeliveryOrderCorrectResponse  — response after correct (shows new order id).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Allowed platform values (nullable — not required in v0.2).
# ---------------------------------------------------------------------------

PlatformLiteral = Literal["rappi", "pedidosya"] | None

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class DeliveryOrderCompleteItem(BaseModel):
    product_id: uuid.UUID
    quantity: Annotated[Decimal, Field(gt=0)]


class DeliveryOrderComplete(BaseModel):
    """Body for POST /delivery-orders/{id}/complete."""

    items: Annotated[list[DeliveryOrderCompleteItem], Field(min_length=1)]
    platform: PlatformLiteral = None


class DeliveryOrderCorrect(BaseModel):
    """Body for POST /delivery-orders/{id}/correct."""

    items: Annotated[list[DeliveryOrderCompleteItem], Field(min_length=1)]
    reason: Annotated[str | None, Field(default=None, max_length=500)] = None
    platform: PlatformLiteral = None


class DeliveryOrderCancel(BaseModel):
    """Body for POST /delivery-orders/{id}/cancel."""

    reason: Annotated[str | None, Field(default=None, max_length=500)] = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class DeliveryOrderCreatedResponse(BaseModel):
    """Minimal response returned immediately after order creation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: Literal["pending"]
    created_at: datetime


class DeliveryOrderListItem(BaseModel):
    """Lightweight row for GET /delivery-orders (inbox).

    has_photo is computed by the router (photo_url IS NOT NULL).
    photo_by and photo_at are omitted intentionally — operators should
    not see who photographed an order in the list view.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: Literal["pending", "completed"]
    photo_at: datetime | None
    created_at: datetime
    has_photo: bool
    corrects_id: uuid.UUID | None = None


class DeliveryOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: Decimal
    created_at: datetime


class DeliveryOrderDetailResponse(BaseModel):
    """Full detail for a single order.

    created_by / photo_by / completed_by are NOT exposed — traceability
    lives in the DB.  A dedicated audit endpoint can expose them if needed.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: Literal["pending", "completed"]
    has_photo: bool
    photo_at: datetime | None
    completed_at: datetime | None
    platform: str | None
    items: list[DeliveryOrderItemResponse]
    created_at: datetime
    corrects_id: uuid.UUID | None = None


class DeliveryOrderPhotoResponse(BaseModel):
    id: uuid.UUID
    photo_at: datetime
    # relative path stored in DB — not the serving URL
    photo_url: str


class DeliveryOrderCancelResponse(BaseModel):
    """Response after cancel — new order row that cancels the original."""

    id: uuid.UUID
    corrects_id: uuid.UUID
    status: Literal["pending"]
    created_at: datetime


class DeliveryOrderCorrectResponse(BaseModel):
    """Response after correct — new order row that corrects the original."""

    id: uuid.UUID
    corrects_id: uuid.UUID
    status: Literal["completed"]
    items: list[DeliveryOrderItemResponse]
    created_at: datetime
