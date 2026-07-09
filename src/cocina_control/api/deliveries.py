"""Delivery endpoints (issue #10 pre-load + issue #11 verification).

Pre-load routes (issue #10)
----------------------------
POST   /api/v1/deliveries          — owner pre-loads a delivery
GET    /api/v1/deliveries          — inbox list (operator + owner)
GET    /api/v1/deliveries/{id}     — delivery detail (operator + owner)
PATCH  /api/v1/deliveries/{id}     — edit draft delivery (owner only, no_leida)

Verification routes (issue #11)
---------------------------------
POST   /api/v1/deliveries/{id}/open                    — operator marks en_verificacion
POST   /api/v1/deliveries/{id}/items/{item_id}/confirm — operator sets received_qty
POST   /api/v1/deliveries/{id}/validate                — operator finalises delivery
POST   /api/v1/deliveries/{id}/items/{item_id}/correct — operator (same day) or owner

Append-only invariant for delivery_items
-----------------------------------------
Once an operator opens a delivery (status -> en_verificacion), items become
append-only: corrections create new rows pointing to the corrected row via
corrects_id.  While the delivery is still no_leida (draft, never seen by
anyone), the owner's edits are NOT corrections — they are plain draft edits.
The PATCH handler therefore replaces items with a physical DELETE + INSERT
(no corrects_id trail).  This is intentional and documented in diseno.md §2.a.

Confirm vs. Correct — design decision
--------------------------------------
During en_verificacion the operator fills in received_qty for each item.
This is a COMPLETION of information the owner could not know at pre-load
time — NOT a correction of a previous value.  Therefore confirm() does an
UPDATE on the existing item row rather than inserting a new one.

After the delivery is validada, any change to received_qty is a true
correction (the value was already recorded and reviewed).  Therefore
correct() inserts a NEW row with corrects_id pointing to the previous row,
preserving the append-only audit trail.

Concurrency design for PATCH — last-write-wins on no_leida
-----------------------------------------------------------
Two concurrent PATCH requests from the same owner on a no_leida delivery do
NOT conflict with each other: the second commit simply wins (last-write-wins).
This is an accepted design decision because:
  1. Only one owner exists per deployment.
  2. The delivery is a draft — no operator has opened it.
  3. Adding ETag or optimistic locking would be over-engineering at v0.2.

The PATCH handler does use SELECT FOR UPDATE to guard against a CONCURRENT
operator /open sneaking in between the status check and the update.  That
race is handled.  Owner-vs-owner PATCH concurrency is not guarded — last
write wins.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cocina_control.api.deps import get_current_user, require_role
from cocina_control.db import get_session
from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.product import Product
from cocina_control.models.user import User
from cocina_control.schemas.delivery import (
    DeliveryCreate,
    DeliveryDetailResponse,
    DeliveryItemConfirm,
    DeliveryItemCorrect,
    DeliveryItemCorrectionResponse,
    DeliveryItemResponse,
    DeliveryListItem,
    DeliveryUpdate,
)
from cocina_control.security.time_windows import is_same_calendar_day_argentina

log = logging.getLogger(__name__)

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

_EDITABLE_STATUSES = {"no_leida"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_delivery_or_404(session: Session, delivery_id: uuid.UUID) -> Delivery:
    delivery = session.get(Delivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")
    return delivery


def _get_delivery_for_update_or_404(session: Session, delivery_id: uuid.UUID) -> Delivery:
    """SELECT ... FOR UPDATE — use inside an open transaction."""
    delivery = session.scalars(
        select(Delivery).where(Delivery.id == delivery_id).with_for_update()
    ).first()
    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")
    return delivery


def _get_leaf_item_or_404(
    session: Session, delivery_id: uuid.UUID, item_id: uuid.UUID
) -> DeliveryItem:
    """Return the item if it belongs to the delivery and is a leaf (not yet corrected).

    A "leaf" item is one that no other item references via corrects_id.
    Corrected items cannot be confirmed or corrected again — the caller must
    target the latest leaf in the chain.

    Returns 404 (not 409) for both missing items and non-leaf items: this
    avoids leaking the existence of superseded rows to the caller, which is
    consistent with a resource-oriented API where corrected items are no longer
    addressable as targets.
    """
    item = session.scalars(
        select(DeliveryItem).where(
            DeliveryItem.id == item_id,
            DeliveryItem.delivery_id == delivery_id,
        )
    ).first()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found in this delivery",
        )
    # Check whether another item corrects this one (i.e. it is NOT a leaf).
    corrector = session.scalars(
        select(DeliveryItem).where(DeliveryItem.corrects_id == item_id).limit(1)
    ).first()
    if corrector is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found in this delivery",
        )
    return item


def _validate_products(
    session: Session, items: list
) -> dict[uuid.UUID, Product]:
    """Return a {product_id: Product} map for all items.

    Raises 400 with a list of invalid IDs if any product_id is missing or
    inactive.
    """
    product_ids = [item.product_id for item in items]
    rows = session.scalars(
        select(Product).where(Product.id.in_(product_ids))
    ).all()

    found = {p.id: p for p in rows}
    invalid = [
        str(pid)
        for pid in product_ids
        if pid not in found or not found[pid].is_active
    ]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Invalid or inactive product_ids", "invalid_ids": invalid},
        )
    return found


def _build_item_responses(
    session: Session, delivery_id: uuid.UUID
) -> list[DeliveryItemResponse]:
    """Return the current (leaf) items for a delivery, resolved with product_name.

    "Leaf" means items not referenced by any other item's corrects_id — i.e.
    the most-recent version in each correction chain.  In this PR there are no
    correction chains (only POST and PATCH-as-replacement), but the helper is
    built correctly from the start to support issue #11 without changes.
    """
    # Fetch all items for this delivery.
    all_items = session.scalars(
        select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)
    ).all()

    if not all_items:
        return []

    # IDs that are pointed to by another item (i.e. have been corrected).
    corrected_ids = {item.corrects_id for item in all_items if item.corrects_id is not None}

    # Leaf items = items not in corrected_ids.
    leaf_items = [item for item in all_items if item.id not in corrected_ids]

    # Resolve product names in a single IN query.
    product_ids = list({item.product_id for item in leaf_items})
    products = {
        p.id: p
        for p in session.scalars(select(Product).where(Product.id.in_(product_ids))).all()
    }

    responses = []
    for item in leaf_items:
        product = products.get(item.product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Data integrity error: item references missing product",
            )
        responses.append(
            DeliveryItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=product.name,
                announced_qty=item.announced_qty,
                received_qty=item.received_qty,  # always None in this PR
            )
        )
    return responses


def _delivery_to_detail(session: Session, delivery: Delivery) -> DeliveryDetailResponse:
    items = _build_item_responses(session, delivery.id)
    return DeliveryDetailResponse(
        id=delivery.id,
        supplier_name=delivery.supplier_name,
        status=delivery.status,
        created_at=delivery.created_at,
        validated_at=delivery.validated_at,
        validated_by=delivery.validated_by,
        items=items,
    )


# ---------------------------------------------------------------------------
# POST /deliveries
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DeliveryDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Pre-load a delivery (owner only)",
)
def create_delivery(
    body: DeliveryCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role("owner")),
) -> DeliveryDetailResponse:
    """Owner announces an expected delivery before the operator receives it.

    Validates every product_id — all must exist and be active.
    Duplicate product_ids within the same request are rejected (422 from schema
    or 400 if somehow bypassed).  The delivery starts as no_leida.
    """
    _validate_products(session, body.items)

    delivery = Delivery(
        id=uuid.uuid4(),
        supplier_name=body.supplier_name,
        status="no_leida",
        created_by=current_user.id,
    )
    session.add(delivery)
    session.flush()  # obtain delivery.id before inserting items

    for item_in in body.items:
        item = DeliveryItem(
            id=uuid.uuid4(),
            delivery_id=delivery.id,
            product_id=item_in.product_id,
            announced_qty=item_in.announced_qty,
            received_qty=None,
            corrects_id=None,
            created_by=current_user.id,
        )
        session.add(item)

    session.flush()
    return _delivery_to_detail(session, delivery)


# ---------------------------------------------------------------------------
# GET /deliveries
# ---------------------------------------------------------------------------


_VALID_STATUSES = {"no_leida", "en_verificacion", "validada"}


@router.get(
    "",
    response_model=list[DeliveryListItem],
    summary="List deliveries inbox (operator + owner)",
)
def list_deliveries(
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DeliveryListItem]:
    """Return the delivery inbox ordered newest-first.

    Optional ?status= filter accepts no_leida | en_verificacion | validada.
    Defaults to ?limit=100 (low volume — no pagination in v0.2).
    """
    if status_filter is not None and status_filter not in _VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status filter. Allowed values: {sorted(_VALID_STATUSES)}",
        )

    stmt = select(Delivery).order_by(Delivery.created_at.desc()).limit(limit)
    if status_filter is not None:
        stmt = stmt.where(Delivery.status == status_filter)

    deliveries = session.scalars(stmt).all()

    # Count items per delivery in a single pass.
    if not deliveries:
        return []

    delivery_ids = [d.id for d in deliveries]

    # Fetch only leaf items (not corrected) to get accurate item_count.
    all_items = session.scalars(
        select(DeliveryItem).where(DeliveryItem.delivery_id.in_(delivery_ids))
    ).all()
    corrected_ids = {i.corrects_id for i in all_items if i.corrects_id is not None}
    leaf_items = [i for i in all_items if i.id not in corrected_ids]

    count_by_delivery: dict[uuid.UUID, int] = {}
    for item in leaf_items:
        count_by_delivery[item.delivery_id] = count_by_delivery.get(item.delivery_id, 0) + 1

    return [
        DeliveryListItem(
            id=d.id,
            supplier_name=d.supplier_name,
            status=d.status,
            item_count=count_by_delivery.get(d.id, 0),
            created_at=d.created_at,
        )
        for d in deliveries
    ]


# ---------------------------------------------------------------------------
# GET /deliveries/{delivery_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{delivery_id}",
    response_model=DeliveryDetailResponse,
    summary="Get delivery detail (operator + owner)",
)
def get_delivery(
    delivery_id: uuid.UUID,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> DeliveryDetailResponse:
    """Return full delivery detail including items with product_name.

    received_qty is always null until the operator confirms (issue #11).
    Items reflect the current (leaf) state of each correction chain.
    """
    delivery = _get_delivery_or_404(session, delivery_id)
    return _delivery_to_detail(session, delivery)


# ---------------------------------------------------------------------------
# PATCH /deliveries/{delivery_id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{delivery_id}",
    response_model=DeliveryDetailResponse,
    summary="Edit draft delivery (owner only, status == no_leida)",
)
def update_delivery(
    delivery_id: uuid.UUID,
    body: DeliveryUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role("owner")),
) -> DeliveryDetailResponse:
    """Partially update a delivery that has not yet been opened by the operator.

    Only allowed while status == no_leida.  Returns 409 for any other status.
    Fail-safe: only statuses in _EDITABLE_STATUSES are permitted — any future
    status defaults to non-editable until explicitly added to that set.

    Item replacement strategy
    -------------------------
    While the delivery is no_leida, nobody has seen it — it is a draft.
    The owner's edits are plain draft mutations, NOT corrections under the
    append-only model (which only kicks in after the operator opens the
    delivery).  Therefore, when items are provided, the existing items are
    physically deleted and the new items are inserted fresh, with no
    corrects_id trail.  This is an explicit design decision documented in
    diseno.md §2.a (Pregunta 1).

    Audit trail
    -----------
    updated_at and updated_by are set on every write that produces a real
    change (supplier_name or items).  These columns are not exposed in the
    API response — they live in the DB only for internal auditing.

    Concurrency — owner-vs-owner last-write-wins
    --------------------------------------------
    En estado no_leida no hay control de concurrencia entre PATCHes del
    dueño.  El segundo commit gana.  Esto es aceptado porque un solo dueño
    edita su propio borrador.  See module docstring for full rationale.

    The SELECT FOR UPDATE lock guards against a CONCURRENT operator /open
    (issue #11) racing with this PATCH — that race IS prevented.
    """
    # Lock the row to prevent a concurrent operator /open from sneaking in.
    delivery = session.scalars(
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .with_for_update()
    ).first()

    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    if delivery.status not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delivery cannot be edited in its current status",
        )

    changed = False

    if body.supplier_name is not None:
        delivery.supplier_name = body.supplier_name
        changed = True

    if body.items is not None:
        # Validate new items before touching the database.
        _validate_products(session, body.items)

        # Physical replacement — this is a draft, not an append-only correction.
        session.execute(
            delete(DeliveryItem).where(DeliveryItem.delivery_id == delivery.id)
        )
        for item_in in body.items:
            item = DeliveryItem(
                id=uuid.uuid4(),
                delivery_id=delivery.id,
                product_id=item_in.product_id,
                announced_qty=item_in.announced_qty,
                received_qty=None,
                corrects_id=None,
                created_by=current_user.id,
            )
            session.add(item)
        changed = True

    # Stamp audit columns whenever a real change occurred.
    if changed:
        delivery.updated_at = datetime.now(UTC)
        delivery.updated_by = current_user.id

    session.flush()
    return _delivery_to_detail(session, delivery)


# ---------------------------------------------------------------------------
# POST /deliveries/{delivery_id}/open   (issue #11)
# ---------------------------------------------------------------------------


@router.post(
    "/{delivery_id}/open",
    response_model=DeliveryDetailResponse,
    summary="Open delivery for verification (operator only)",
)
def open_delivery(
    delivery_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role("operator")),
) -> DeliveryDetailResponse:
    """Transition a delivery from no_leida → en_verificacion.

    SELECT FOR UPDATE prevents a concurrent PATCH (owner) or another /open
    from racing through the status check.

    Idempotency: if the delivery is already en_verificacion this returns 409
    rather than silently succeeding, because the caller must know whether it
    was THIS call that opened the delivery (audit trail in updated_by).

    Status mapping for 409 messages:
    - en_verificacion → "Delivery is already open"
    - validada        → "Delivery is already validated"
    """
    delivery = _get_delivery_for_update_or_404(session, delivery_id)

    if delivery.status == "en_verificacion":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delivery is already open",
        )
    if delivery.status == "validada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delivery is already validated",
        )

    delivery.status = "en_verificacion"
    delivery.updated_at = datetime.now(UTC)
    delivery.updated_by = current_user.id

    session.flush()
    return _delivery_to_detail(session, delivery)


# ---------------------------------------------------------------------------
# POST /deliveries/{delivery_id}/items/{item_id}/confirm   (issue #11)
# ---------------------------------------------------------------------------


@router.post(
    "/{delivery_id}/items/{item_id}/confirm",
    response_model=DeliveryItemResponse,
    summary="Confirm item quantity received (operator only)",
)
def confirm_item(
    delivery_id: uuid.UUID,
    item_id: uuid.UUID,
    body: DeliveryItemConfirm,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role("operator")),
) -> DeliveryItemResponse:
    """Set received_qty on a leaf item while the delivery is en_verificacion.

    Design decision — UPDATE not INSERT
    ------------------------------------
    During en_verificacion the operator fills in information the owner could
    not know at pre-load time (what actually arrived).  This is a COMPLETION,
    not a correction of a previously recorded value.  Therefore confirm()
    mutates the existing item row directly rather than inserting a new row.

    The append-only model kicks in only after validate(): any post-validation
    change goes through /correct, which inserts a new row with corrects_id.

    Idempotency
    -----------
    If the same received_qty is sent twice the call is idempotent: returns 200
    with the current item without writing to the DB.

    If a DIFFERENT received_qty is sent after the item already has one, the
    call returns 409.  The operator must use /correct after the delivery is
    validated to change a previously confirmed quantity.

    Status guards
    -------------
    - no_leida      → 409 "open the delivery first"
    - validada      → 409 "delivery already validated; use correct endpoint"
    """
    delivery = _get_delivery_or_404(session, delivery_id)

    if delivery.status == "no_leida":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Open the delivery first",
        )
    if delivery.status == "validada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delivery already validated; use correct endpoint",
        )

    item = _get_leaf_item_or_404(session, delivery_id, item_id)

    # Idempotency: same value → return current state without writing.
    if item.received_qty is not None:
        if item.received_qty == body.received_qty:
            product = session.get(Product, item.product_id)
            return DeliveryItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=product.name if product else "",
                announced_qty=item.announced_qty,
                received_qty=item.received_qty,
                corrects_id=item.corrects_id,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Item already confirmed with different qty;"
                " use correct endpoint after validation"
            ),
        )

    item.received_qty = body.received_qty
    session.flush()

    product = session.get(Product, item.product_id)
    return DeliveryItemResponse(
        id=item.id,
        product_id=item.product_id,
        product_name=product.name if product else "",
        announced_qty=item.announced_qty,
        received_qty=item.received_qty,
        corrects_id=item.corrects_id,
    )


# ---------------------------------------------------------------------------
# POST /deliveries/{delivery_id}/validate   (issue #11)
# ---------------------------------------------------------------------------


@router.post(
    "/{delivery_id}/validate",
    response_model=DeliveryDetailResponse,
    summary="Validate delivery (operator only, all items must be confirmed)",
)
def validate_delivery(
    delivery_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role("operator")),
) -> DeliveryDetailResponse:
    """Finalise a delivery, transitioning it from en_verificacion → validada.

    Pre-conditions:
    - All leaf items must have received_qty IS NOT NULL.
    - Delivery must be in en_verificacion.

    Concurrency
    -----------
    SELECT FOR UPDATE on the delivery row ensures that if two operators attempt
    to validate simultaneously, the second will block until the first commits.
    The second then reads status == validada and returns 409.

    Stock impact
    ------------
    Once status == validada, the delivery_items rows (leaf items with
    received_qty IS NOT NULL) are automatically included in the on-demand stock
    computation that the dashboard (issue #14) runs.  No separate stock table
    is updated here — the computation reads directly from this table.
    """
    delivery = _get_delivery_for_update_or_404(session, delivery_id)

    if delivery.status != "en_verificacion":
        if delivery.status == "validada":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Delivery is already validated",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delivery must be open (en_verificacion) to validate",
        )

    # Fetch leaf items.
    all_items = session.scalars(
        select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)
    ).all()
    corrected_ids = {i.corrects_id for i in all_items if i.corrects_id is not None}
    leaf_items = [i for i in all_items if i.id not in corrected_ids]

    pending = [str(i.id) for i in leaf_items if i.received_qty is None]
    if pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "All items must be confirmed before validation",
                "pending_item_ids": pending,
            },
        )

    now = datetime.now(UTC)
    delivery.status = "validada"
    delivery.validated_at = now
    delivery.validated_by = current_user.id
    delivery.updated_at = now
    delivery.updated_by = current_user.id

    session.flush()
    return _delivery_to_detail(session, delivery)


# ---------------------------------------------------------------------------
# POST /deliveries/{delivery_id}/items/{item_id}/correct   (issue #11)
# ---------------------------------------------------------------------------


@router.post(
    "/{delivery_id}/items/{item_id}/correct",
    response_model=DeliveryItemCorrectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Correct a validated item (operator same-day, owner anytime)",
)
def correct_item(
    delivery_id: uuid.UUID,
    item_id: uuid.UUID,
    body: DeliveryItemCorrect,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DeliveryItemCorrectionResponse:
    """Create a new correction row for a leaf item of a validated delivery.

    Append-only: the original item row is NEVER modified.  A new DeliveryItem
    row is inserted with corrects_id pointing to the item being corrected.

    Permission and time-window rules
    ----------------------------------
    - Owner: can correct at any time, no window restriction.
    - Operator: can only correct items whose creation date (in UTC-3 calendar)
      is the same calendar day as now (UTC-3).  If the item was confirmed on a
      previous calendar day, the operator receives 403.

    The time-window is based on the item's created_at (when the item row was
    first inserted at pre-load time), which is effectively the same as the
    date of the delivery session for practical purposes.  Using the delivery's
    validated_at would also be valid, but item.created_at is more granular.

    Why item.created_at and not validated_at
    -----------------------------------------
    The item row was created when the owner pre-loaded the delivery.  The
    operator confirmed it (set received_qty) on the same day.  Using
    item.created_at as the window anchor means the operator's window is tied
    to the day the delivery was created — which matches the business intent:
    "same session" ≈ "same calendar day".  If a delivery is pre-loaded at
    23:55 and the operator confirms at 00:10 the next day, the operator
    window would be closed.  This edge case is rare and the owner can always
    correct.

    reason (optional)
    ------------------
    When provided, reason is persisted in the new correction row.  This makes
    the forensic CSV self-explanatory — the owner sees what was corrected and
    why, without needing a side channel.
    """
    delivery = _get_delivery_or_404(session, delivery_id)

    if delivery.status != "validada":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delivery not validated yet; confirm and validate first",
        )

    item = _get_leaf_item_or_404(session, delivery_id, item_id)

    now = datetime.now(UTC)

    # Enforce time-window for operators.
    if current_user.role == "operator":
        if not is_same_calendar_day_argentina(item.created_at, now):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Correction window closed for operator",
            )
    elif current_user.role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    new_item = DeliveryItem(
        id=uuid.uuid4(),
        delivery_id=delivery_id,
        product_id=item.product_id,
        announced_qty=item.announced_qty,
        received_qty=body.received_qty,
        corrects_id=item_id,
        reason=body.reason,
        created_by=current_user.id,
    )
    session.add(new_item)

    delivery.updated_at = now
    delivery.updated_by = current_user.id

    session.flush()

    if body.reason is not None:
        log.info(
            "Delivery item corrected with reason",
            extra={
                "delivery_id": str(delivery_id),
                "original_item_id": str(item_id),
                "new_item_id": str(new_item.id),
                "corrected_by": str(current_user.id),
                "role": current_user.role,
                "reason": body.reason,
            },
        )

    return DeliveryItemCorrectionResponse(
        id=new_item.id,
        delivery_id=new_item.delivery_id,
        product_id=new_item.product_id,
        announced_qty=new_item.announced_qty,
        received_qty=new_item.received_qty,
        corrects_id=new_item.corrects_id,
        reason=new_item.reason,
        created_at=new_item.created_at,
    )
