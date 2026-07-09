"""Delivery pre-load endpoints (issue #10).

Routes
------
POST   /api/v1/deliveries           — owner pre-loads a delivery
GET    /api/v1/deliveries           — inbox list (operator + owner)
GET    /api/v1/deliveries/{id}      — delivery detail (operator + owner)
PATCH  /api/v1/deliveries/{id}      — edit draft delivery (owner only, status == no_leida)

Verification endpoints (open/confirm/validate/correct) are issue #11 — not here.

Append-only invariant for delivery_items
-----------------------------------------
Once an operator opens a delivery (status -> en_verificacion), items become
append-only: corrections create new rows pointing to the corrected row via
corrects_id.  While the delivery is still no_leida (draft, never seen by
anyone), the owner's edits are NOT corrections — they are plain draft edits.
The PATCH handler therefore replaces items with a physical DELETE + INSERT
(no corrects_id trail).  This is intentional and documented in diseno.md §2.a.
"""

import uuid
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
    DeliveryItemResponse,
    DeliveryListItem,
    DeliveryUpdate,
)

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

_EDITABLE_STATUS = "no_leida"
_LOCKED_STATUSES = {"en_verificacion", "validada"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_delivery_or_404(session: Session, delivery_id: uuid.UUID) -> Delivery:
    delivery = session.get(Delivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")
    return delivery


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

    return [
        DeliveryItemResponse(
            id=item.id,
            product_id=item.product_id,
            product_name=products[item.product_id].name,
            announced_qty=item.announced_qty,
            received_qty=item.received_qty,  # always None in this PR
        )
        for item in leaf_items
    ]


def _delivery_to_detail(session: Session, delivery: Delivery) -> DeliveryDetailResponse:
    items = _build_item_responses(session, delivery.id)
    return DeliveryDetailResponse(
        id=delivery.id,
        supplier_name=delivery.supplier_name,
        status=delivery.status,
        created_at=delivery.created_at,
        created_by=delivery.created_by,
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

    Only allowed while status == no_leida.  Returns 409 once an operator has
    opened the delivery (en_verificacion) or after validation (validada).

    Item replacement strategy
    -------------------------
    While the delivery is no_leida, nobody has seen it — it is a draft.
    The owner's edits are plain draft mutations, NOT corrections under the
    append-only model (which only kicks in after the operator opens the
    delivery).  Therefore, when items are provided, the existing items are
    physically deleted and the new items are inserted fresh, with no
    corrects_id trail.  This is an explicit design decision documented in
    diseno.md §2.a (Pregunta 1).

    Race condition guard
    --------------------
    The delivery row is fetched WITH a row-level lock (SELECT FOR UPDATE).
    This prevents a concurrent /open request from changing the status between
    the check and the commit.
    """
    # Lock the row to prevent a concurrent operator /open from sneaking in.
    delivery = session.scalars(
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .with_for_update()
    ).first()

    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    if delivery.status in _LOCKED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delivery already opened by operator, cannot edit",
        )

    if body.supplier_name is not None:
        delivery.supplier_name = body.supplier_name

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

    session.flush()
    return _delivery_to_detail(session, delivery)
