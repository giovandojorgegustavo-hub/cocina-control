"""Dashboard calculation service (issue #14).

This module implements the two heavy calculations for the summary endpoint:

1. stock_now — the "current stock" for a product, defined as:

       stock_now = last_completed_count_qty
                 + sum(validated_delivery_received_qty since last_count)
                 - sum(completed_order_qty since last_count)

   Where "last completed count" is the LATEST inventory_count_item leaf row
   of a COMPLETED count, regardless of date.  If no completed count exists
   at all, the product has no stock reference: stock_now = Decimal("0") and
   a note field is set accordingly.  At v0.1 volume this O(products × events)
   scan is acceptable; a materialized view can be added later.

2. consumption — the period-range consumption:

       consumption = stock_inicio + entries_qty - stock_actual

   Where:
   - stock_inicio  = qty from the latest completed count leaf BEFORE `from_dt`
                     (strictly before). None → consumption_available = False.
   - entries_qty   = sum of received_qty (or announced_qty when received is NULL)
                     of LEAF delivery_items whose parent delivery is `validada`
                     and whose delivery.validated_at is IN [from_dt, to_dt].
   - stock_actual  = qty from the latest completed count leaf whose count
                     completed_at is IN [from_dt, to_dt].  If no count exists
                     IN the range, stock_actual = stock_inicio (meaning "no new
                     count was done, stock is unknown at period end").

   alert = True when consumption < 0 (stock grew without registered entries)
           OR when stock_actual > stock_inicio + entries_qty (same condition,
           different expression).

3. low_stock — products with low_stock_threshold != NULL and
   stock_now < low_stock_threshold.

All queries use SQLAlchemy core-style filtering; no ORM relationships are loaded
to avoid N+1 problems.  leaf_ids sets are computed once per product and reused.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.delivery_order import DeliveryOrder, DeliveryOrderItem
from cocina_control.models.inventory import InventoryCount, InventoryCountItem
from cocina_control.models.product import Product
from cocina_control.models.user import User
from cocina_control.schemas.dashboard import (
    DashboardSummaryResponse,
    LowStockItem,
    OrdersSummary,
    ProductSummaryItem,
    TraceabilityEvent,
)

_ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _leaf_ids_for_items(items: list) -> set[uuid.UUID]:
    """Return the set of IDs that are NOT corrected by any other item.

    An item is a 'leaf' if no other item points to it via corrects_id.
    Used to determine the current (most-recent) value of each product
    in append-only tables.
    """
    corrected = {i.corrects_id for i in items if i.corrects_id is not None}
    return {i.id for i in items if i.id not in corrected}


def _get_user_names(session: Session, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Return a map of user_id → user.name for the given IDs."""
    if not user_ids:
        return {}
    users = session.scalars(select(User).where(User.id.in_(user_ids))).all()
    return {u.id: u.name for u in users}


def _last_completed_count_item_before(
    session: Session, product_id: uuid.UUID, before_dt: datetime
) -> Decimal | None:
    """Return the quantity of the latest leaf inventory_count_item for product_id
    whose parent count is 'completed' and completed_at < before_dt.

    Returns None if no such count exists.
    """
    # Fetch all completed counts completed strictly before before_dt.
    counts = session.scalars(
        select(InventoryCount).where(
            InventoryCount.status == "completed",
            InventoryCount.completed_at < before_dt,
        )
    ).all()
    if not counts:
        return None

    count_ids = [c.id for c in counts]

    # Fetch all count_items for those counts and this product.
    items = session.scalars(
        select(InventoryCountItem).where(
            InventoryCountItem.inventory_count_id.in_(count_ids),
            InventoryCountItem.product_id == product_id,
        )
    ).all()
    if not items:
        return None

    leaf_ids = _leaf_ids_for_items(items)
    leaf_items = [i for i in items if i.id in leaf_ids]
    if not leaf_items:
        return None

    # Among leaf items, find the one from the latest count (by completed_at).
    count_map = {c.id: c for c in counts}
    # Sort by the completed_at of the parent count, descending.
    leaf_items.sort(
        key=lambda i: count_map[i.inventory_count_id].completed_at or datetime.min,
        reverse=True,
    )
    return leaf_items[0].quantity


def _last_completed_count_item_in_range(
    session: Session, product_id: uuid.UUID, from_dt: datetime, to_dt: datetime
) -> Decimal | None:
    """Return the quantity of the latest leaf inventory_count_item for product_id
    whose parent count is 'completed' and completed_at IN [from_dt, to_dt].

    Returns None if no such count exists in the range.
    """
    counts = session.scalars(
        select(InventoryCount).where(
            InventoryCount.status == "completed",
            InventoryCount.completed_at >= from_dt,
            InventoryCount.completed_at <= to_dt,
        )
    ).all()
    if not counts:
        return None

    count_ids = [c.id for c in counts]
    items = session.scalars(
        select(InventoryCountItem).where(
            InventoryCountItem.inventory_count_id.in_(count_ids),
            InventoryCountItem.product_id == product_id,
        )
    ).all()
    if not items:
        return None

    leaf_ids = _leaf_ids_for_items(items)
    leaf_items = [i for i in items if i.id in leaf_ids]
    if not leaf_items:
        return None

    count_map = {c.id: c for c in counts}
    leaf_items.sort(
        key=lambda i: count_map[i.inventory_count_id].completed_at or datetime.min,
        reverse=True,
    )
    return leaf_items[0].quantity


def _entries_qty_in_range(
    session: Session, product_id: uuid.UUID, from_dt: datetime, to_dt: datetime
) -> Decimal:
    """Sum of received_qty (or announced_qty fallback) of leaf delivery_items
    whose parent delivery is 'validada' and validated_at IN [from_dt, to_dt].

    Only leaf items are counted (corrections supersede originals).
    The fallback to announced_qty is defensive; all validated deliveries
    should have received_qty set by the time validation occurs.
    """
    validated_deliveries = session.scalars(
        select(Delivery).where(
            Delivery.status == "validada",
            Delivery.validated_at >= from_dt,
            Delivery.validated_at <= to_dt,
        )
    ).all()
    if not validated_deliveries:
        return _ZERO

    delivery_ids = [d.id for d in validated_deliveries]
    items = session.scalars(
        select(DeliveryItem).where(
            DeliveryItem.delivery_id.in_(delivery_ids),
            DeliveryItem.product_id == product_id,
        )
    ).all()
    if not items:
        return _ZERO

    leaf_ids = _leaf_ids_for_items(items)
    total = _ZERO
    for item in items:
        if item.id in leaf_ids:
            qty = item.received_qty if item.received_qty is not None else item.announced_qty
            total += qty
    return total


def _entries_qty_since(
    session: Session, product_id: uuid.UUID, since_dt: datetime
) -> Decimal:
    """Sum of received_qty (or announced_qty fallback) of leaf delivery_items
    whose parent delivery is 'validada' and validated_at > since_dt (strict).

    The strict inequality avoids double-counting the boundary event when
    since_dt is the completed_at of the last inventory count: the count itself
    already captures the stock at that instant, so deliveries validated exactly
    AT that timestamp should not be counted again.

    Used by stock_now calculation.
    """
    validated_deliveries = session.scalars(
        select(Delivery).where(
            Delivery.status == "validada",
            Delivery.validated_at > since_dt,
        )
    ).all()
    if not validated_deliveries:
        return _ZERO

    delivery_ids = [d.id for d in validated_deliveries]
    items = session.scalars(
        select(DeliveryItem).where(
            DeliveryItem.delivery_id.in_(delivery_ids),
            DeliveryItem.product_id == product_id,
        )
    ).all()
    if not items:
        return _ZERO

    leaf_ids = _leaf_ids_for_items(items)
    total = _ZERO
    for item in items:
        if item.id in leaf_ids:
            qty = item.received_qty if item.received_qty is not None else item.announced_qty
            total += qty
    return total


def _orders_qty_since(
    session: Session, product_id: uuid.UUID, since_dt: datetime
) -> Decimal:
    """Sum of quantity of leaf delivery_order_items whose parent order is
    'completed' and completed_at > since_dt (strict).

    The strict inequality is symmetric with _entries_qty_since: avoids counting
    orders completed exactly AT the last-count timestamp, which would be
    inconsistent with the stock baseline captured by that count.

    Used by stock_now calculation.
    """
    completed_orders = session.scalars(
        select(DeliveryOrder).where(
            DeliveryOrder.status == "completed",
            DeliveryOrder.completed_at > since_dt,
        )
    ).all()
    if not completed_orders:
        return _ZERO

    order_ids = [o.id for o in completed_orders]
    items = session.scalars(
        select(DeliveryOrderItem).where(
            DeliveryOrderItem.delivery_order_id.in_(order_ids),
            DeliveryOrderItem.product_id == product_id,
        )
    ).all()
    if not items:
        return _ZERO

    leaf_ids = _leaf_ids_for_items(items)
    return sum((i.quantity for i in items if i.id in leaf_ids), _ZERO)


def _compute_stock_now(session: Session, product_id: uuid.UUID) -> Decimal:
    """Compute the current stock for a product.

    Algorithm:
      1. Find the latest completed inventory_count_item (leaf) for this product.
         That count_completed_at becomes the 'since' anchor.
      2. Add all validated delivery entries since that date (leaf items).
      3. Subtract all completed order items since that date (leaf items).

    If no completed count exists at all, there is no stock baseline: return 0.
    The caller may choose to show "unknown" in the UI for such products; for now
    0 is returned because the API contract doesn't expose a separate flag for
    stock_now availability (only consumption_available does that).
    """
    # Find the last completed count for this product (any date, no range filter).
    all_completed_counts = session.scalars(
        select(InventoryCount).where(InventoryCount.status == "completed")
    ).all()
    if not all_completed_counts:
        return _ZERO

    count_ids = [c.id for c in all_completed_counts]
    all_count_items = session.scalars(
        select(InventoryCountItem).where(
            InventoryCountItem.inventory_count_id.in_(count_ids),
            InventoryCountItem.product_id == product_id,
        )
    ).all()
    if not all_count_items:
        return _ZERO

    leaf_ids = _leaf_ids_for_items(all_count_items)
    leaf_items = [i for i in all_count_items if i.id in leaf_ids]
    if not leaf_items:
        return _ZERO

    count_map = {c.id: c for c in all_completed_counts}
    leaf_items.sort(
        key=lambda i: count_map[i.inventory_count_id].completed_at or datetime.min,
        reverse=True,
    )
    last_item = leaf_items[0]
    last_count_qty = last_item.quantity
    last_count_at = count_map[last_item.inventory_count_id].completed_at

    if last_count_at is None:
        return last_count_qty

    entries = _entries_qty_since(session, product_id, last_count_at)
    consumed = _orders_qty_since(session, product_id, last_count_at)

    return last_count_qty + entries - consumed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_summary(
    session: Session, from_dt: datetime, to_dt: datetime
) -> DashboardSummaryResponse:
    """Compute the full dashboard summary for the given date range.

    from_dt and to_dt must be timezone-aware datetimes converted from the
    user-supplied YYYY-MM-DD dates to the business timezone boundary:
      - from_dt = date at 00:00:00 local time (business timezone, default America/Lima)
      - to_dt   = date at 23:59:59.999999 local time

    Products:
      For each active product, compute:
      - stock_now (see _compute_stock_now)
      - entries_qty (validated deliveries in range)
      - consumption (stock_inicio + entries - stock_actual)
      - alert (consumption < 0)

    Low stock:
      Products with low_stock_threshold set and stock_now < threshold.

    Orders summary:
      Count of orders in the range by status.
    """
    products = session.scalars(
        select(Product).where(Product.is_active.is_(True))
    ).all()

    product_items: list[ProductSummaryItem] = []
    low_stock_items: list[LowStockItem] = []

    for product in products:
        stock_now = _compute_stock_now(session, product.id)

        # Consumption formula.
        stock_inicio = _last_completed_count_item_before(session, product.id, from_dt)
        entries_qty = _entries_qty_in_range(session, product.id, from_dt, to_dt)

        if stock_inicio is None:
            consumption_available = False
            consumption = None
            alert = False
        else:
            stock_actual_in_range = _last_completed_count_item_in_range(
                session, product.id, from_dt, to_dt
            )
            # If no count inside the range, use stock_inicio as the "unchanged" baseline.
            stock_actual = (
                stock_actual_in_range
                if stock_actual_in_range is not None
                else stock_inicio
            )
            consumption = stock_inicio + entries_qty - stock_actual
            consumption_available = True
            # Alert: stock grew without registered entries, or numbers don't add up.
            alert = consumption < _ZERO or stock_actual > stock_inicio + entries_qty

        product_items.append(
            ProductSummaryItem(
                id=product.id,
                name=product.name,
                unit=product.unit,
                stock_now=str(stock_now),
                entries_qty=str(entries_qty),
                consumption=str(consumption) if consumption is not None else None,
                consumption_available=consumption_available,
                alert=alert,
            )
        )

        # Low stock check.
        # Convert threshold to Decimal before comparison: the ORM may return a str
        # for objects that were not flushed to the DB yet (e.g. in tests).
        threshold = (
            Decimal(str(product.low_stock_threshold))
            if product.low_stock_threshold is not None
            else None
        )
        if threshold is not None and stock_now < threshold:
            low_stock_items.append(
                LowStockItem(
                    id=product.id,
                    name=product.name,
                    unit=product.unit,
                    stock_now=str(stock_now),
                    low_stock_threshold=str(product.low_stock_threshold),
                )
            )

    # Orders summary — counts use event-specific timestamps, not created_at.
    #
    # completed_count: leaf orders whose completed_at falls in [from_dt, to_dt].
    #   Using completed_at is consistent with the consumption calculation
    #   (_orders_qty_since uses completed_at) and represents when the order
    #   was actually fulfilled, not when it was opened.
    #
    # photo_only_count: leaf orders whose photo_at falls in [from_dt, to_dt]
    #   but whose completed_at is NULL or outside the range.  These are orders
    #   that were photographed (operator registered them) but never completed.
    #   Note: a "cancelled" order in this model is a pending order that has been
    #   superseded by a corrector row (corrects_id pointing to it).  The leaf
    #   filter already excludes such orders.
    completed_orders_in_range = session.scalars(
        select(DeliveryOrder).where(
            DeliveryOrder.status == "completed",
            DeliveryOrder.completed_at >= from_dt,
            DeliveryOrder.completed_at <= to_dt,
        )
    ).all()
    # Among completed orders, keep only leaf orders (not corrected by another).
    completed_corrected_ids = {
        o.corrects_id for o in completed_orders_in_range if o.corrects_id is not None
    }
    completed_count = sum(
        1 for o in completed_orders_in_range if o.id not in completed_corrected_ids
    )

    photo_only_orders_in_range = session.scalars(
        select(DeliveryOrder).where(
            DeliveryOrder.status == "pending",
            DeliveryOrder.photo_at >= from_dt,
            DeliveryOrder.photo_at <= to_dt,
        )
    ).all()
    # Leaf filter: exclude orders that have a corrector (cancelled originals).
    photo_corrected_ids = {
        o.corrects_id for o in photo_only_orders_in_range if o.corrects_id is not None
    }
    photo_only_count = sum(
        1 for o in photo_only_orders_in_range if o.id not in photo_corrected_ids
    )

    return DashboardSummaryResponse(
        products=product_items,
        low_stock=low_stock_items,
        orders_summary=OrdersSummary(
            completed_count=completed_count,
            photo_only_count=photo_only_count,
        ),
    )


def compute_traceability(
    session: Session,
    product_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
) -> list[TraceabilityEvent]:
    """Return ALL events (originals + corrections) for product_id in [from_dt, to_dt].

    Events are ordered by their created_at date ASC.  Each event includes:
    - event_type, id, date, operator name, qty, corrects_id, reason
    - Parent reference (delivery_id / delivery_order_id / count_id)

    The traceability endpoint includes ALL rows (not just leaves) because the
    forensic chain requires seeing corrections alongside originals.
    """
    # Verify product exists.
    product = session.get(Product, product_id)
    if product is None:
        return []  # Caller raises 404.

    events: list[TraceabilityEvent] = []
    user_id_set: set[uuid.UUID] = set()

    # --- delivery_items ---
    # Only include items whose parent delivery is 'validada' and validated_at in range.
    # Items of pending or non-validated deliveries must NOT appear in traceability
    # because they represent unconfirmed stock movements that could inflate or
    # distort the forensic record.
    validated_deliveries = session.scalars(
        select(Delivery).where(
            Delivery.status == "validada",
            Delivery.validated_at >= from_dt,
            Delivery.validated_at <= to_dt,
        )
    ).all()
    delivery_ids_in_range = {d.id for d in validated_deliveries}

    validated_items = session.scalars(
        select(DeliveryItem).where(
            DeliveryItem.product_id == product_id,
            DeliveryItem.delivery_id.in_(delivery_ids_in_range),
        )
    ).all() if delivery_ids_in_range else []

    seen_delivery_item_ids: set[uuid.UUID] = set()
    for item in list(validated_items):
        if item.id in seen_delivery_item_ids:
            continue
        seen_delivery_item_ids.add(item.id)
        user_id_set.add(item.created_by)
        qty = item.received_qty if item.received_qty is not None else item.announced_qty
        events.append(
            TraceabilityEvent(
                event_type="delivery_item",
                id=item.id,
                date=item.created_at,
                operator="",  # filled later
                qty=str(qty),
                corrects_id=item.corrects_id,
                reason=item.reason,
                delivery_id=item.delivery_id,
                delivery_order_id=None,
                count_id=None,
            )
        )

    # Store created_by keyed by event id for post-pass.
    delivery_item_created_by: dict[uuid.UUID, uuid.UUID] = {}
    for item in list(validated_items):
        delivery_item_created_by[item.id] = item.created_by

    # --- delivery_order_items ---
    # Only include items whose parent order is 'completed'.
    # Items of pending orders must NOT appear in traceability — a pending order
    # is a photo-only record with no confirmed consumption.
    completed_orders = session.scalars(
        select(DeliveryOrder).where(
            DeliveryOrder.status == "completed",
            DeliveryOrder.completed_at >= from_dt,
            DeliveryOrder.completed_at <= to_dt,
        )
    ).all()
    order_ids_in_range = {o.id for o in completed_orders}

    order_items_from_completed = session.scalars(
        select(DeliveryOrderItem).where(
            DeliveryOrderItem.product_id == product_id,
            DeliveryOrderItem.delivery_order_id.in_(order_ids_in_range),
        )
    ).all() if order_ids_in_range else []

    seen_order_item_ids: set[uuid.UUID] = set()
    order_item_created_by: dict[uuid.UUID, uuid.UUID] = {}
    for item in list(order_items_from_completed):
        if item.id in seen_order_item_ids:
            continue
        seen_order_item_ids.add(item.id)
        user_id_set.add(item.created_by)
        order_item_created_by[item.id] = item.created_by
        events.append(
            TraceabilityEvent(
                event_type="delivery_order_item",
                id=item.id,
                date=item.created_at,
                operator="",
                qty=str(item.quantity),
                corrects_id=item.corrects_id,
                reason=None,
                delivery_id=None,
                delivery_order_id=item.delivery_order_id,
                count_id=None,
            )
        )

    # --- inventory_count_items ---
    # Only include items whose parent count is 'completed'.
    # Items of in-progress counts must NOT appear in traceability.
    completed_counts_in_range = session.scalars(
        select(InventoryCount).where(
            InventoryCount.status == "completed",
            InventoryCount.completed_at >= from_dt,
            InventoryCount.completed_at <= to_dt,
        )
    ).all()
    count_ids_in_range = {c.id for c in completed_counts_in_range}

    count_items_from_completed = session.scalars(
        select(InventoryCountItem).where(
            InventoryCountItem.product_id == product_id,
            InventoryCountItem.inventory_count_id.in_(count_ids_in_range),
        )
    ).all() if count_ids_in_range else []

    seen_count_item_ids: set[uuid.UUID] = set()
    count_item_created_by: dict[uuid.UUID, uuid.UUID] = {}
    for item in list(count_items_from_completed):
        if item.id in seen_count_item_ids:
            continue
        seen_count_item_ids.add(item.id)
        user_id_set.add(item.created_by)
        count_item_created_by[item.id] = item.created_by
        events.append(
            TraceabilityEvent(
                event_type="inventory_count_item",
                id=item.id,
                date=item.created_at,
                operator="",
                qty=str(item.quantity),
                corrects_id=item.corrects_id,
                reason=item.reason,
                delivery_id=None,
                delivery_order_id=None,
                count_id=item.inventory_count_id,
            )
        )

    # Resolve user names.
    user_names = _get_user_names(session, user_id_set)
    all_created_by: dict[uuid.UUID, uuid.UUID] = {}
    all_created_by.update(delivery_item_created_by)
    all_created_by.update(order_item_created_by)
    all_created_by.update(count_item_created_by)

    for event in events:
        created_by = all_created_by.get(event.id)
        if created_by is not None:
            event.operator = user_names.get(created_by, str(created_by))

    events.sort(key=lambda e: e.date)
    return events
