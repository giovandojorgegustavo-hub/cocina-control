"""Purchase-order service helpers — shared by EP-2 through EP-6.

All helpers are pure query functions: they read from the DB and return typed
Python values.  No writes happen here; mutations live in the router layer.

Key design rules from decisiones-orden-compra.md:
- P3: active (leaf) items are identified by NOT EXISTS (corrects_id points to me).
      Do NOT use corrects_id IS NULL — that finds the root, not the leaf.
- P8: derived status is computed from the event log + saldo, never from a column.
- FIFO / costs are NOT this service's responsibility (Backend #3).
"""

import uuid
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.product import Product
from cocina_control.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderItemCost,
    PurchaseOrderStatusEvent,
)

_ZERO = Decimal("0")

DerivedStatus = Literal["open", "partially_received", "closed", "annulled"]

# ---------------------------------------------------------------------------
# Item / cost helpers
# ---------------------------------------------------------------------------


def get_active_items(session: Session, order_id: uuid.UUID) -> list[PurchaseOrderItem]:
    """Return the leaf (active) items of a purchase order.

    A leaf row is one that no other row's corrects_id points to.
    Decision P3: NOT EXISTS pattern — corrects_id IS NULL would return the root.
    """
    all_items = session.scalars(
        select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order_id)
    ).all()

    if not all_items:
        return []

    corrected_ids = {i.corrects_id for i in all_items if i.corrects_id is not None}
    return [i for i in all_items if i.id not in corrected_ids]


def get_active_cost(session: Session, item_id: uuid.UUID) -> Decimal:
    """Return the current unit_cost of a purchase_order_item (leaf of the cost chain).

    If no cost row exists (data integrity issue) returns 0 defensively.
    """
    all_costs = session.scalars(
        select(PurchaseOrderItemCost).where(
            PurchaseOrderItemCost.purchase_order_item_id == item_id
        )
    ).all()

    if not all_costs:
        return _ZERO

    corrected_ids = {c.corrects_id for c in all_costs if c.corrects_id is not None}
    leaf_costs = [c for c in all_costs if c.id not in corrected_ids]

    if not leaf_costs:
        return _ZERO

    # There should be exactly one leaf (UNIQUE corrects_id guarantees no bifurcation).
    return Decimal(str(leaf_costs[0].unit_cost))


def get_received_qty_by_item(
    session: Session, order_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Return {purchase_order_item_id: Σ received_qty} from validated partidas.

    Only leaf delivery_items in validated deliveries count.  Corrections
    (non-leaf items) are superseded and must not be double-counted.

    Returns a defaultdict-style dict: missing keys mean 0 received.
    """
    # Fetch all validated deliveries for this order.
    deliveries = session.scalars(
        select(Delivery).where(
            Delivery.purchase_order_id == order_id,
            Delivery.status == "validada",
        )
    ).all()

    if not deliveries:
        return {}

    delivery_ids = [d.id for d in deliveries]

    # Fetch all delivery_items that reference a PO item.
    di_rows = session.scalars(
        select(DeliveryItem).where(
            DeliveryItem.delivery_id.in_(delivery_ids),
            DeliveryItem.purchase_order_item_id.is_not(None),
        )
    ).all()

    if not di_rows:
        return {}

    # Compute leaf set (items not corrected by another item in same delivery).
    corrected_ids = {i.corrects_id for i in di_rows if i.corrects_id is not None}

    totals: dict[uuid.UUID, Decimal] = {}
    for item in di_rows:
        if item.id in corrected_ids:
            continue  # superseded
        po_item_id = item.purchase_order_item_id
        if po_item_id is None:
            continue
        qty = item.received_qty if item.received_qty is not None else _ZERO
        totals[po_item_id] = totals.get(po_item_id, _ZERO) + qty

    return totals


# ---------------------------------------------------------------------------
# Status derivation
# ---------------------------------------------------------------------------


def derive_status(session: Session, order_id: uuid.UUID) -> DerivedStatus:
    """Derive the current lifecycle status of a purchase order.

    Priority (from decision P8):
    1. Last event is 'annulled'                    → 'annulled'
    2. Last event is 'closed_auto' or 'closed_manual' → 'closed'
    3. No terminal event + Σ received > 0 for any item → 'partially_received'
    4. Else                                         → 'open'

    Defensive case: no terminal event but all pending_qty <= 0 → 'closed'
    (auto-close should have emitted the event; this prevents showing a
    completed order as 'open' if the event write failed in production).
    """
    # Fetch latest event (the DESC index on created_at makes this cheap).
    last_event = session.scalars(
        select(PurchaseOrderStatusEvent)
        .where(PurchaseOrderStatusEvent.purchase_order_id == order_id)
        .order_by(PurchaseOrderStatusEvent.created_at.desc())
        .limit(1)
    ).first()

    if last_event is not None:
        if last_event.event_type == "annulled":
            return "annulled"
        if last_event.event_type in ("closed_auto", "closed_manual"):
            return "closed"
        # 'reopened' → fall through to saldo check below.

    # No terminal event (or last event was 'reopened'): check saldo.
    active_items = get_active_items(session, order_id)
    if not active_items:
        # Defensive: order with no items → treat as open.
        return "open"

    received = get_received_qty_by_item(session, order_id)

    total_received = sum(received.values(), _ZERO)

    if total_received == _ZERO:
        return "open"

    # Check if all items are fully received (pending_qty <= 0 for all).
    all_done = all(
        item.expected_qty - received.get(item.id, _ZERO) <= _ZERO
        for item in active_items
    )
    if all_done:
        # Defensive: should have been closed by EP-6, but protect the invariant.
        return "closed"

    return "partially_received"


# ---------------------------------------------------------------------------
# Totals computation
# ---------------------------------------------------------------------------


def compute_order_totals(session: Session, order_id: uuid.UUID) -> dict:
    """Return monetary totals and item details for a purchase order.

    Returns:
        {
            'total_ordered':  Decimal  — Σ(expected_qty × unit_cost) vigentes
            'total_received': Decimal  — Σ(min(received_qty, expected_qty) × unit_cost)
            'pending_amount': Decimal  — total_ordered - total_received
            'items': list[dict]        — one dict per active item with detail fields
        }

    Excess qty (received > expected) is NOT valorized for total_received
    (spec: "el exceso NO se valoriza").
    """
    active_items = get_active_items(session, order_id)
    received = get_received_qty_by_item(session, order_id)

    # Resolve products in a single query.
    product_ids = list({i.product_id for i in active_items})
    products: dict[uuid.UUID, Product] = {}
    if product_ids:
        products = {
            p.id: p
            for p in session.scalars(
                select(Product).where(Product.id.in_(product_ids))
            ).all()
        }

    total_ordered = _ZERO
    total_received = _ZERO
    items = []

    for item in active_items:
        cost = get_active_cost(session, item.id)
        expected = Decimal(str(item.expected_qty))
        recv = received.get(item.id, _ZERO)
        pending = expected - recv

        line_total = expected * cost
        # Cap received valorization at expected (no excess valorization).
        received_capped = min(recv, expected) if recv > _ZERO else _ZERO
        received_value = received_capped * cost

        total_ordered += line_total
        total_received += received_value

        product = products.get(item.product_id)
        items.append(
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_name": product.name if product else "",
                "unit": product.unit if product else "",
                "expected_qty": expected,
                "unit_cost": cost,
                "received_qty": recv,
                "pending_qty": pending,
                "line_total": line_total,
            }
        )

    pending_amount = total_ordered - total_received

    return {
        "total_ordered": total_ordered,
        "total_received": total_received,
        "pending_amount": pending_amount,
        "items": items,
    }


# ---------------------------------------------------------------------------
# Pending summary string
# ---------------------------------------------------------------------------


def build_pending_summary(session: Session, order_id: uuid.UUID) -> str | None:
    """Return a human-readable summary of still-pending items.

    Example: "faltan 40 kg POLLO · 2 kg CEBOLLA"
    Returns None if no items have pending_qty > 0 (order effectively done).
    """
    active_items = get_active_items(session, order_id)
    if not active_items:
        return None

    received = get_received_qty_by_item(session, order_id)

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

    parts = []
    for item in active_items:
        pending = Decimal(str(item.expected_qty)) - received.get(item.id, _ZERO)
        if pending <= _ZERO:
            continue
        product = products.get(item.product_id)
        unit = product.unit if product else "u"
        name = product.name if product else str(item.product_id)
        # Format: remove trailing zeros without scientific notation.
        # Use quantize to a small precision then strip; handles integers cleanly.
        # e.g. Decimal("40") → "40", Decimal("1.50") → "1.5", Decimal("0.25") → "0.25"
        pending_str = f"{pending:.10f}".rstrip("0").rstrip(".")
        parts.append(f"{pending_str} {unit} {name}")

    if not parts:
        return None

    return "faltan " + " · ".join(parts)


# ---------------------------------------------------------------------------
# Received summary helper (issue #146)
# ---------------------------------------------------------------------------


def build_received_summary(session: Session, delivery_id: uuid.UUID) -> str:
    """Resumen humano de lo recibido en una partida validada.

    Ejemplo: "18 kg CERDO · 40 kg POLLO". Sin montos (pantalla de cocinero).
    """
    from cocina_control.models.delivery import DeliveryItem

    items = session.scalars(
        select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)
    ).all()
    if not items:
        return "sin detalle"

    product_ids = list({i.product_id for i in items})
    products: dict[uuid.UUID, Product] = {
        p.id: p
        for p in session.scalars(
            select(Product).where(Product.id.in_(product_ids))
        ).all()
    }

    parts = []
    for item in items:
        qty = item.received_qty if item.received_qty is not None else item.announced_qty
        product = products.get(item.product_id)
        unit = product.unit if product else "u"
        name = product.name if product else str(item.product_id)
        qty_str = f"{qty:.10f}".rstrip("0").rstrip(".")
        parts.append(f"{qty_str} {unit} {name}")

    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Partida count helper
# ---------------------------------------------------------------------------


def get_partida_count(session: Session, order_id: uuid.UUID) -> int:
    """Return the number of validated deliveries (partidas) for this order."""
    deliveries = session.scalars(
        select(Delivery).where(
            Delivery.purchase_order_id == order_id,
            Delivery.status == "validada",
        )
    ).all()
    return len(deliveries)
