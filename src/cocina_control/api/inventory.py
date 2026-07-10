"""Inventory-count endpoints (issue #13 — on-demand inventory counts).

Endpoints
---------
POST   /api/v1/inventory-counts                          — start a count session
GET    /api/v1/inventory-counts/{id}                     — get session state + items
POST   /api/v1/inventory-counts/{id}/items               — register a product count
POST   /api/v1/inventory-counts/{id}/items/{item_id}/correct  — correct a count
POST   /api/v1/inventory-counts/{id}/complete            — close the session

Design invariants
-----------------
- The OPERATOR NEVER SEES AN EXPECTED VALUE.  No field named expected_qty,
  stock_level, previous_count, or any equivalent may appear in any response
  from this module.  This is a non-negotiable requirement (requerimientos.md §1,
  docs/diseno.md §2.c Q9).

- Items are append-only.  POST /items inserts a new row; there is no PATCH or
  PUT on items.  Corrections create a new row with corrects_id pointing to the
  original.

- Idempotency for add_item: if the same product_id is submitted twice within
  the same session, the second call returns 409.  The caller must use
  /correct to change a previously recorded count.

- Complete requires ALL active products to have at least one leaf item in the
  session.  Partial counts cannot be closed (docs/diseno.md §2.c Q9).

- Concurrency: SELECT FOR UPDATE on inventory_counts serialises concurrent
  mutations on the same session.  UniqueConstraint(corrects_id) on
  inventory_count_items provides a second layer for concurrent corrections.

Time-window for operator corrections
--------------------------------------
The correction window for operators is anchored to item.created_at — NOT to
the session's completed_at.  Rationale:

  - In deliveries (issue #11), the window was anchored to validated_at because
    validation is an explicit one-time transition: there is one moment when the
    operator "closes" the delivery and the window starts.  Anchoring to that
    moment prevents a loophole where a later owner correction (with a new
    created_at) would re-open the operator's window.

  - In inventory counts, the operator counts each product individually over the
    course of a session that may span hours.  There is no single "the operator
    finished this product" transition — only item.created_at.  An item counted
    at 22:55 and corrected at 23:01 of the same calendar day is within the
    window; the same item corrected at 00:01 the next day is not.

  - The session-level completed_at is a bad anchor here: if the session is
    completed at 23:58, all items (even those added at 09:00) would get a
    same-day window that effectively expires in 2 minutes.  Anchoring to
    item.created_at gives each item its own natural window.

  - The owner can always correct, regardless of window, consistent with
    deliveries and docs/diseno.md §2.c Q10.

  Calendar-day comparison uses the business timezone (default America/Lima;
  configurable via COCINA_BUSINESS_TIMEZONE).

Fail-safe status sets
----------------------
_COUNTABLE_STATUSES and _CORRECTABLE_STATUSES use allowlists, not blocklists.
Any future status is non-writable by default until explicitly added.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cocina_control.api.deps import get_current_user, require_role
from cocina_control.db import get_session
from cocina_control.models.inventory import InventoryCount, InventoryCountItem
from cocina_control.models.product import Product
from cocina_control.models.user import User
from cocina_control.schemas.inventory import (
    InventoryCompleteResponse,
    InventoryCountResponse,
    InventoryCountStartResponse,
    InventoryItemCorrect,
    InventoryItemCorrectionResponse,
    InventoryItemCreate,
    InventoryItemResponseOperator,
    InventoryItemResponseOwner,
)
from cocina_control.security.time_windows import is_same_calendar_day_local

log = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory-counts", tags=["inventory"])

# Statuses in which new items can be added.
_COUNTABLE_STATUSES = {"in_progress"}

# Statuses in which items can be corrected (completed is allowed so that
# same-day corrections after closing still work).
_CORRECTABLE_STATUSES = {"in_progress", "completed"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_count_or_404(session: Session, count_id: uuid.UUID) -> InventoryCount:
    count = session.get(InventoryCount, count_id)
    if count is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory count not found",
        )
    return count


def _get_count_for_update_or_404(session: Session, count_id: uuid.UUID) -> InventoryCount:
    """SELECT ... FOR UPDATE — use inside an open transaction."""
    count = session.scalars(
        select(InventoryCount).where(InventoryCount.id == count_id).with_for_update()
    ).first()
    if count is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory count not found",
        )
    return count


def _get_leaf_item_or_404(
    session: Session, count_id: uuid.UUID, item_id: uuid.UUID
) -> InventoryCountItem:
    """Return the item if it belongs to the session and is a leaf (not yet corrected).

    A leaf item is one that no other item references via corrects_id.
    Corrected items cannot be corrected again — the caller must target the
    latest leaf in the chain.

    Returns 404 for both missing and non-leaf items: avoids leaking the
    existence of superseded rows.  Same pattern as deliveries (issue #11).
    """
    item = session.scalars(
        select(InventoryCountItem).where(
            InventoryCountItem.id == item_id,
            InventoryCountItem.inventory_count_id == count_id,
        )
    ).first()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found in this inventory count",
        )
    corrector = session.scalars(
        select(InventoryCountItem)
        .where(InventoryCountItem.corrects_id == item_id)
        .limit(1)
    ).first()
    if corrector is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found in this inventory count",
        )
    return item


def _build_item_responses(
    session: Session,
    count_id: uuid.UUID,
    viewer_role: str,
) -> list[InventoryItemResponseOwner | InventoryItemResponseOperator]:
    """Return ALL items for this session, resolved with product_name.

    Returns all items (original + corrections) so the caller can filter to
    leaf-only items before returning to the client.

    viewer_role controls which schema is used:
    - "owner": InventoryItemResponseOwner  (includes corrects_id + reason)
    - "operator" or any other role: InventoryItemResponseOperator  (excludes
      both fields to prevent the operator from reconstructing correction chains
      and inferring previous values — requerimientos.md §1)

    IMPORTANT: This function intentionally omits any 'expected_qty' or stock
    comparison.  The operator must count blind (requerimientos.md §1).
    """
    all_items = session.scalars(
        select(InventoryCountItem).where(
            InventoryCountItem.inventory_count_id == count_id
        )
    ).all()

    if not all_items:
        return []

    product_ids = list({item.product_id for item in all_items})
    products = {
        p.id: p
        for p in session.scalars(select(Product).where(Product.id.in_(product_ids))).all()
    }

    responses: list[InventoryItemResponseOwner | InventoryItemResponseOperator] = []
    for item in all_items:
        product = products.get(item.product_id)
        if product is None:
            log.error(
                "data_integrity_item_missing_product",
                extra={
                    "count_id": str(count_id),
                    "item_id": str(item.id),
                    "product_id": str(item.product_id),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Data integrity error: item references missing product",
            )
        if viewer_role == "owner":
            responses.append(
                InventoryItemResponseOwner(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=product.name,
                    quantity=item.quantity,
                    corrects_id=item.corrects_id,
                    reason=item.reason,
                )
            )
        else:
            responses.append(
                InventoryItemResponseOperator(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=product.name,
                    quantity=item.quantity,
                )
            )
    return responses


def _count_to_response(
    session: Session, count: InventoryCount, viewer_role: str
) -> InventoryCountResponse:
    """Build the full count response with leaf-only items.

    Leaf items = items not referenced by any other item's corrects_id.
    These represent the current (most-recent) state of each counted product.

    viewer_role is forwarded to _build_item_responses to select the correct
    response schema:
    - "owner": full fields including corrects_id + reason
    - "operator": stripped view without corrects_id or reason
    """
    all_item_responses = _build_item_responses(session, count.id, viewer_role)

    # Compute corrected IDs to filter leaves.
    all_items = session.scalars(
        select(InventoryCountItem).where(
            InventoryCountItem.inventory_count_id == count.id
        )
    ).all()
    corrected_ids = {i.corrects_id for i in all_items if i.corrects_id is not None}

    leaf_responses = [r for r in all_item_responses if r.id not in corrected_ids]

    return InventoryCountResponse(
        id=count.id,
        status=count.status,
        started_at=count.started_at,
        completed_at=count.completed_at,
        items=leaf_responses,
    )


# ---------------------------------------------------------------------------
# POST /inventory-counts  — start a count session
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=InventoryCountStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new inventory count session (operator or owner)",
)
def start_count(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> InventoryCountStartResponse:
    """Open a new inventory count session.

    Both operator and owner can start a count (e.g. the owner may start one
    during an audit visit).  The session starts as in_progress with no items.
    The caller must add items via POST /items and close with /complete.

    No body required.
    """
    now = datetime.now(UTC)
    count = InventoryCount(
        id=uuid.uuid4(),
        status="in_progress",
        started_at=now,
        started_by=current_user.id,
        created_by=current_user.id,
    )
    session.add(count)
    session.flush()

    return InventoryCountStartResponse(
        id=count.id,
        status="in_progress",
        started_at=count.started_at,
    )


# ---------------------------------------------------------------------------
# GET /inventory-counts/{count_id}  — get session state
# ---------------------------------------------------------------------------


@router.get(
    "/{count_id}",
    response_model=InventoryCountResponse,
    summary="Get inventory count state with leaf items (operator + owner)",
)
def get_count(
    count_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> InventoryCountResponse:
    """Return the current state of a count session including leaf items.

    Leaf items represent the most-recent count for each product (original or
    latest correction).  Superseded items are excluded from the response.

    CRITICAL: The response MUST NOT include any expected_qty, previous count,
    stock level, or any comparison value.  The operator counts blind.
    See requerimientos.md §Principio 1 and docs/diseno.md §2.c Q9.

    Access control (operator)
    --------------------------
    Operators may only read their own session while it is in_progress.
    Completed sessions — even their own — are not accessible to operators:
    a completed count contains the full count record which could be used
    to reconstruct expected values on a subsequent count (violates §1).
    Any other session (different owner or completed) returns 403 — NOT 404 —
    to avoid leaking the existence of count UUIDs via enumeration.

    Owners can read any session in any status.
    """
    count = _get_count_or_404(session, count_id)

    if current_user.role == "operator":
        if count.started_by != current_user.id or count.status != "in_progress":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

    return _count_to_response(session, count, current_user.role)


# ---------------------------------------------------------------------------
# POST /inventory-counts/{count_id}/items  — add a product count
# ---------------------------------------------------------------------------


@router.post(
    "/{count_id}/items",
    response_model=InventoryItemResponseOperator,
    status_code=status.HTTP_201_CREATED,
    summary="Register a product count in the session (operator only)",
)
def add_item(
    count_id: uuid.UUID,
    body: InventoryItemCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role("operator")),
) -> InventoryItemResponseOperator:
    """Record the counted quantity for a product within a count session.

    Validations:
    - quantity >= 0 (0 is valid: "none left").
    - product_id must exist and be active.
    - Session must be in_progress (fail-safe: only statuses in _COUNTABLE_STATUSES).
    - Idempotency: if the product was already counted in this session, returns
      409.  The caller must use /correct to change the recorded value.

    Owner cannot add items (403) — counting is the operator's task.
    """
    # Lock the session row to serialise concurrent adds.
    count = _get_count_for_update_or_404(session, count_id)

    if count.status not in _COUNTABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inventory count is not in_progress",
        )

    # Validate product.
    product = session.get(Product, body.product_id)
    if product is None or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product not found or inactive",
        )

    # Idempotency: check if any leaf item already counts this product in this session.
    all_items = session.scalars(
        select(InventoryCountItem).where(
            InventoryCountItem.inventory_count_id == count_id
        )
    ).all()
    corrected_ids = {i.corrects_id for i in all_items if i.corrects_id is not None}
    leaf_product_ids = {i.product_id for i in all_items if i.id not in corrected_ids}

    if body.product_id in leaf_product_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product already counted in this session; use correct endpoint to change",
        )

    item = InventoryCountItem(
        id=uuid.uuid4(),
        inventory_count_id=count_id,
        product_id=body.product_id,
        quantity=body.quantity,
        corrects_id=None,
        created_by=current_user.id,
    )
    session.add(item)
    session.flush()

    return InventoryItemResponseOperator(
        id=item.id,
        product_id=item.product_id,
        product_name=product.name,
        quantity=item.quantity,
    )


# ---------------------------------------------------------------------------
# POST /inventory-counts/{count_id}/items/{item_id}/correct  — correct a count
# ---------------------------------------------------------------------------


@router.post(
    "/{count_id}/items/{item_id}/correct",
    response_model=InventoryItemCorrectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Correct a counted item (operator same-day, owner anytime)",
)
def correct_item(
    count_id: uuid.UUID,
    item_id: uuid.UUID,
    body: InventoryItemCorrect,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> InventoryItemCorrectionResponse:
    """Create a new correction row for a leaf item.

    Append-only: the original item row is NEVER modified.  A new
    InventoryCountItem is inserted with corrects_id pointing to the corrected
    item.

    Session status: must be in_progress OR completed (corrections are allowed
    after the session is closed, within the time window).

    Permission and time-window rules
    ----------------------------------
    - Owner: can correct at any time, regardless of window.
    - Operator: correction window is the same calendar day (business timezone,
      default America/Lima) as item.created_at.

    Why item.created_at (not session.completed_at)
    -----------------------------------------------
    In deliveries (issue #11) the window was anchored to validated_at because
    the delivery has one explicit "done" transition.  In inventory counts, the
    operator counts each product individually over the course of the session
    (which may span hours).  Using completed_at as the anchor would mean that
    items counted at 09:00 in a session completed at 23:58 would have their
    correction window expire in 2 minutes — not the intended behaviour.

    Anchoring to item.created_at gives each item its own natural same-day
    window, which matches the user expectation: "I counted it today, I can
    fix it today".  The calendar-day boundary is evaluated in the business
    timezone (default America/Lima; configurable via COCINA_BUSINESS_TIMEZONE).

    Concurrency (chain bifurcation prevention)
    -------------------------------------------
    Two layers:
    1. SELECT FOR UPDATE on the count session row (serialises at app layer).
    2. UniqueConstraint("corrects_id") on inventory_count_items (DB guarantee:
       second concurrent INSERT raises IntegrityError → 409).
    """
    # Lock to serialise concurrent corrections.
    count = _get_count_for_update_or_404(session, count_id)

    if count.status not in _CORRECTABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inventory count cannot be corrected in its current status",
        )

    item = _get_leaf_item_or_404(session, count_id, item_id)

    now = datetime.now(UTC)

    # Enforce ownership and time-window for operators.
    # Ownership is checked BEFORE the time window so that an operator cannot
    # probe whether another operator's session exists by testing the time window.
    if current_user.role == "operator":
        if count.started_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )
        # Enforce time-window anchored to item.created_at.
        # See module docstring for the rationale vs. session.completed_at.
        if not is_same_calendar_day_local(item.created_at, now):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Correction window closed for operator",
            )
    elif current_user.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    new_item = InventoryCountItem(
        id=uuid.uuid4(),
        inventory_count_id=count_id,
        product_id=item.product_id,
        quantity=body.quantity,
        corrects_id=item_id,
        reason=body.reason,
        created_by=current_user.id,
    )
    session.add(new_item)

    count.updated_at = now
    count.updated_by = current_user.id

    try:
        session.flush()
    except IntegrityError as exc:
        constraint = getattr(exc.orig, "diag", None)
        constraint_name = (
            constraint.constraint_name if constraint is not None else str(exc.orig)
        )
        if "uq_inventory_count_items_corrects_id" in str(constraint_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Item already corrected concurrently; refresh and retry",
            ) from exc
        raise

    log.info(
        "correct_inventory_item",
        extra={
            "action": "correct_inventory_item",
            "count_id": str(count_id),
            "item_id_original": str(item_id),
            "new_item_id": str(new_item.id),
            "actor_id": str(current_user.id),
            "actor_role": current_user.role,
            "reason_length": len(body.reason) if body.reason else 0,
        },
    )

    return InventoryItemCorrectionResponse(
        id=new_item.id,
        inventory_count_id=new_item.inventory_count_id,
        product_id=new_item.product_id,
        quantity=new_item.quantity,
        corrects_id=new_item.corrects_id,
        reason=new_item.reason,
        created_at=new_item.created_at,
    )


# ---------------------------------------------------------------------------
# POST /inventory-counts/{count_id}/complete  — close the session
# ---------------------------------------------------------------------------


@router.post(
    "/{count_id}/complete",
    response_model=InventoryCompleteResponse,
    summary="Complete an inventory count (all active products must be counted)",
)
def complete_count(
    count_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> InventoryCompleteResponse:
    """Close an inventory count session.

    Pre-conditions:
    - Session must be in_progress.
    - Every active product in the catalogue must have at least one leaf item
      in this session.  Partial counts cannot be completed
      (docs/diseno.md §2.c Q9).

    If any active product is missing, returns 400 with a list of
    missing product_ids.

    Concurrency: SELECT FOR UPDATE serialises two concurrent /complete calls
    on the same session.  The second reads status == completed and returns 409.

    Access control (operator)
    --------------------------
    Operators can only complete their own session.  Attempting to complete
    another operator's session returns 403.  Owner can complete any session.

    Active products snapshot
    ------------------------
    The list of required products is evaluated at the moment /complete is
    called using the current is_active = true catalogue — NOT a snapshot from
    when the session started.  Rationale:

    - The catalogue is dynamic: products can be activated or deactivated
      between start and complete.
    - A product deactivated after start is no longer sold, so blocking the
      count for it would be incorrect.
    - A product activated after start is now part of the catalogue and must
      be counted.
    - This avoids locking sessions to a stale catalogue and is consistent
      with the dynamic nature of the product list.
    """
    # Lock to prevent race on /complete.
    count = _get_count_for_update_or_404(session, count_id)

    # Ownership check for operator: cannot complete another operator's session.
    if current_user.role == "operator" and count.started_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    if count.status not in _COUNTABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inventory count is not in_progress",
        )

    # Determine which active products have a leaf item in this session.
    active_products = session.scalars(
        select(Product).where(Product.is_active.is_(True))
    ).all()

    all_items = session.scalars(
        select(InventoryCountItem).where(
            InventoryCountItem.inventory_count_id == count_id
        )
    ).all()
    corrected_ids = {i.corrects_id for i in all_items if i.corrects_id is not None}
    counted_product_ids = {
        i.product_id for i in all_items if i.id not in corrected_ids
    }

    missing = [
        str(p.id) for p in active_products if p.id not in counted_product_ids
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "All active products must be counted before completing",
                "missing_product_ids": missing,
            },
        )

    now = datetime.now(UTC)
    count.status = "completed"
    count.completed_at = now
    count.completed_by = current_user.id
    count.updated_at = now
    count.updated_by = current_user.id

    session.flush()

    return InventoryCompleteResponse(
        id=count.id,
        status="completed",
        completed_at=count.completed_at,
    )
