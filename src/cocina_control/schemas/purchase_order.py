"""Pydantic schemas for the purchase-orders domain (Backend #2 — Slice 2b).

Request schemas:
  PurchaseOrderCreateItem, PurchaseOrderCreate    — EP-1 POST /purchase-orders
  PartidaCreateItem, PartidaCreate               — EP-6 POST /purchase-orders/{id}/partidas

Response schemas:
  PurchaseOrderListItem                          — EP-2 GET /purchase-orders
  PurchaseOrderDetailItem, PurchaseOrderDetailResponse  — EP-1, EP-3
  PurchaseOrderPendingItem                       — EP-4 GET /purchase-orders/pending
  PartidaDraftItem, PartidaDraftResponse         — EP-5 GET /purchase-orders/{id}/partida-draft
  PartidaResponse                                — EP-6 POST /purchase-orders/{id}/partidas

Regla de oro (requerimientos.md Principio 1):
  PurchaseOrderPendingItem, PartidaDraftItem/Response, and PartidaResponse
  MUST NOT contain unit_cost, total_ordered, pending_amount, or any monetary field.
  This is enforced by schema design — those fields simply do not exist.
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


class PurchaseOrderCreateItem(BaseModel):
    product_id: uuid.UUID
    expected_qty: Annotated[Decimal, Field(gt=0, description="Must be greater than 0")]
    unit_cost: Annotated[Decimal, Field(gt=0, description="Must be greater than 0")]


class PurchaseOrderCreate(BaseModel):
    supplier_name: Annotated[str, Field(min_length=1, max_length=500)]
    items: Annotated[list[PurchaseOrderCreateItem], Field(min_length=1)]

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
    def no_duplicate_product_ids(self) -> "PurchaseOrderCreate":
        ids = [item.product_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("items must not contain duplicate product_id values")
        return self


class PartidaCreateItem(BaseModel):
    purchase_order_item_id: uuid.UUID
    received_qty: Annotated[Decimal, Field(ge=0, description="Must be >= 0")]


class PartidaCreate(BaseModel):
    items: Annotated[list[PartidaCreateItem], Field(min_length=1)]

    @model_validator(mode="after")
    def no_duplicate_item_ids(self) -> "PartidaCreate":
        ids = [item.purchase_order_item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("items must not contain duplicate purchase_order_item_id values")
        return self


# ---------------------------------------------------------------------------
# Response schemas — owner/admin (include monetary fields)
# ---------------------------------------------------------------------------


class PurchaseOrderDetailItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID                  # id of the active (leaf) item
    product_id: uuid.UUID
    product_name: str
    unit: str
    expected_qty: Decimal          # vigente (leaf)
    unit_cost: Decimal             # vigente (leaf cost)
    received_qty: Decimal          # Σ received_qty across validated partidas
    pending_qty: Decimal           # expected_qty - received_qty (can be negative)
    line_total: Decimal            # expected_qty × unit_cost


class PurchaseOrderDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_name: str
    created_at: datetime
    created_by_name: str
    derived_status: Literal["open", "partially_received", "closed", "annulled"]
    items: list[PurchaseOrderDetailItem]
    total_ordered: Decimal
    total_received: Decimal
    pending_amount: Decimal
    partida_count: int


class PurchaseOrderListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_name: str
    created_at: datetime
    derived_status: Literal["open", "partially_received", "closed", "annulled"]
    item_count: int
    total_ordered: Decimal
    total_received: Decimal
    pending_amount: Decimal
    pending_summary: str | None = None


# ---------------------------------------------------------------------------
# Response schemas — cocinero/captura (ZERO monetary fields — regla de oro)
# ---------------------------------------------------------------------------


class PurchaseOrderPendingItem(BaseModel):
    """Response schema for EP-4 GET /purchase-orders/pending.

    CRITICAL: This schema intentionally omits ALL monetary fields.
    No unit_cost, no total_ordered, no pending_amount, no price-related data.
    Verified in tests (test_pending_no_monetary_fields).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    supplier_name: str
    created_at: datetime
    derived_status: Literal["open", "partially_received"]
    pending_items_summary: str


class PartidaDraftItem(BaseModel):
    """One item in the draft partida — no monetary fields."""

    model_config = ConfigDict(from_attributes=True)

    purchase_order_item_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    unit: str
    pending_qty: Decimal           # expected_qty_vigente - Σ received_qty
    already_received: Decimal      # Σ received_qty


class PartidaDraftResponse(BaseModel):
    """Response for EP-5 GET /purchase-orders/{id}/partida-draft.

    CRITICAL: No monetary fields. No expected_qty (redundant). No unit_cost.
    """

    model_config = ConfigDict(from_attributes=True)

    order_id: uuid.UUID
    supplier_name: str
    partida_number: int
    items: list[PartidaDraftItem]


class PartidaResponse(BaseModel):
    """Response for EP-6 POST /purchase-orders/{id}/partidas.

    CRITICAL: No monetary fields.
    order_status reflects the new derived status after the partida is recorded.
    """

    model_config = ConfigDict(from_attributes=True)

    delivery_id: uuid.UUID
    partida_number: int
    order_id: uuid.UUID
    order_status: Literal["open", "partially_received", "closed"]
