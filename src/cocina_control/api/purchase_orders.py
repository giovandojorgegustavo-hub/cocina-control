"""Purchase-order endpoints — Backend #2 Slice 2b.

Routes
------
EP-1  POST   /api/v1/purchase-orders                          — create order (owner|admin)
EP-2  GET    /api/v1/purchase-orders                          — list orders (owner|admin)
EP-4  GET    /api/v1/purchase-orders/pending                  — cocinero bandeja (cocinero|admin)
EP-3  GET    /api/v1/purchase-orders/{order_id}               — order detail (owner|admin)
EP-5  GET    /api/v1/purchase-orders/{order_id}/partida-draft — draft view (cocinero|admin)
EP-6  POST   /api/v1/purchase-orders/{order_id}/partidas      — validate partida (cocinero|admin)

Route ordering note
-------------------
EP-4 (/pending) MUST be declared BEFORE EP-3 (/{order_id}) so that FastAPI
matches the literal path segment "pending" before trying to parse it as a UUID.
FastAPI resolves routes in declaration order.

Regla de oro (requerimientos.md Principio 1)
--------------------------------------------
EP-4, EP-5, EP-6 are capture-screen endpoints.  Their response schemas must
NEVER include monetary fields (unit_cost, total_ordered, pending_amount, etc.).
This is enforced at the schema layer.  Tests verify it explicitly.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.api.deps import require_any_role
from cocina_control.db import get_session
from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.product import Product
from cocina_control.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderItemCost,
    PurchaseOrderStatusEvent,
)
from cocina_control.models.user import User
from cocina_control.schemas.purchase_order import (
    PurchaseOrderAnnulRequest,
    PurchaseOrderLineEditRequest,
    PurchaseOrderLineRemoveRequest,
    PurchaseOrderReceivedPartida,
    PartidaCreate,
    PartidaDraftItem,
    PartidaDraftResponse,
    PartidaResponse,
    PurchaseOrderCreate,
    PurchaseOrderDetailItem,
    PurchaseOrderDetailResponse,
    PurchaseOrderListItem,
    PurchaseOrderPendingItem,
)
from cocina_control.services.purchase_orders import (
    build_received_summary,
    build_pending_summary,
    compute_order_totals,
    derive_status,
    get_active_cost,
    get_active_items,
    get_partida_count,
    get_received_qty_by_item,
)

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_order_or_404(session: Session, order_id: uuid.UUID) -> PurchaseOrder:
    order = session.get(PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase order not found",
        )
    return order


def _validate_products_for_order(
    session: Session, items: list
) -> dict[uuid.UUID, Product]:
    """Validate that all product_ids exist and are active.

    Returns {product_id: Product} map.
    Raises 400 listing invalid IDs.
    """
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


def _build_detail_response(
    session: Session,
    order: PurchaseOrder,
) -> PurchaseOrderDetailResponse:
    """Build a PurchaseOrderDetailResponse from the order and DB state."""
    from cocina_control.models.user import User as UserModel

    creator = session.get(UserModel, order.created_by)
    created_by_name = creator.name if creator else str(order.created_by)

    derived_status = derive_status(session, order.id)
    totals = compute_order_totals(session, order.id)
    partida_count = get_partida_count(session, order.id)

    items = [
        PurchaseOrderDetailItem(
            id=it["id"],
            product_id=it["product_id"],
            product_name=it["product_name"],
            unit=it["unit"],
            expected_qty=it["expected_qty"],
            unit_cost=it["unit_cost"],
            received_qty=it["received_qty"],
            pending_qty=it["pending_qty"],
            line_total=it["line_total"],
        )
        for it in totals["items"]
    ]

    return PurchaseOrderDetailResponse(
        id=order.id,
        supplier_name=order.supplier_name,
        created_at=order.created_at,
        created_by_name=created_by_name,
        derived_status=derived_status,
        items=items,
        total_ordered=totals["total_ordered"],
        total_received=totals["total_received"],
        pending_amount=totals["pending_amount"],
        partida_count=partida_count,
    )


# ---------------------------------------------------------------------------
# EP-1: POST /purchase-orders
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=PurchaseOrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new purchase order (owner or admin)",
)
def create_purchase_order(
    body: PurchaseOrderCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("owner", "admin")),
) -> PurchaseOrderDetailResponse:
    """Owner or admin creates a purchase order with items and costs.

    Validations:
    - supplier_name not blank (enforced by schema).
    - At least 1 item (enforced by schema).
    - No duplicate product_ids (enforced by schema model_validator).
    - expected_qty > 0, unit_cost > 0 (enforced by schema Field constraints).
    - All product_ids must exist and be active (validated below).

    Everything is created in a single transaction (flush at the end).
    Returns 201 with the full detail response.
    """
    products = _validate_products_for_order(session, body.items)

    order = PurchaseOrder(
        id=uuid.uuid4(),
        supplier_name=body.supplier_name,
        created_by=current_user.id,
    )
    session.add(order)
    session.flush()  # obtain order.id

    for item_in in body.items:
        po_item = PurchaseOrderItem(
            id=uuid.uuid4(),
            purchase_order_id=order.id,
            product_id=item_in.product_id,
            expected_qty=item_in.expected_qty,
            created_by=current_user.id,
        )
        session.add(po_item)
        session.flush()  # obtain po_item.id for cost FK

        cost = PurchaseOrderItemCost(
            id=uuid.uuid4(),
            purchase_order_item_id=po_item.id,
            unit_cost=item_in.unit_cost,
            created_by=current_user.id,
        )
        session.add(cost)

    session.flush()
    # Suppress unused variable for products — used to validate, map is not needed further.
    _ = products
    return _build_detail_response(session, order)


# ---------------------------------------------------------------------------
# EP-2: GET /purchase-orders
# ---------------------------------------------------------------------------

_ALL_STATUSES: set[str] = {"open", "partially_received", "closed", "annulled", "all"}


@router.get(
    "",
    response_model=list[PurchaseOrderListItem],
    summary="List purchase orders (owner or admin)",
)
def list_purchase_orders(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("owner", "admin")),
    status_filter: Annotated[
        Literal["open", "partially_received", "closed", "annulled", "all"],
        Query(alias="status"),
    ] = "all",
) -> list[PurchaseOrderListItem]:
    """Return all purchase orders, newest first.

    Optional ?status= filter (open|partially_received|closed|annulled|all).
    Derived status is computed on the fly for each order.
    No pagination in v0.3.0.
    """
    orders = session.scalars(
        select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    ).all()

    if not orders:
        return []

    result: list[PurchaseOrderListItem] = []
    for order in orders:
        derived = derive_status(session, order.id)

        if status_filter != "all" and derived != status_filter:
            continue

        totals = compute_order_totals(session, order.id)
        active_items = get_active_items(session, order.id)

        pending_summary: str | None = None
        if derived == "partially_received":
            pending_summary = build_pending_summary(session, order.id)

        result.append(
            PurchaseOrderListItem(
                id=order.id,
                supplier_name=order.supplier_name,
                created_at=order.created_at,
                derived_status=derived,
                item_count=len(active_items),
                total_ordered=totals["total_ordered"],
                total_received=totals["total_received"],
                pending_amount=totals["pending_amount"],
                pending_summary=pending_summary,
            )
        )

    return result


# ---------------------------------------------------------------------------
# EP-4: GET /purchase-orders/pending   (MUST be before /{order_id})
# ---------------------------------------------------------------------------


@router.get(
    "/pending",
    response_model=list[PurchaseOrderPendingItem],
    summary="Cocinero bandeja: orders with pending deliveries (cocinero or admin)",
)
def list_pending_orders(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("cocinero", "admin")),
) -> list[PurchaseOrderPendingItem]:
    """Return orders that are 'open' or 'partially_received' — cocinero capture screen.

    CRITICAL: Response contains ZERO monetary fields (regla de oro).
    Schema PurchaseOrderPendingItem has no unit_cost, no total_*, no pending_amount.
    """
    orders = session.scalars(
        select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    ).all()

    result: list[PurchaseOrderPendingItem] = []
    for order in orders:
        derived = derive_status(session, order.id)
        if derived not in ("open", "partially_received"):
            continue

        if derived == "open":
            summary = "todo pendiente"
        else:
            summary = build_pending_summary(session, order.id) or "pendiente"

        result.append(
            PurchaseOrderPendingItem(
                id=order.id,
                supplier_name=order.supplier_name,
                created_at=order.created_at,
                derived_status=derived,  # type: ignore[arg-type]
                pending_items_summary=summary,
            )
        )

    return result


# ---------------------------------------------------------------------------
# Edicion de ordenes (issue #101) — reglas del dueño:
#   - orden SIN recepciones: se edita todo, incluida la eliminacion de lineas
#   - orden CON recepciones: no se desarma — se anula con motivo
# ---------------------------------------------------------------------------


def _assert_order_editable(session: Session, order: PurchaseOrder) -> None:
    """La edicion de lineas solo aplica a ordenes abiertas sin recepciones."""
    derived = derive_status(session, order.id)
    if derived != "open":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Only open orders can be edited", "derived_status": derived},
        )
    if get_partida_count(session, order.id) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Order has received partidas — annul instead of editing"},
        )


def _get_active_item_or_404(
    session: Session, order: PurchaseOrder, item_id: uuid.UUID
) -> PurchaseOrderItem:
    active = {i.id: i for i in get_active_items(session, order.id)}
    item = active.get(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order line not found or not active",
        )
    return item


@router.post(
    "/{order_id}/annul",
    response_model=PurchaseOrderDetailResponse,
    summary="Annul an order with mandatory reason (owner or admin)",
)
def annul_purchase_order(
    order_id: uuid.UUID,
    body: PurchaseOrderAnnulRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("owner", "admin")),
) -> PurchaseOrderDetailResponse:
    order = _get_order_or_404(session, order_id)
    derived = derive_status(session, order.id)
    if derived in ("annulled", "closed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": f"Order is already {derived}"},
        )
    event = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=order.id,
        event_type="annulled",
        reason=body.reason,
        created_by=current_user.id,
    )
    session.add(event)
    session.flush()
    return _build_detail_response(session, order)


@router.post(
    "/{order_id}/items/{item_id}/remove",
    response_model=PurchaseOrderDetailResponse,
    summary="Remove a line from an open order without receptions (owner or admin)",
)
def remove_purchase_order_line(
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    body: PurchaseOrderLineRemoveRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("owner", "admin")),
) -> PurchaseOrderDetailResponse:
    order = _get_order_or_404(session, order_id)
    _assert_order_editable(session, order)
    item = _get_active_item_or_404(session, order, item_id)

    # Correccion append-only: la cantidad copia la anterior (CHECK qty > 0);
    # removed=true marca la linea como quitada. get_active_items la filtra.
    removal = PurchaseOrderItem(
        id=uuid.uuid4(),
        purchase_order_id=order.id,
        product_id=item.product_id,
        expected_qty=item.expected_qty,
        removed=True,
        corrects_id=item.id,
        reason=body.reason,
        created_by=current_user.id,
    )
    session.add(removal)
    session.flush()
    return _build_detail_response(session, order)


@router.patch(
    "/{order_id}/items/{item_id}",
    response_model=PurchaseOrderDetailResponse,
    summary="Edit qty and/or unit cost of a line, append-only (owner or admin)",
)
def edit_purchase_order_line(
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    body: PurchaseOrderLineEditRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("owner", "admin")),
) -> PurchaseOrderDetailResponse:
    order = _get_order_or_404(session, order_id)
    _assert_order_editable(session, order)
    item = _get_active_item_or_404(session, order, item_id)

    target_item = item
    if body.expected_qty is not None:
        correction = PurchaseOrderItem(
            id=uuid.uuid4(),
            purchase_order_id=order.id,
            product_id=item.product_id,
            expected_qty=body.expected_qty,
            removed=False,
            corrects_id=item.id,
            reason=body.reason,
            created_by=current_user.id,
        )
        session.add(correction)
        session.flush()
        target_item = correction
        # La cadena de costos vive por item: el item nuevo arranca su cadena
        # copiando el costo vigente (o el editado en este mismo request).
        new_cost = body.unit_cost if body.unit_cost is not None else get_active_cost(session, item.id)
        session.add(
            PurchaseOrderItemCost(
                id=uuid.uuid4(),
                purchase_order_item_id=target_item.id,
                unit_cost=new_cost,
                reason=body.reason,
                created_by=current_user.id,
            )
        )
        session.flush()
    elif body.unit_cost is not None:
        # Solo costo: correccion en la cadena de costos del item vigente.
        all_costs = session.scalars(
            select(PurchaseOrderItemCost).where(
                PurchaseOrderItemCost.purchase_order_item_id == item.id
            )
        ).all()
        corrected = {c.corrects_id for c in all_costs if c.corrects_id is not None}
        leaf = next((c for c in all_costs if c.id not in corrected), None)
        session.add(
            PurchaseOrderItemCost(
                id=uuid.uuid4(),
                purchase_order_item_id=item.id,
                unit_cost=body.unit_cost,
                corrects_id=leaf.id if leaf else None,
                reason=body.reason,
                created_by=current_user.id,
            )
        )
        session.flush()

    return _build_detail_response(session, order)


# ---------------------------------------------------------------------------
# GET /purchase-orders/received — historial de partidas (issue #146)
# ---------------------------------------------------------------------------


@router.get(
    "/received",
    response_model=list[PurchaseOrderReceivedPartida],
    summary="Cocinero bandeja: historial de partidas recibidas (cocinero or admin)",
)
def list_received_partidas(
    limit: int = Query(default=30, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("cocinero", "admin")),
) -> list[PurchaseOrderReceivedPartida]:
    """Partidas validadas de ordenes de compra, mas recientes primero.

    CRITICAL: sin campos monetarios (regla de oro — pantalla de cocinero).
    """
    from cocina_control.models.delivery import Delivery

    deliveries = session.scalars(
        select(Delivery)
        .where(
            Delivery.purchase_order_id.is_not(None),
            Delivery.status == "validada",
        )
        .order_by(Delivery.validated_at.desc())
        .limit(limit)
    ).all()

    validator_ids = list({d.validated_by for d in deliveries if d.validated_by})
    validators: dict = {}
    if validator_ids:
        validators = {
            u.id: u.name
            for u in session.scalars(
                select(User).where(User.id.in_(validator_ids))
            ).all()
        }

    return [
        PurchaseOrderReceivedPartida(
            id=d.id,
            supplier_name=d.supplier_name,
            validated_at=d.validated_at,
            validated_by_name=validators.get(d.validated_by),
            received_summary=build_received_summary(session, d.id),
        )
        for d in deliveries
        if d.validated_at is not None
    ]


# ---------------------------------------------------------------------------
# EP-3: GET /purchase-orders/{order_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{order_id}",
    response_model=PurchaseOrderDetailResponse,
    summary="Get purchase order detail (owner or admin)",
)
def get_purchase_order(
    order_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("owner", "admin")),
) -> PurchaseOrderDetailResponse:
    """Return the full detail of a purchase order including items, totals, and status."""
    order = _get_order_or_404(session, order_id)
    return _build_detail_response(session, order)


# ---------------------------------------------------------------------------
# EP-5: GET /purchase-orders/{order_id}/partida-draft
# ---------------------------------------------------------------------------


@router.get(
    "/{order_id}/partida-draft",
    response_model=PartidaDraftResponse,
    summary="Get partida draft view (cocinero or admin)",
)
def get_partida_draft(
    order_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("cocinero", "admin")),
) -> PartidaDraftResponse:
    """Return the pre-populated draft for a new partida (capture screen).

    Shows each item's pending_qty and already_received — NO monetary fields.
    Returns 404 if order not found.
    Returns 409 if order is 'closed' or 'annulled'.
    Does NOT create any DB record.
    """
    order = _get_order_or_404(session, order_id)
    derived = derive_status(session, order.id)

    if derived in ("closed", "annulled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot start a partida on a {derived} order",
        )

    active_items = get_active_items(session, order.id)
    received = get_received_qty_by_item(session, order.id)
    partida_number = get_partida_count(session, order.id) + 1

    # Resolve products.
    product_ids = list({i.product_id for i in active_items})
    products: dict[uuid.UUID, Product] = {}
    if product_ids:
        products = {
            p.id: p
            for p in session.scalars(
                select(Product).where(Product.id.in_(product_ids))
            ).all()
        }

    from decimal import Decimal

    items = []
    for item in active_items:
        product = products.get(item.product_id)
        expected = Decimal(str(item.expected_qty))
        recv = received.get(item.id, Decimal("0"))
        items.append(
            PartidaDraftItem(
                purchase_order_item_id=item.id,
                product_id=item.product_id,
                product_name=product.name if product else "",
                unit=product.unit if product else "",
                pending_qty=expected - recv,
                already_received=recv,
            )
        )

    return PartidaDraftResponse(
        order_id=order.id,
        supplier_name=order.supplier_name,
        partida_number=partida_number,
        items=items,
    )


# ---------------------------------------------------------------------------
# EP-6: POST /purchase-orders/{order_id}/partidas
# ---------------------------------------------------------------------------


@router.post(
    "/{order_id}/partidas",
    response_model=PartidaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Validate a partida (cocinero or admin)",
)
def create_partida(
    order_id: uuid.UUID,
    body: PartidaCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_any_role("cocinero", "admin")),
) -> PartidaResponse:
    """Record a partida (batch delivery) for a purchase order.

    Validations:
    - Order must exist (404).
    - Order must be 'open' or 'partially_received' (409 otherwise).
    - All purchase_order_item_ids in body must be leaves (vigentes) of this order.
    - Body must cover ALL vigent items — no missing, no extra.
    - received_qty >= 0 (enforced by schema).

    Creates (in one transaction):
    - Delivery (status='validada', purchase_order_id=order.id)
    - DeliveryItem per body item (purchase_order_item_id set)
    - PurchaseOrderStatusEvent 'closed_auto' if all pending_qty <= 0 after partida.

    Returns 201 with PartidaResponse (no monetary fields).
    """
    from decimal import Decimal

    order = _get_order_or_404(session, order_id)
    derived = derive_status(session, order.id)

    if derived in ("closed", "annulled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot add a partida to a {derived} order",
        )

    # Validate that all body item ids are leaves of this order.
    active_items = get_active_items(session, order.id)
    active_item_ids = {i.id for i in active_items}
    active_item_map = {i.id: i for i in active_items}

    body_item_ids = {it.purchase_order_item_id for it in body.items}

    # Check for items not belonging to this order or not vigent.
    invalid_ids = [str(iid) for iid in body_item_ids if iid not in active_item_ids]
    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Some purchase_order_item_ids are invalid or not active for this order",
                "invalid_ids": invalid_ids,
            },
        )

    # Body must cover ALL active items — no more, no less.
    if body_item_ids != active_item_ids:
        missing = [str(iid) for iid in active_item_ids if iid not in body_item_ids]
        extra = [str(iid) for iid in body_item_ids if iid not in active_item_ids]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Body must cover all active items of the order",
                "missing_ids": missing,
                "extra_ids": extra,
            },
        )

    now = datetime.now(UTC)

    # Get current received totals (before this partida) to compute announced_qty.
    received_before = get_received_qty_by_item(session, order.id)
    partida_number = get_partida_count(session, order.id) + 1

    # Resolve product_id per active item.
    product_ids = list({i.product_id for i in active_items})
    products: dict[uuid.UUID, Product] = {}
    if product_ids:
        products = {
            p.id: p
            for p in session.scalars(
                select(Product).where(Product.id.in_(product_ids))
            ).all()
        }

    # Create the Delivery (partida).
    delivery = Delivery(
        id=uuid.uuid4(),
        supplier_name=order.supplier_name,
        status="validada",
        created_by=current_user.id,
        validated_at=now,
        validated_by=current_user.id,
        purchase_order_id=order.id,
    )
    session.add(delivery)
    session.flush()  # obtain delivery.id

    # Map body items for quick lookup.
    body_map = {it.purchase_order_item_id: it for it in body.items}

    # Create DeliveryItem per body entry.
    for po_item in active_items:
        body_item = body_map[po_item.id]
        po_item_obj = active_item_map[po_item.id]
        expected = Decimal(str(po_item_obj.expected_qty))
        already_recv = received_before.get(po_item.id, Decimal("0"))
        # announced_qty = pending at the time this partida was started.
        announced_qty = max(expected - already_recv, Decimal("0"))
        # announced_qty must be > 0 per the DB CHECK constraint.
        # If already fully received, use a small positive value to satisfy constraint.
        # In practice this shouldn't happen (order would be closed), but be defensive.
        if announced_qty <= Decimal("0"):
            announced_qty = expected  # fallback: use expected_qty

        di = DeliveryItem(
            id=uuid.uuid4(),
            delivery_id=delivery.id,
            product_id=po_item_obj.product_id,
            announced_qty=announced_qty,
            received_qty=body_item.received_qty,
            created_by=current_user.id,
            confirmed_at=now,
            confirmed_by=current_user.id,
            purchase_order_item_id=po_item.id,
        )
        session.add(di)

    session.flush()

    # Recalculate saldo post-partida to determine if auto-close applies.
    received_after = get_received_qty_by_item(session, order.id)

    all_done = all(
        Decimal(str(item.expected_qty)) - received_after.get(item.id, Decimal("0")) <= Decimal("0")
        for item in active_items
    )

    if all_done:
        event = PurchaseOrderStatusEvent(
            id=uuid.uuid4(),
            purchase_order_id=order.id,
            event_type="closed_auto",
            created_by=current_user.id,
        )
        session.add(event)
        session.flush()

    # derive_status is the single source of truth — never compute status locally.
    new_order_status = derive_status(session, order.id)

    return PartidaResponse(
        delivery_id=delivery.id,
        partida_number=partida_number,
        order_id=order.id,
        order_status=new_order_status,
    )
