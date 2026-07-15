"""Integration tests for the purchase orders schema (migration 0012).

Requires a live PostgreSQL database — the db_engine fixture in conftest.py
runs alembic upgrade head before the session starts.

Pattern for IntegrityError capture:
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()

This absorbs the error inside a nested SAVEPOINT without invalidating the
outer transaction managed by the conftest fixture.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError, InternalError, ProgrammingError
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_product(session: Session, user_id: uuid.UUID) -> uuid.UUID:
    from cocina_control.models.product import Product

    p = Product(
        id=uuid.uuid4(),
        name=f"prod-{uuid.uuid4().hex[:6]}",
        unit="kg",
        created_by=user_id,
    )
    session.add(p)
    session.flush()
    return p.id


def _make_purchase_order(
    session: Session,
    created_by: uuid.UUID,
    supplier_name: str = "Proveedor Test SA",
    corrects_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> uuid.UUID:
    from cocina_control.models.purchase_order import PurchaseOrder

    po = PurchaseOrder(
        id=uuid.uuid4(),
        supplier_name=supplier_name,
        created_by=created_by,
        corrects_id=corrects_id,
        reason=reason,
    )
    session.add(po)
    session.flush()
    return po.id


def _make_po_item(
    session: Session,
    purchase_order_id: uuid.UUID,
    product_id: uuid.UUID,
    created_by: uuid.UUID,
    expected_qty: Decimal = Decimal("10"),
    corrects_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> uuid.UUID:
    from cocina_control.models.purchase_order import PurchaseOrderItem

    item = PurchaseOrderItem(
        id=uuid.uuid4(),
        purchase_order_id=purchase_order_id,
        product_id=product_id,
        expected_qty=expected_qty,
        created_by=created_by,
        corrects_id=corrects_id,
        reason=reason,
    )
    session.add(item)
    session.flush()
    return item.id


def _make_delivery(
    session: Session,
    created_by: uuid.UUID,
    purchase_order_id: uuid.UUID | None = None,
) -> uuid.UUID:
    from cocina_control.models.delivery import Delivery

    d = Delivery(
        id=uuid.uuid4(),
        supplier_name="Prov Delivery",
        status="no_leida",
        created_by=created_by,
        purchase_order_id=purchase_order_id,
    )
    session.add(d)
    session.flush()
    return d.id


def _make_delivery_item(
    session: Session,
    delivery_id: uuid.UUID,
    product_id: uuid.UUID,
    created_by: uuid.UUID,
    announced_qty: Decimal = Decimal("5"),
    purchase_order_item_id: uuid.UUID | None = None,
) -> uuid.UUID:
    from cocina_control.models.delivery import DeliveryItem

    di = DeliveryItem(
        id=uuid.uuid4(),
        delivery_id=delivery_id,
        product_id=product_id,
        announced_qty=announced_qty,
        created_by=created_by,
        purchase_order_item_id=purchase_order_item_id,
    )
    session.add(di)
    session.flush()
    return di.id


# ---------------------------------------------------------------------------
# Test 1: migration creates the 4 new tables
# ---------------------------------------------------------------------------


def test_migration_creates_purchase_order_tables(db_engine):
    """After upgrade head, all 4 purchase order tables must exist."""
    expected = {
        "purchase_orders",
        "purchase_order_items",
        "purchase_order_item_costs",
        "purchase_order_status_events",
    }
    existing = set(inspect(db_engine).get_table_names())
    assert expected.issubset(existing), f"Missing tables: {expected - existing}"


# ---------------------------------------------------------------------------
# Test 2: basic creation with owner
# ---------------------------------------------------------------------------


def test_purchase_order_created_by_owner(db_session: Session, owner_user):
    """Create a PurchaseOrder with an owner; basic fields must persist."""
    po_id = _make_purchase_order(db_session, created_by=owner_user.id)

    from cocina_control.models.purchase_order import PurchaseOrder

    po = db_session.get(PurchaseOrder, po_id)
    assert po is not None
    assert po.supplier_name == "Proveedor Test SA"
    assert po.created_by == owner_user.id
    assert po.corrects_id is None
    assert po.reason is None


# ---------------------------------------------------------------------------
# Test 3: correction chain
# ---------------------------------------------------------------------------


def test_purchase_order_corrects_id_chain(db_session: Session, owner_user):
    """Order B correcting order A must persist and be queryable."""
    from cocina_control.models.purchase_order import PurchaseOrder

    po_a_id = _make_purchase_order(db_session, created_by=owner_user.id, supplier_name="Proveedor A")
    po_b_id = _make_purchase_order(
        db_session,
        created_by=owner_user.id,
        supplier_name="Proveedor A corregido",
        corrects_id=po_a_id,
        reason="Nombre incorrecto",
    )

    po_b = db_session.get(PurchaseOrder, po_b_id)
    assert po_b.corrects_id == po_a_id
    assert po_b.reason == "Nombre incorrecto"


# ---------------------------------------------------------------------------
# Test 4: no self-correction
# ---------------------------------------------------------------------------


def test_purchase_order_no_self_correction(db_session: Session, owner_user):
    """A PurchaseOrder with corrects_id == id must be rejected."""
    from cocina_control.models.purchase_order import PurchaseOrder

    self_id = uuid.uuid4()
    po = PurchaseOrder(
        id=self_id,
        supplier_name="Loop",
        created_by=owner_user.id,
        corrects_id=self_id,
    )
    db_session.add(po)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 5: corrects_id uniqueness (no chain bifurcation)
# ---------------------------------------------------------------------------


def test_purchase_order_corrects_unique(db_session: Session, owner_user):
    """Two orders pointing to the same corrects_id must raise IntegrityError."""
    po_orig_id = _make_purchase_order(db_session, created_by=owner_user.id)
    _make_purchase_order(db_session, created_by=owner_user.id, corrects_id=po_orig_id)

    from cocina_control.models.purchase_order import PurchaseOrder

    po_fork = PurchaseOrder(
        id=uuid.uuid4(),
        supplier_name="Fork",
        created_by=owner_user.id,
        corrects_id=po_orig_id,
    )
    db_session.add(po_fork)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 6: expected_qty must be positive
# ---------------------------------------------------------------------------


def test_purchase_order_item_expected_qty_positive(db_session: Session, owner_user):
    """PurchaseOrderItem with expected_qty = 0 must be rejected (CHECK constraint)."""
    from cocina_control.models.purchase_order import PurchaseOrderItem

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)

    item = PurchaseOrderItem(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        product_id=product_id,
        expected_qty=Decimal("0"),
        created_by=owner_user.id,
    )
    db_session.add(item)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 7: partial unique index — one active item per product per order
# ---------------------------------------------------------------------------


def test_purchase_order_item_unique_active_product_rejects_duplicate(
    db_session: Session, owner_user
):
    """Two active items (corrects_id IS NULL) for the same product in the same order must fail."""
    from cocina_control.models.purchase_order import PurchaseOrderItem

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)
    _make_po_item(db_session, po_id, product_id, owner_user.id)

    duplicate = PurchaseOrderItem(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        product_id=product_id,
        expected_qty=Decimal("5"),
        created_by=owner_user.id,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()


def test_purchase_order_item_unique_active_product_allows_correction(
    db_session: Session, owner_user
):
    """A correction row (corrects_id IS NOT NULL) for an existing active item must succeed.

    The partial unique index uq_purchase_order_items_active_product only
    constrains rows WHERE corrects_id IS NULL. A correction row with a
    non-NULL corrects_id is always allowed, regardless of product duplication.
    """
    from cocina_control.models.purchase_order import PurchaseOrderItem

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)
    first_item_id = _make_po_item(db_session, po_id, product_id, owner_user.id)

    correction_id = _make_po_item(
        db_session,
        po_id,
        product_id,
        owner_user.id,
        expected_qty=Decimal("15"),
        corrects_id=first_item_id,
        reason="Actualizar cantidad",
    )
    item = db_session.get(PurchaseOrderItem, correction_id)
    assert item.corrects_id == first_item_id


# ---------------------------------------------------------------------------
# Test 8: unit_cost must be positive
# ---------------------------------------------------------------------------


def test_purchase_order_item_cost_positive(db_session: Session, owner_user):
    """PurchaseOrderItemCost with unit_cost = 0 must be rejected (CHECK constraint)."""
    from cocina_control.models.purchase_order import PurchaseOrderItemCost

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)
    item_id = _make_po_item(db_session, po_id, product_id, owner_user.id)

    cost = PurchaseOrderItemCost(
        id=uuid.uuid4(),
        purchase_order_item_id=item_id,
        unit_cost=Decimal("0"),
        created_by=owner_user.id,
    )
    db_session.add(cost)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 9: cost correction chain
# ---------------------------------------------------------------------------


def test_purchase_order_item_cost_chain(db_session: Session, owner_user):
    """Create cost A, then correction B; both must persist and chain correctly."""
    from cocina_control.models.purchase_order import PurchaseOrderItemCost

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)
    item_id = _make_po_item(db_session, po_id, product_id, owner_user.id)

    cost_a = PurchaseOrderItemCost(
        id=uuid.uuid4(),
        purchase_order_item_id=item_id,
        unit_cost=Decimal("12.50"),
        created_by=owner_user.id,
    )
    db_session.add(cost_a)
    db_session.flush()

    cost_b = PurchaseOrderItemCost(
        id=uuid.uuid4(),
        purchase_order_item_id=item_id,
        unit_cost=Decimal("13.00"),
        created_by=owner_user.id,
        corrects_id=cost_a.id,
        reason="Precio final de factura",
    )
    db_session.add(cost_b)
    db_session.flush()
    db_session.refresh(cost_b)

    assert cost_b.corrects_id == cost_a.id
    assert cost_b.unit_cost == Decimal("13.00")
    assert cost_b.reason == "Precio final de factura"


# ---------------------------------------------------------------------------
# Test 10: status event types
# ---------------------------------------------------------------------------


def test_purchase_order_status_event_types(db_session: Session, owner_user):
    """The 4 valid event_types must insert; 'opened' must fail with DataError."""
    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)

    for valid_type in ("closed_auto", "closed_manual", "reopened", "annulled"):
        event = PurchaseOrderStatusEvent(
            id=uuid.uuid4(),
            purchase_order_id=po_id,
            event_type=valid_type,
            created_by=owner_user.id,
        )
        db_session.add(event)
        db_session.flush()

    # Invalid type must fail.
    invalid_event = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        event_type="opened",  # not in enum
        created_by=owner_user.id,
    )
    db_session.add(invalid_event)
    with pytest.raises((DataError, LookupError, ValueError)):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 11: partida linked to a purchase order
# ---------------------------------------------------------------------------


def test_delivery_partida_link_to_purchase_order(db_session: Session, owner_user, cocinero_user):
    """A delivery (partida) linked to a PO and a delivery_item linked to a PO item."""
    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)
    po_item_id = _make_po_item(db_session, po_id, product_id, owner_user.id)

    delivery_id = _make_delivery(db_session, created_by=cocinero_user.id, purchase_order_id=po_id)
    di_id = _make_delivery_item(
        db_session,
        delivery_id=delivery_id,
        product_id=product_id,
        created_by=cocinero_user.id,
        announced_qty=Decimal("5"),
        purchase_order_item_id=po_item_id,
    )

    from cocina_control.models.delivery import Delivery, DeliveryItem

    delivery = db_session.get(Delivery, delivery_id)
    di = db_session.get(DeliveryItem, di_id)

    assert delivery.purchase_order_id == po_id
    assert di.purchase_order_item_id == po_item_id


# ---------------------------------------------------------------------------
# Test 12: legacy v0.2 deliveries still work (NULL purchase_order_id)
# ---------------------------------------------------------------------------


def test_delivery_legacy_v02_still_works(db_session: Session, cocinero_user):
    """Legacy deliveries with NULL purchase_order_id and NULL purchase_order_item_id must still work."""
    product_id = _make_product(db_session, cocinero_user.id)

    delivery_id = _make_delivery(db_session, created_by=cocinero_user.id, purchase_order_id=None)
    di_id = _make_delivery_item(
        db_session,
        delivery_id=delivery_id,
        product_id=product_id,
        created_by=cocinero_user.id,
        purchase_order_item_id=None,
    )

    from cocina_control.models.delivery import Delivery, DeliveryItem

    delivery = db_session.get(Delivery, delivery_id)
    di = db_session.get(DeliveryItem, di_id)

    assert delivery.purchase_order_id is None
    assert di.purchase_order_item_id is None


# ---------------------------------------------------------------------------
# Test 13: purchase_order_status_events has no corrects_id column
# ---------------------------------------------------------------------------


def test_status_events_no_corrects_id_column(db_engine):
    """purchase_order_status_events must NOT have a corrects_id column (immutable log)."""
    columns = {
        col["name"]
        for col in inspect(db_engine).get_columns("purchase_order_status_events")
    }
    assert "corrects_id" not in columns, (
        "purchase_order_status_events must be immutable — corrects_id column found"
    )


# ---------------------------------------------------------------------------
# Test 14: status events ordered by created_at
# ---------------------------------------------------------------------------


def test_status_events_ordered_by_created_at(db_session: Session, owner_user):
    """The most recent event for an order must be retrievable by created_at ordering."""
    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)

    t1 = datetime(2026, 7, 1, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 7, 1, 11, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)

    for event_type, ts in (("closed_auto", t1), ("reopened", t2), ("annulled", t3)):
        event = PurchaseOrderStatusEvent(
            id=uuid.uuid4(),
            purchase_order_id=po_id,
            event_type=event_type,
            created_by=owner_user.id,
            created_at=ts,
        )
        db_session.add(event)
    db_session.flush()

    # Fetch all events for the order sorted descending.
    result = (
        db_session.query(PurchaseOrderStatusEvent)
        .filter(PurchaseOrderStatusEvent.purchase_order_id == po_id)
        .order_by(PurchaseOrderStatusEvent.created_at.desc())
        .all()
    )

    assert len(result) == 3
    assert result[0].event_type == "annulled"  # most recent
    assert result[1].event_type == "reopened"
    assert result[2].event_type == "closed_auto"    # oldest


# ---------------------------------------------------------------------------
# Helper for item costs (used in new trigger tests)
# ---------------------------------------------------------------------------


def _make_po_item_cost(
    session: Session,
    purchase_order_item_id: uuid.UUID,
    created_by: uuid.UUID,
    unit_cost: Decimal = Decimal("10.00"),
    corrects_id: uuid.UUID | None = None,
) -> uuid.UUID:
    from cocina_control.models.purchase_order import PurchaseOrderItemCost

    cost = PurchaseOrderItemCost(
        id=uuid.uuid4(),
        purchase_order_item_id=purchase_order_item_id,
        unit_cost=unit_cost,
        created_by=created_by,
        corrects_id=corrects_id,
    )
    session.add(cost)
    session.flush()
    return cost.id


# ---------------------------------------------------------------------------
# Test 15: closed_manual requires owner (SEG-A1)
# ---------------------------------------------------------------------------


def test_status_event_closed_manual_requires_owner(db_session: Session, owner_user, cocinero_user):
    """closed_manual with a cocinero created_by must be rejected by the DB trigger.

    closed_auto with a cocinero must succeed — no role restriction for auto-closes.
    """
    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)

    # closed_auto with cocinero must succeed.
    event_auto = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        event_type="closed_auto",
        created_by=cocinero_user.id,
    )
    db_session.add(event_auto)
    db_session.flush()  # must not raise

    # closed_manual with cocinero must fail.
    event_manual = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        event_type="closed_manual",
        created_by=cocinero_user.id,
    )
    db_session.add(event_manual)
    with pytest.raises((IntegrityError, InternalError, ProgrammingError)):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 16: reopened requires owner (SEG-A1)
# ---------------------------------------------------------------------------


def test_status_event_reopened_requires_owner(db_session: Session, owner_user, cocinero_user):
    """reopened with a cocinero created_by must be rejected by the DB trigger."""
    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)

    event = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        event_type="reopened",
        created_by=cocinero_user.id,
    )
    db_session.add(event)
    with pytest.raises((IntegrityError, InternalError, ProgrammingError)):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 17: annulled requires owner (SEG-A1)
# ---------------------------------------------------------------------------


def test_status_event_annulled_requires_owner(db_session: Session, owner_user, cocinero_user):
    """annulled with a cocinero created_by must be rejected by the DB trigger."""
    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)

    event = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        event_type="annulled",
        created_by=cocinero_user.id,
    )
    db_session.add(event)
    with pytest.raises((IntegrityError, InternalError, ProgrammingError)):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 18: purchase_order created_by operator rejected (SEG-A2)
# ---------------------------------------------------------------------------


def test_purchase_order_created_by_cocinero_rejected(db_session: Session, cocinero_user):
    """PurchaseOrder with created_by=cocinero must be rejected by the DB trigger."""
    from cocina_control.models.purchase_order import PurchaseOrder

    po = PurchaseOrder(
        id=uuid.uuid4(),
        supplier_name="Proveedor Ilegal",
        created_by=cocinero_user.id,
    )
    db_session.add(po)
    with pytest.raises((IntegrityError, InternalError, ProgrammingError)):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 19: purchase_order_item created_by operator rejected (SEG-A2)
# ---------------------------------------------------------------------------


def test_purchase_order_item_created_by_cocinero_rejected(
    db_session: Session, owner_user, cocinero_user
):
    """PurchaseOrderItem with created_by=cocinero must be rejected by the DB trigger."""
    from cocina_control.models.purchase_order import PurchaseOrderItem

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)

    item = PurchaseOrderItem(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        product_id=product_id,
        expected_qty=Decimal("5"),
        created_by=cocinero_user.id,
    )
    db_session.add(item)
    with pytest.raises((IntegrityError, InternalError, ProgrammingError)):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 20: purchase_order_item_cost created_by operator rejected (SEG-A2 / B2)
# ---------------------------------------------------------------------------


def test_purchase_order_item_cost_created_by_cocinero_rejected(
    db_session: Session, owner_user, cocinero_user
):
    """PurchaseOrderItemCost with created_by=cocinero must be rejected by the DB trigger.

    This is the most critical case: cost records are exclusively owner/admin data
    and must never be writable by a cocinero, even if the app layer is bypassed.
    """
    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)
    item_id = _make_po_item(db_session, po_id, product_id, owner_user.id)

    from cocina_control.models.purchase_order import PurchaseOrderItemCost

    cost = PurchaseOrderItemCost(
        id=uuid.uuid4(),
        purchase_order_item_id=item_id,
        unit_cost=Decimal("15.00"),
        created_by=cocinero_user.id,
    )
    db_session.add(cost)
    with pytest.raises((IntegrityError, InternalError, ProgrammingError)):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# Test 21: correction chain leaf identification (QA-1)
# ---------------------------------------------------------------------------


def test_purchase_order_items_chain_leaf_identification(db_session: Session, owner_user):
    """Demonstrate that the partial unique index identifies the ROOT, not the leaf.

    Chain: A (root, corrects_id=NULL) → B → C (leaf).

    - WHERE corrects_id IS NULL returns only A (the root).
    - The leaf (C) is identified with NOT EXISTS, not with corrects_id IS NULL.

    This test covers QA-1: the empirical proof that the index name
    uq_purchase_order_items_root_per_product is semantically correct.
    """
    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)

    # A: root (no predecessor)
    a_id = _make_po_item(db_session, po_id, product_id, owner_user.id, expected_qty=Decimal("10"))
    # B: corrects A
    b_id = _make_po_item(
        db_session, po_id, product_id, owner_user.id,
        expected_qty=Decimal("12"),
        corrects_id=a_id,
        reason="Ajuste B",
    )
    # C: corrects B (leaf)
    c_id = _make_po_item(
        db_session, po_id, product_id, owner_user.id,
        expected_qty=Decimal("14"),
        corrects_id=b_id,
        reason="Ajuste C",
    )

    # corrects_id IS NULL → returns only the root (A).
    root_rows = db_session.execute(
        text(
            "SELECT id FROM purchase_order_items "
            "WHERE purchase_order_id = :po_id AND corrects_id IS NULL"
        ),
        {"po_id": po_id},
    ).fetchall()
    root_ids = {row[0] for row in root_rows}
    assert root_ids == {a_id}, f"Expected only root A, got: {root_ids}"

    # NOT EXISTS → returns only the leaf (C).
    leaf_rows = db_session.execute(
        text(
            "SELECT t.id FROM purchase_order_items t "
            "WHERE t.purchase_order_id = :po_id "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM purchase_order_items x WHERE x.corrects_id = t.id"
            ")"
        ),
        {"po_id": po_id},
    ).fetchall()
    leaf_ids = {row[0] for row in leaf_rows}
    assert leaf_ids == {c_id}, f"Expected only leaf C, got: {leaf_ids}"


# ---------------------------------------------------------------------------
# Tests 22-29: three-role model (Backend #2 — 0013_three_roles)
# ---------------------------------------------------------------------------


def test_purchase_order_admin_can_create(db_session: Session, admin_user):
    """A user with role='admin' must be allowed to create a PurchaseOrder (trigger allows owner/admin)."""
    po_id = _make_purchase_order(db_session, created_by=admin_user.id)

    from cocina_control.models.purchase_order import PurchaseOrder

    po = db_session.get(PurchaseOrder, po_id)
    assert po is not None
    assert po.created_by == admin_user.id


def test_purchase_order_item_admin_can_create(db_session: Session, owner_user, admin_user):
    """A user with role='admin' must be allowed to create a PurchaseOrderItem."""
    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)

    item_id = _make_po_item(db_session, po_id, product_id, admin_user.id)

    from cocina_control.models.purchase_order import PurchaseOrderItem

    item = db_session.get(PurchaseOrderItem, item_id)
    assert item is not None
    assert item.created_by == admin_user.id


def test_purchase_order_item_cost_admin_can_create(db_session: Session, owner_user, admin_user):
    """A user with role='admin' must be allowed to create a PurchaseOrderItemCost."""
    po_id = _make_purchase_order(db_session, created_by=owner_user.id)
    product_id = _make_product(db_session, owner_user.id)
    item_id = _make_po_item(db_session, po_id, product_id, owner_user.id)

    cost_id = _make_po_item_cost(db_session, item_id, admin_user.id)

    from cocina_control.models.purchase_order import PurchaseOrderItemCost

    cost = db_session.get(PurchaseOrderItemCost, cost_id)
    assert cost is not None
    assert cost.created_by == admin_user.id


def test_purchase_order_cocinero_still_rejected(db_session: Session, cocinero_user):
    """Cocinero (ex-operator) must still be rejected when creating a PurchaseOrder."""
    from cocina_control.models.purchase_order import PurchaseOrder

    po = PurchaseOrder(
        id=uuid.uuid4(),
        supplier_name="Proveedor Ilegal",
        created_by=cocinero_user.id,
    )
    db_session.add(po)
    with pytest.raises((IntegrityError, InternalError, ProgrammingError)):
        with db_session.begin_nested():
            db_session.flush()


def test_status_event_closed_manual_admin_ok(db_session: Session, owner_user, admin_user):
    """closed_manual with admin created_by must be accepted by the updated DB trigger."""
    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)

    event = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        event_type="closed_manual",
        created_by=admin_user.id,
    )
    db_session.add(event)
    db_session.flush()  # must not raise

    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent as PSE

    persisted = db_session.get(PSE, event.id)
    assert persisted is not None
    assert persisted.event_type == "closed_manual"


def test_status_event_reopened_admin_ok(db_session: Session, owner_user, admin_user):
    """reopened with admin created_by must be accepted by the updated DB trigger."""
    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)

    event = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        event_type="reopened",
        created_by=admin_user.id,
    )
    db_session.add(event)
    db_session.flush()  # must not raise

    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent as PSE

    persisted = db_session.get(PSE, event.id)
    assert persisted is not None
    assert persisted.event_type == "reopened"


def test_status_event_annulled_admin_ok(db_session: Session, owner_user, admin_user):
    """annulled with admin created_by must be accepted by the updated DB trigger."""
    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)

    event = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        event_type="annulled",
        created_by=admin_user.id,
    )
    db_session.add(event)
    db_session.flush()  # must not raise

    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent as PSE

    persisted = db_session.get(PSE, event.id)
    assert persisted is not None
    assert persisted.event_type == "annulled"


def test_status_event_closed_auto_cocinero_ok(db_session: Session, owner_user, cocinero_user):
    """closed_auto with cocinero created_by must still be accepted (no role restriction on auto-close)."""
    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent

    po_id = _make_purchase_order(db_session, created_by=owner_user.id)

    event = PurchaseOrderStatusEvent(
        id=uuid.uuid4(),
        purchase_order_id=po_id,
        event_type="closed_auto",
        created_by=cocinero_user.id,
    )
    db_session.add(event)
    db_session.flush()  # must not raise

    from cocina_control.models.purchase_order import PurchaseOrderStatusEvent as PSE

    persisted = db_session.get(PSE, event.id)
    assert persisted is not None
    assert persisted.event_type == "closed_auto"
