"""Pydantic schemas for the dashboard endpoints (issue #14).

All monetary/quantity values are serialized as strings (Decimal → str) so that
JavaScript clients receive exact values without floating-point rounding.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Summary  — GET /dashboard/summary
# ---------------------------------------------------------------------------


class ProductSummaryItem(BaseModel):
    """Per-product row in the summary response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str
    stock_now: str  # Decimal serialized as string
    entries_qty: str  # sum of received_qty for validated deliveries in range
    consumption: str | None  # None when consumption_available is False
    consumption_available: bool
    alert: bool


class LowStockItem(BaseModel):
    """Product below its low_stock_threshold."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit: str
    stock_now: str
    low_stock_threshold: str


class OrdersSummary(BaseModel):
    completed_count: int
    photo_only_count: int


class DashboardSummaryResponse(BaseModel):
    products: list[ProductSummaryItem]
    low_stock: list[LowStockItem]
    orders_summary: OrdersSummary


# ---------------------------------------------------------------------------
# Traceability  — GET /dashboard/traceability/{product_id}
# ---------------------------------------------------------------------------


class TraceabilityEvent(BaseModel):
    """A single event that touched a product in the requested range."""

    event_type: str  # "delivery_item" | "delivery_order_item" | "inventory_count_item"
    id: uuid.UUID
    date: datetime
    operator: str  # user.name of created_by
    qty: str  # Decimal as string
    corrects_id: uuid.UUID | None
    reason: str | None

    # Parent reference — only one is non-null per event_type.
    delivery_id: uuid.UUID | None = None
    delivery_order_id: uuid.UUID | None = None
    count_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Export  — GET /dashboard/export  (StreamingResponse, no Pydantic model)
#
# The export endpoint returns a StreamingResponse directly; no schema needed.
# CSV columns:
#   event_type, event_id, date, operator_name, product_id, product_name,
#   qty, delivery_id, delivery_order_id, count_id, corrects_id, reason
# ---------------------------------------------------------------------------
