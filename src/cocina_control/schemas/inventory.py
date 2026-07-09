"""Pydantic schemas for the inventory-counts domain (issue #13).

Design constraints enforced here:
- quantity >= 0: zero is valid ("nothing left").
- reason max_length=500: consistent with deliveries domain (issue #11).
- No expected_qty or any comparison field: the operator counts blind.
  See requerimientos.md §Principio 1 and docs/diseno.md §2.c Q9.
- created_by / started_by / completed_by are intentionally excluded from all
  response schemas — traceability lives in the DB, not in the public API.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class InventoryItemCreate(BaseModel):
    """Body for POST /inventory-counts/{id}/items.

    quantity == 0 is valid: it means "I counted this product and there is none
    left".  Negative values are rejected by the ge=0 constraint.
    """

    product_id: uuid.UUID
    quantity: Annotated[Decimal, Field(ge=0)]


class InventoryItemCorrect(BaseModel):
    """Body for POST /inventory-counts/{id}/items/{item_id}/correct.

    reason is optional.  When provided it is persisted in the new correction
    row for forensic audit.  max_length=500 matches the deliveries domain.
    """

    quantity: Annotated[Decimal, Field(ge=0)]
    reason: Annotated[str | None, Field(default=None, max_length=500)] = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class InventoryItemResponseOperator(BaseModel):
    """Single item in an inventory count session — operator view.

    Intentionally excludes:
    - expected_qty / any comparison field (operator counts blind — requerimientos.md §1)
    - created_by (traceability stays in the DB)
    - corrects_id (correction chain is internal; revealing it lets operators
      infer previous values and reconstruct deltas — requerimientos.md §1)
    - reason (correction rationale is owner-only information)
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    quantity: Decimal


class InventoryItemResponseOwner(BaseModel):
    """Single item in an inventory count session — owner view.

    Owner sees the full correction chain (corrects_id + reason) for audit.
    Intentionally excludes:
    - expected_qty / any comparison field (requerimientos.md §1 — blind count
      invariant is not broken here because owner already sees all reports)
    - created_by (traceability stays in the DB)
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    quantity: Decimal
    corrects_id: uuid.UUID | None = None
    reason: str | None = None


class InventoryCountResponse(BaseModel):
    """Response for POST /inventory-counts and GET /inventory-counts/{id}.

    started_by / completed_by are excluded — the operator does not need to
    see who started the session, and the owner has audit access via the DB.

    items contains leaf items only — corrected items are excluded from the
    response.  A leaf item is the most-recent count for a given product
    (original or latest correction).  The GET handler filters before returning.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: Literal["in_progress", "completed"]
    started_at: datetime
    completed_at: datetime | None = None
    items: list[InventoryItemResponseOwner | InventoryItemResponseOperator]


class InventoryCountStartResponse(BaseModel):
    """Slim response for POST /inventory-counts (start a new count).

    Returns only what the client needs to know right after creation.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: Literal["in_progress"]
    started_at: datetime


class InventoryItemCorrectionResponse(BaseModel):
    """Response for POST /inventory-counts/{id}/items/{item_id}/correct.

    Returns the new correction row.  corrects_id makes the chain explicit.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    inventory_count_id: uuid.UUID
    product_id: uuid.UUID
    quantity: Decimal
    corrects_id: uuid.UUID
    reason: str | None
    created_at: datetime


class InventoryCompleteResponse(BaseModel):
    """Response for POST /inventory-counts/{id}/complete."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: Literal["completed"]
    completed_at: datetime
