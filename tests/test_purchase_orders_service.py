"""Unit tests for services/purchase_orders.py.

These tests exercise the service helpers directly against the real DB
(function-scoped SAVEPOINT rollback via conftest).  No HTTP layer involved.

Fixtures inherited from conftest.py:
  db_session, owner_user, admin_user, cocinero_user.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.product import Product
from cocina_control.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderItemCost,
    PurchaseOrderStatusEvent,
)
from cocina_control.services.purchase_orders import (
    build_pending_summary,
    compute_order_totals,
    derive_status,
    get_active_cost,
    get_active_items,
    get_partida_count,
    get_received_qty_by_item,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_product(session: Session, owner_id: uuid.UUID, name: str, unit: str = "kg") -> Product:
    p = Product(
        id=uuid.uuid4(),
        name=name.upper(),
        unit=unit,
        is_active=True,
        created_by=owner_id,
    )
    session.add(p)
    session.flush()
    return p


def _make_order(session: Session, owner_id: uuid.UUID, supplier: str = "S1") -> PurchaseOrder:
    o = PurchaseOrder(
        id=uuid.uuid4(),
        supplier_name=supplier,
        created_by=owner_id,
    )
    session.add(o)
    session.flush()
    return o


def _make_item(
    session: Session,
    order: PurchaseOrder,
    product: Product,
    owner_id: uuid.UUID,
    expected_qty: str = "10",
    corrects_id: uuid.UUID | None = None,
) -> PurchaseOrderItem:
    i = PurchaseOrderItem(
        id=uuid.uuid4(),
        purchase_order_id=order.id,
        product_id=product.id,
        expected_qty=Decimal(expected_qty),
        corrects_id=corrects_id,
        created_by=owner_id,
    )
    session.add(i)
    session.flush()
    return i


def _make_cost(
    session: Session,
    item: PurchaseOrderItem,
    owner_id: uuid.UUID,
    unit_cost: str = "5.00",
    corrects_id: uuid.UUID | None = None,
) -> PurchaseOrderItemCost:
    c = PurchaseOrderItemCost(
        id=uuid.uuid4(),
        purchase_order_item_id=item.id,
        unit_cost=Decimal(unit_cost),
        corrects_id=corrects_id,
        created_by=owner_id,
    )
    session.add(c)
    session.flush()
    return c


def _make_event(
    session: Session,
    order: PurchaseOrder,
    event_type: str,
    user_id: uuid.UUID,
) -> PurchaseOrderStatusEvent:
    e = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=order.id,
        event_type=event_type,
        created_by=user_id,
    )
    session.add(e)
    session.flush()
    return e


def _make_validated_delivery(
    session: Session,
    order: PurchaseOrder,
    user_id: uuid.UUID,
) -> Delivery:
    d = Delivery(
        id=uuid.uuid4(),
        supplier_name=order.supplier_name,
        status="validada",
        created_by=user_id,
        validated_at=datetime.now(UTC),
        validated_by=user_id,
        purchase_order_id=order.id,
    )
    session.add(d)
    session.flush()
    return d


def _make_delivery_item(
    session: Session,
    delivery: Delivery,
    product: Product,
    po_item: PurchaseOrderItem,
    user_id: uuid.UUID,
    announced_qty: str = "10",
    received_qty: str = "10",
    corrects_id: uuid.UUID | None = None,
) -> DeliveryItem:
    di = DeliveryItem(
        id=uuid.uuid4(),
        delivery_id=delivery.id,
        product_id=product.id,
        announced_qty=Decimal(announced_qty),
        received_qty=Decimal(received_qty),
        created_by=user_id,
        confirmed_at=datetime.now(UTC),
        confirmed_by=user_id,
        purchase_order_item_id=po_item.id,
        corrects_id=corrects_id,
    )
    session.add(di)
    session.flush()
    return di


# ---------------------------------------------------------------------------
# get_active_items
# ---------------------------------------------------------------------------


def test_get_active_items_no_corrections(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "POLLO")
    item = _make_item(db_session, order, product, owner_user.id)

    result = get_active_items(db_session, order.id)

    assert len(result) == 1
    assert result[0].id == item.id


def test_get_active_items_with_correction_returns_leaf(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "CERDO")

    root_item = _make_item(db_session, order, product, owner_user.id, expected_qty="10")
    leaf_item = _make_item(
        db_session, order, product, owner_user.id, expected_qty="15", corrects_id=root_item.id
    )

    result = get_active_items(db_session, order.id)

    ids = {r.id for r in result}
    assert leaf_item.id in ids
    assert root_item.id not in ids


# ---------------------------------------------------------------------------
# get_active_cost
# ---------------------------------------------------------------------------


def test_get_active_cost_no_corrections(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "TOMATE")
    item = _make_item(db_session, order, product, owner_user.id)
    _make_cost(db_session, item, owner_user.id, unit_cost="3.50")

    result = get_active_cost(db_session, item.id)

    assert result == Decimal("3.50")


def test_get_active_cost_with_correction_returns_leaf(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "CEBOLLA")
    item = _make_item(db_session, order, product, owner_user.id)

    root_cost = _make_cost(db_session, item, owner_user.id, unit_cost="2.00")
    _make_cost(db_session, item, owner_user.id, unit_cost="2.50", corrects_id=root_cost.id)

    result = get_active_cost(db_session, item.id)

    assert result == Decimal("2.50")


# ---------------------------------------------------------------------------
# get_received_qty_by_item
# ---------------------------------------------------------------------------


def test_get_received_qty_by_item_no_partidas(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    result = get_received_qty_by_item(db_session, order.id)
    assert result == {}


def test_get_received_qty_by_item_after_partida(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "PALTA")
    po_item = _make_item(db_session, order, product, owner_user.id, expected_qty="20")
    delivery = _make_validated_delivery(db_session, order, owner_user.id)
    _make_delivery_item(
        db_session, delivery, product, po_item, owner_user.id,
        announced_qty="20", received_qty="15",
    )

    result = get_received_qty_by_item(db_session, order.id)

    assert po_item.id in result
    assert result[po_item.id] == Decimal("15")


# ---------------------------------------------------------------------------
# derive_status
# ---------------------------------------------------------------------------


def test_derive_status_no_events_no_partidas_returns_open(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    assert derive_status(db_session, order.id) == "open"


def test_derive_status_no_events_with_partidas_returns_partially_received(
    db_session: Session, owner_user
):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "ARROZ")
    po_item = _make_item(db_session, order, product, owner_user.id, expected_qty="100")
    delivery = _make_validated_delivery(db_session, order, owner_user.id)
    _make_delivery_item(
        db_session, delivery, product, po_item, owner_user.id,
        announced_qty="50", received_qty="50",
    )

    assert derive_status(db_session, order.id) == "partially_received"


def test_derive_status_closed_auto_returns_closed(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    _make_event(db_session, order, "closed_auto", owner_user.id)

    assert derive_status(db_session, order.id) == "closed"


def test_derive_status_closed_manual_returns_closed(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    _make_event(db_session, order, "closed_manual", owner_user.id)

    assert derive_status(db_session, order.id) == "closed"


def test_derive_status_annulled_returns_annulled(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    _make_event(db_session, order, "annulled", owner_user.id)

    assert derive_status(db_session, order.id) == "annulled"


def test_derive_status_reopened_after_closed_returns_open_or_partial_based_on_saldo(
    db_session: Session, owner_user
):
    """After a 'reopened' event the status is derived from saldo, not from the event."""
    order = _make_order(db_session, owner_user.id)
    _make_event(db_session, order, "closed_auto", owner_user.id)
    _make_event(db_session, order, "reopened", owner_user.id)

    # No active items → open (defensive)
    assert derive_status(db_session, order.id) == "open"


# ---------------------------------------------------------------------------
# compute_order_totals
# ---------------------------------------------------------------------------


def test_compute_order_totals_no_partidas(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "QUESO")
    item = _make_item(db_session, order, product, owner_user.id, expected_qty="10")
    _make_cost(db_session, item, owner_user.id, unit_cost="8.00")

    totals = compute_order_totals(db_session, order.id)

    assert totals["total_ordered"] == Decimal("80.00")
    assert totals["total_received"] == Decimal("0")
    assert totals["pending_amount"] == Decimal("80.00")


def test_compute_order_totals_with_partidas(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "POLLO2")
    item = _make_item(db_session, order, product, owner_user.id, expected_qty="100")
    _make_cost(db_session, item, owner_user.id, unit_cost="7.00")

    delivery = _make_validated_delivery(db_session, order, owner_user.id)
    _make_delivery_item(
        db_session, delivery, product, item, owner_user.id,
        announced_qty="60", received_qty="60",
    )

    totals = compute_order_totals(db_session, order.id)

    assert totals["total_ordered"] == Decimal("700.00")
    # 60 × 7 = 420
    assert totals["total_received"] == Decimal("420.00")
    assert totals["pending_amount"] == Decimal("280.00")


def test_compute_order_totals_excess_qty_not_valorized(db_session: Session, owner_user):
    """received > expected: excess portion must NOT be valorized."""
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "CERDO2")
    item = _make_item(db_session, order, product, owner_user.id, expected_qty="10")
    _make_cost(db_session, item, owner_user.id, unit_cost="9.00")

    delivery = _make_validated_delivery(db_session, order, owner_user.id)
    _make_delivery_item(
        db_session, delivery, product, item, owner_user.id,
        announced_qty="10", received_qty="15",  # 5 units excess
    )

    totals = compute_order_totals(db_session, order.id)

    # total_ordered = 10 × 9 = 90
    assert totals["total_ordered"] == Decimal("90.00")
    # total_received = min(15, 10) × 9 = 90 (capped at expected)
    assert totals["total_received"] == Decimal("90.00")
    assert totals["pending_amount"] == Decimal("0.00")


# ---------------------------------------------------------------------------
# build_pending_summary
# ---------------------------------------------------------------------------


def test_build_pending_summary_open_order(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "POLLO", unit="kg")
    item = _make_item(db_session, order, product, owner_user.id, expected_qty="40")

    summary = build_pending_summary(db_session, order.id)

    assert summary is not None
    assert "40" in summary
    assert "kg" in summary
    assert "POLLO" in summary
    assert summary.startswith("faltan ")


def test_build_pending_summary_partially_received(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "CEBOLLA", unit="kg")
    item = _make_item(db_session, order, product, owner_user.id, expected_qty="20")

    delivery = _make_validated_delivery(db_session, order, owner_user.id)
    _make_delivery_item(
        db_session, delivery, product, item, owner_user.id,
        announced_qty="20", received_qty="5",
    )

    summary = build_pending_summary(db_session, order.id)

    assert summary is not None
    assert "15" in summary  # 20 - 5
    assert "CEBOLLA" in summary


def test_build_pending_summary_closed_returns_none(db_session: Session, owner_user):
    order = _make_order(db_session, owner_user.id)
    product = _make_product(db_session, owner_user.id, "TOMATE2", unit="kg")
    item = _make_item(db_session, order, product, owner_user.id, expected_qty="10")

    delivery = _make_validated_delivery(db_session, order, owner_user.id)
    _make_delivery_item(
        db_session, delivery, product, item, owner_user.id,
        announced_qty="10", received_qty="10",
    )

    # All items fully received — pending_qty = 0 for all → None
    summary = build_pending_summary(db_session, order.id)
    assert summary is None
