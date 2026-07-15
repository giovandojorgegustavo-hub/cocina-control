"""Delivery-order endpoints (issue #12 — photo-first orders).

Endpoints
---------
POST   /api/v1/delivery-orders              — operator creates pending order
POST   /api/v1/delivery-orders/{id}/photo   — operator uploads photo
GET    /api/v1/delivery-orders/{id}/photo   — owner or uploader downloads photo
GET    /api/v1/delivery-orders              — inbox list (operator + owner)
GET    /api/v1/delivery-orders/{id}         — full detail for one order (operator + owner)
POST   /api/v1/delivery-orders/{id}/complete— operator marks completed + items
POST   /api/v1/delivery-orders/{id}/cancel  — operator or owner cancels (append-only)
POST   /api/v1/delivery-orders/{id}/correct — operator (same-day) or owner corrects

Append-only invariant
---------------------
cancel and correct never mutate the original order.  They create a new
DeliveryOrder row with corrects_id pointing to the original.

UniqueConstraint("corrects_id") on delivery_orders (migration 0008) prevents
concurrent bifurcation: if two clients race, the second INSERT raises
IntegrityError → 409.

Photo access rules
------------------
GET /photo is accessible only to:
  - The operator who uploaded the photo (photo_by == current_user.id).
  - Any owner.

Path-traversal guard
--------------------
photo_url stored in the DB is always a UUID-based relative path generated
by save_photo().  resolve_path_safely() performs an additional check that
the resolved absolute path stays within PHOTOS_ROOT.
"""

import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cocina_control.api.deps import get_current_user, require_any_role, require_role
from cocina_control.config import get_settings
from cocina_control.db import get_session
from cocina_control.models.delivery_order import DeliveryOrder, DeliveryOrderItem
from cocina_control.models.product import Product
from cocina_control.models.user import User
from cocina_control.schemas.delivery_order import (
    DeliveryOrderCancel,
    DeliveryOrderCancelResponse,
    DeliveryOrderComplete,
    DeliveryOrderCorrect,
    DeliveryOrderCorrectResponse,
    DeliveryOrderCreatedResponse,
    DeliveryOrderDetailResponse,
    DeliveryOrderItemResponse,
    DeliveryOrderListItem,
    DeliveryOrderPhotoResponse,
)
from cocina_control.security.time_windows import is_same_calendar_day_local
from cocina_control.services.photos import (
    PhotoValidationError,
    content_type_for_extension,
    read_and_validate_upload,
    resolve_path_safely,
    save_photo,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/delivery-orders", tags=["delivery-orders"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_STATUSES = {"pending", "completed"}


def _get_order_or_404(session: Session, order_id: uuid.UUID) -> DeliveryOrder:
    order = session.get(DeliveryOrder, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _get_order_for_update_or_404(session: Session, order_id: uuid.UUID) -> DeliveryOrder:
    """SELECT … FOR UPDATE — prevents concurrent state transitions."""
    order = session.scalars(
        select(DeliveryOrder).where(DeliveryOrder.id == order_id).with_for_update()
    ).first()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _is_leaf_order(session: Session, order_id: uuid.UUID) -> bool:
    """Return True if no other order references this one via corrects_id."""
    corrector = session.scalars(
        select(DeliveryOrder).where(DeliveryOrder.corrects_id == order_id).limit(1)
    ).first()
    return corrector is None


def _validate_products(
    session: Session, items: list
) -> dict[uuid.UUID, Product]:
    product_ids = [item.product_id for item in items]
    rows = session.scalars(select(Product).where(Product.id.in_(product_ids))).all()
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


def _get_leaf_items(session: Session, order_id: uuid.UUID) -> list[DeliveryOrderItem]:
    """Return all items for an order.

    Item-level correction (corrects_id on DeliveryOrderItem) does not apply
    in this domain — orders are corrected as a whole via correct_order().
    The corrects_id column exists from the generic append-only schema but is
    never populated here, so a simple SELECT is correct and sufficient.
    """
    return list(
        session.scalars(
            select(DeliveryOrderItem).where(DeliveryOrderItem.delivery_order_id == order_id)
        ).all()
    )


def _build_item_responses(
    session: Session, order_id: uuid.UUID
) -> list[DeliveryOrderItemResponse]:
    leaf_items = _get_leaf_items(session, order_id)
    return [
        DeliveryOrderItemResponse(
            id=item.id,
            product_id=item.product_id,
            quantity=item.quantity,
            created_at=item.created_at,
        )
        for item in leaf_items
    ]


def _order_to_detail(
    session: Session, order: DeliveryOrder
) -> DeliveryOrderDetailResponse:
    items = _build_item_responses(session, order.id)
    return DeliveryOrderDetailResponse(
        id=order.id,
        status=order.status,
        has_photo=order.photo_url is not None,
        photo_at=order.photo_at,
        completed_at=order.completed_at,
        platform=order.platform,
        items=items,
        created_at=order.created_at,
        corrects_id=order.corrects_id,
        reason=order.reason,
    )


def _handle_integrity_error(exc: IntegrityError, constraint_fragment: str) -> None:
    """Re-raise exc as 409 if the constraint name matches, else propagate."""
    constraint = getattr(exc.orig, "diag", None)
    name = constraint.constraint_name if constraint is not None else str(exc.orig)
    if constraint_fragment in str(name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concurrent modification detected; refresh and retry",
        ) from exc
    raise exc


# ---------------------------------------------------------------------------
# POST /delivery-orders
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DeliveryOrderCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pending order (cocinero or admin)",
)
def create_order(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("cocinero", "admin")),
) -> DeliveryOrderCreatedResponse:
    """Operator creates an empty order in 'pending' status.

    No body required.  The photo is uploaded separately via /photo.
    """
    now = datetime.now(UTC)
    order = DeliveryOrder(
        id=uuid.uuid4(),
        status="pending",
        created_by=current_user.id,
        created_at=now,
    )
    session.add(order)
    session.flush()
    return DeliveryOrderCreatedResponse(
        id=order.id,
        status="pending",
        created_at=order.created_at,
    )


# ---------------------------------------------------------------------------
# POST /delivery-orders/{id}/photo
# ---------------------------------------------------------------------------


@router.post(
    "/{order_id}/photo",
    response_model=DeliveryOrderPhotoResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload photo for an order (cocinero or admin)",
)
async def upload_photo(
    order_id: uuid.UUID,
    file: UploadFile,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("cocinero", "admin")),
) -> DeliveryOrderPhotoResponse:
    """Upload a JPEG or PNG photo for a pending order.

    Rules:
    - Maximum 2 MB.  Returns 413 if exceeded.
    - Only JPEG and PNG are accepted (validated by magic bytes, not Content-Type).
      Returns 415 for unsupported formats, 400 for wrong magic bytes.
    - If the order already has a photo: returns 409.
    - The order must exist: returns 404 otherwise.
    - Only the operator role can upload: owner returns 403.

    Stored at: PHOTOS_ROOT/{year}/{month}/{uuid}.{ext}
    photo_url in DB: relative path '{year}/{month}/{uuid}.{ext}'

    Filesystem safety:
    - The order is locked (SELECT FOR UPDATE) before reading the file.
    - save_photo() writes to a .tmp file; os.replace() runs only after DB flush
      succeeds.  If flush fails the .tmp is deleted and no orphan is left.
    """
    # 1. Lock the order row before touching the filesystem.
    order = _get_order_for_update_or_404(session, order_id)

    if order.photo_url is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="photo already exists; use /correct to replace it",
        )

    # 2. Read and validate upload (after order check to avoid IO on bad orders).
    try:
        raw, ext = await read_and_validate_upload(file)
    except PhotoValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    now = datetime.now(UTC)
    settings = get_settings()

    # 3. Write to .tmp — no permanent file until DB flush succeeds.
    relative_path, tmp_path, final_path = save_photo(raw, ext, settings.photos_root, now)

    try:
        order.photo_url = relative_path
        order.photo_at = now
        order.photo_by = current_user.id
        session.flush()
        # Atomic rename: only runs if flush succeeded.
        os.replace(tmp_path, final_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return DeliveryOrderPhotoResponse(
        id=order.id,
        photo_at=now,
    )


# ---------------------------------------------------------------------------
# GET /delivery-orders/{id}/photo
# ---------------------------------------------------------------------------


@router.get(
    "/{order_id}/photo",
    summary="Download order photo (owner or uploader only)",
    response_class=FileResponse,
)
def get_photo(
    order_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Serve the binary photo file.

    Access rules:
    - Owner: always allowed.
    - Operator: only if they are the one who uploaded the photo (photo_by).

    Returns:
    - 401 if no token.
    - 403 if operator is not the uploader.
    - 404 if order not found or has no photo.
    - FileResponse with correct Content-Type otherwise.
    """
    order = _get_order_or_404(session, order_id)

    # 1. Authorize first — prevents existence oracle for operators who didn't upload.
    if current_user.role in ("cocinero", "admin") and order.photo_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    elif current_user.role not in ("cocinero", "owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # 2. Check photo existence after auth.
    if order.photo_url is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This order has no photo yet",
        )

    settings = get_settings()
    try:
        abs_path = resolve_path_safely(order.photo_url, settings.photos_root)
    except ValueError:
        log.error(
            "path_traversal_blocked",
            extra={"order_id": str(order_id), "photo_url": order.photo_url},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal storage error",
        )

    if not abs_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo file not found",
        )

    ext = order.photo_url.rsplit(".", 1)[-1].lower()
    media_type = content_type_for_extension(ext)

    response = FileResponse(path=str(abs_path), media_type=media_type)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ---------------------------------------------------------------------------
# GET /delivery-orders
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[DeliveryOrderListItem],
    summary="List orders inbox (operator + owner)",
)
def list_orders(
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DeliveryOrderListItem]:
    """Return delivery orders newest-first.

    Optional ?status=pending|completed filter.
    """
    if status_filter is not None and status_filter not in _VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status filter. Allowed values: {sorted(_VALID_STATUSES)}",
        )

    stmt = (
        select(DeliveryOrder).order_by(DeliveryOrder.created_at.desc()).limit(limit)
    )
    if status_filter is not None:
        stmt = stmt.where(DeliveryOrder.status == status_filter)

    orders = session.scalars(stmt).all()

    return [
        DeliveryOrderListItem(
            id=o.id,
            status=o.status,
            photo_at=o.photo_at,
            created_at=o.created_at,
            has_photo=o.photo_url is not None,
            corrects_id=o.corrects_id,
        )
        for o in orders
    ]


# ---------------------------------------------------------------------------
# POST /delivery-orders/{id}/complete
# ---------------------------------------------------------------------------


@router.post(
    "/{order_id}/complete",
    response_model=DeliveryOrderDetailResponse,
    summary="Complete an order with product items (cocinero or admin)",
)
def complete_order(
    order_id: uuid.UUID,
    body: DeliveryOrderComplete,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("cocinero", "admin")),
) -> DeliveryOrderDetailResponse:
    """Mark a pending order as completed and record product items.

    Requires at least 1 item (enforced by schema min_length=1).
    Order must be in 'pending' status.
    Any operator can complete any pending order (cross-shift allowed).
    """
    order = _get_order_for_update_or_404(session, order_id)

    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order is already {order.status}; cannot complete again",
        )

    _validate_products(session, body.items)

    now = datetime.now(UTC)

    for item_in in body.items:
        item = DeliveryOrderItem(
            id=uuid.uuid4(),
            delivery_order_id=order.id,
            product_id=item_in.product_id,
            quantity=item_in.quantity,
            created_by=current_user.id,
        )
        session.add(item)

    order.status = "completed"
    order.completed_at = now
    order.completed_by = current_user.id
    if body.platform is not None:
        order.platform = body.platform

    session.flush()
    return _order_to_detail(session, order)


# ---------------------------------------------------------------------------
# POST /delivery-orders/{id}/cancel
# ---------------------------------------------------------------------------


@router.post(
    "/{order_id}/cancel",
    response_model=DeliveryOrderCancelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cancel an order (operator or owner) — append-only",
)
def cancel_order(
    order_id: uuid.UUID,
    body: DeliveryOrderCancel,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DeliveryOrderCancelResponse:
    """Anull an order by creating a new order with corrects_id pointing to it.

    The original order is NEVER modified.
    A leaf check ensures the order hasn't already been cancelled/corrected.
    No time-window restriction — cancellation is always available.

    Permission: operator or owner.
    """
    if current_user.role not in ("cocinero", "owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # SELECT FOR UPDATE to prevent concurrent cancellation race.
    order = _get_order_for_update_or_404(session, order_id)

    # Leaf check — cannot cancel an already cancelled/corrected order.
    if not _is_leaf_order(session, order_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order has already been cancelled or corrected",
        )

    now = datetime.now(UTC)
    new_order = DeliveryOrder(
        id=uuid.uuid4(),
        status="pending",
        created_by=current_user.id,
        created_at=now,
        corrects_id=order_id,
        # Carry over platform if set, as metadata reference.
        platform=order.platform,
        reason=body.reason,
    )
    session.add(new_order)

    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        _handle_integrity_error(exc, "uq_delivery_orders_corrects_id")

    log.info(
        "cancel_order",
        extra={
            "action": "cancel_order",
            "original_order_id": str(order_id),
            "new_order_id": str(new_order.id),
            "actor_id": str(current_user.id),
            "actor_role": current_user.role,
            "has_reason": body.reason is not None,
        },
    )

    return DeliveryOrderCancelResponse(
        id=new_order.id,
        corrects_id=order_id,
        status="pending",
        created_at=new_order.created_at,
    )


# ---------------------------------------------------------------------------
# POST /delivery-orders/{id}/correct
# ---------------------------------------------------------------------------


@router.post(
    "/{order_id}/correct",
    response_model=DeliveryOrderCorrectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Correct a completed order (operator same-day business timezone, owner anytime)",
)
def correct_order(
    order_id: uuid.UUID,
    body: DeliveryOrderCorrect,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DeliveryOrderCorrectResponse:
    """Correct a completed order's items by creating a new order row.

    The original order is NEVER modified (append-only).

    Permission and time-window:
    - Owner: can correct at any time.
    - Operator: only on the same calendar day (business timezone, default America/Lima)
      as completed_at.

    The order must be 'completed' to be corrected.
    Leaf check: cannot correct an already corrected order.
    """
    if current_user.role not in ("cocinero", "owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # SELECT FOR UPDATE to prevent concurrent correction race.
    order = _get_order_for_update_or_404(session, order_id)

    if order.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order must be completed before it can be corrected",
        )

    # Leaf check — cannot correct an already corrected/cancelled order.
    if not _is_leaf_order(session, order_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order has already been corrected or cancelled",
        )

    now = datetime.now(UTC)

    # Enforce time-window for operators.
    if current_user.role in ("cocinero", "admin"):
        if order.completed_at is None or not is_same_calendar_day_local(
            order.completed_at, now
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Correction window closed for operator",
            )

    _validate_products(session, body.items)

    platform = body.platform if body.platform is not None else order.platform

    new_order = DeliveryOrder(
        id=uuid.uuid4(),
        status="completed",
        created_by=current_user.id,
        created_at=now,
        completed_at=now,
        completed_by=current_user.id,
        corrects_id=order_id,
        platform=platform,
        reason=body.reason,
    )
    session.add(new_order)

    # Flush 1: persist new_order row (IntegrityError guard for concurrent correct).
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        _handle_integrity_error(exc, "uq_delivery_orders_corrects_id")

    for item_in in body.items:
        item = DeliveryOrderItem(
            id=uuid.uuid4(),
            delivery_order_id=new_order.id,
            product_id=item_in.product_id,
            quantity=item_in.quantity,
            created_by=current_user.id,
        )
        session.add(item)

    # Flush 2: persist items — log only after both flushes succeed.
    session.flush()

    log.info(
        "correct_order",
        extra={
            "action": "correct_order",
            "original_order_id": str(order_id),
            "new_order_id": str(new_order.id),
            "actor_id": str(current_user.id),
            "actor_role": current_user.role,
            "has_reason": body.reason is not None,
        },
    )

    items = _build_item_responses(session, new_order.id)
    return DeliveryOrderCorrectResponse(
        id=new_order.id,
        corrects_id=order_id,
        status="completed",
        items=items,
        created_at=new_order.created_at,
    )


# ---------------------------------------------------------------------------
# GET /delivery-orders/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/{order_id}",
    response_model=DeliveryOrderDetailResponse,
    summary="Get order detail (operator or owner)",
)
def get_order_detail(
    order_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DeliveryOrderDetailResponse:
    """Return full detail for a single order.

    Access: operator or owner.
    Items are included only for completed orders (pending orders have none).
    The reason field is populated for cancelled/corrected orders.
    """
    if current_user.role not in ("cocinero", "owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    order = _get_order_or_404(session, order_id)
    return _order_to_detail(session, order)
