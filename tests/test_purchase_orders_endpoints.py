"""Integration tests for purchase-order endpoints (Backend #2 — Slice 2b).

Covers EP-1 through EP-6:
  POST   /api/v1/purchase-orders
  GET    /api/v1/purchase-orders
  GET    /api/v1/purchase-orders/pending          (cocinero bandeja)
  GET    /api/v1/purchase-orders/{id}
  GET    /api/v1/purchase-orders/{id}/partida-draft
  POST   /api/v1/purchase-orders/{id}/partidas

Fixtures inherited from conftest.py:
  owner_user, admin_user, cocinero_user,
  owner_token, admin_token, cocinero_token,
  client, db_session.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.product import Product
from cocina_control.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderItemCost,
    PurchaseOrderStatusEvent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_product(
    session: Session,
    owner_id: uuid.UUID,
    name: str,
    unit: str = "kg",
    is_active: bool = True,
) -> Product:
    p = Product(
        id=uuid.uuid4(),
        name=name.upper(),
        unit=unit,
        is_active=is_active,
        created_by=owner_id,
    )
    session.add(p)
    session.flush()
    return p


def _make_order(
    session: Session,
    creator_id: uuid.UUID,
    supplier: str = "Proveedor Test",
) -> PurchaseOrder:
    o = PurchaseOrder(
        id=uuid.uuid4(),
        supplier_name=supplier,
        created_by=creator_id,
    )
    session.add(o)
    session.flush()
    return o


def _make_po_item(
    session: Session,
    order: PurchaseOrder,
    product: Product,
    creator_id: uuid.UUID,
    expected_qty: str = "10",
    corrects_id: uuid.UUID | None = None,
) -> PurchaseOrderItem:
    i = PurchaseOrderItem(
        id=uuid.uuid4(),
        purchase_order_id=order.id,
        product_id=product.id,
        expected_qty=Decimal(expected_qty),
        corrects_id=corrects_id,
        created_by=creator_id,
    )
    session.add(i)
    session.flush()
    return i


def _make_po_cost(
    session: Session,
    item: PurchaseOrderItem,
    creator_id: uuid.UUID,
    unit_cost: str = "5.00",
    corrects_id: uuid.UUID | None = None,
) -> PurchaseOrderItemCost:
    c = PurchaseOrderItemCost(
        id=uuid.uuid4(),
        purchase_order_item_id=item.id,
        unit_cost=Decimal(unit_cost),
        corrects_id=corrects_id,
        created_by=creator_id,
    )
    session.add(c)
    session.flush()
    return c


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
    )
    session.add(di)
    session.flush()
    return di


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def two_products(db_session: Session, owner_user):
    """Two active products for use in order creation tests."""
    p1 = _make_product(db_session, owner_user.id, "POLLO", unit="kg")
    p2 = _make_product(db_session, owner_user.id, "PAPA", unit="kg")
    return p1, p2


@pytest.fixture
def inactive_product(db_session: Session, owner_user):
    return _make_product(db_session, owner_user.id, "INACTIVO", is_active=False)


# ---------------------------------------------------------------------------
# EP-1: POST /api/v1/purchase-orders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_order_owner_ok(
    client: AsyncClient,
    owner_token: str,
    two_products,
    owner_user,
):
    """Owner creates order with 2 items — 201, response complete."""
    p1, p2 = two_products
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "Carnicería López",
            "items": [
                {"product_id": str(p1.id), "expected_qty": "100", "unit_cost": "7.00"},
                {"product_id": str(p2.id), "expected_qty": "20", "unit_cost": "2.50"},
            ],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["supplier_name"] == "Carnicería López"
    assert data["derived_status"] == "open"
    assert len(data["items"]) == 2
    assert "total_ordered" in data
    assert "created_by_name" in data
    assert data["partida_count"] == 0


@pytest.mark.asyncio
async def test_create_order_admin_ok(
    client: AsyncClient,
    admin_token: str,
    two_products,
):
    """Admin can also create orders — 201."""
    p1, p2 = two_products
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "Verdulería",
            "items": [
                {"product_id": str(p1.id), "expected_qty": "50", "unit_cost": "6.00"},
            ],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_order_cocinero_forbidden(
    client: AsyncClient,
    cocinero_token: str,
    two_products,
):
    """Cocinero cannot create orders — 403."""
    p1, _ = two_products
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "X",
            "items": [{"product_id": str(p1.id), "expected_qty": "1", "unit_cost": "1.00"}],
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_order_no_auth_401(
    client: AsyncClient,
    two_products,
):
    """No token → 401."""
    p1, _ = two_products
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "X",
            "items": [{"product_id": str(p1.id), "expected_qty": "1", "unit_cost": "1.00"}],
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_order_empty_supplier_400(
    client: AsyncClient,
    owner_token: str,
    two_products,
):
    """Empty/whitespace supplier_name → 400/422."""
    p1, _ = two_products
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "   ",
            "items": [{"product_id": str(p1.id), "expected_qty": "1", "unit_cost": "1.00"}],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_create_order_no_items_400(
    client: AsyncClient,
    owner_token: str,
):
    """Empty items list → 422 (schema validation)."""
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={"supplier_name": "X", "items": []},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_order_duplicate_product_400(
    client: AsyncClient,
    owner_token: str,
    two_products,
):
    """Same product_id twice in items → 400/422."""
    p1, _ = two_products
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "X",
            "items": [
                {"product_id": str(p1.id), "expected_qty": "10", "unit_cost": "5.00"},
                {"product_id": str(p1.id), "expected_qty": "5", "unit_cost": "5.00"},
            ],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_create_order_negative_qty_400(
    client: AsyncClient,
    owner_token: str,
    two_products,
):
    """expected_qty <= 0 → 422."""
    p1, _ = two_products
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "X",
            "items": [{"product_id": str(p1.id), "expected_qty": "-1", "unit_cost": "5.00"}],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_order_negative_cost_400(
    client: AsyncClient,
    owner_token: str,
    two_products,
):
    """unit_cost <= 0 → 422."""
    p1, _ = two_products
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "X",
            "items": [{"product_id": str(p1.id), "expected_qty": "10", "unit_cost": "0"}],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_order_unknown_product_400(
    client: AsyncClient,
    owner_token: str,
):
    """Non-existent product_id → 400."""
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "X",
            "items": [
                {"product_id": str(uuid.uuid4()), "expected_qty": "10", "unit_cost": "5.00"}
            ],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_order_inactive_product_400(
    client: AsyncClient,
    owner_token: str,
    inactive_product,
):
    """Inactive product → 400."""
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "X",
            "items": [
                {
                    "product_id": str(inactive_product.id),
                    "expected_qty": "10",
                    "unit_cost": "5.00",
                }
            ],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_order_persists_correct_costs_items_and_order(
    client: AsyncClient,
    owner_token: str,
    two_products,
    db_session: Session,
    owner_user,
):
    """Verify DB state after creating an order."""
    p1, p2 = two_products
    resp = await client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_name": "Persistencia Test",
            "items": [
                {"product_id": str(p1.id), "expected_qty": "50", "unit_cost": "7.50"},
                {"product_id": str(p2.id), "expected_qty": "20", "unit_cost": "3.00"},
            ],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 201
    order_id = uuid.UUID(resp.json()["id"])

    # Verify order in DB.
    order = db_session.get(PurchaseOrder, order_id)
    assert order is not None
    assert order.supplier_name == "Persistencia Test"

    # Verify items and costs.
    items = db_session.scalars(
        sa_select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order_id)
    ).all()
    assert len(items) == 2

    for item in items:
        costs = db_session.scalars(
            sa_select(PurchaseOrderItemCost).where(
                PurchaseOrderItemCost.purchase_order_item_id == item.id
            )
        ).all()
        assert len(costs) == 1
        assert costs[0].unit_cost > Decimal("0")


# ---------------------------------------------------------------------------
# EP-2: GET /api/v1/purchase-orders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_orders_owner_all_status(
    client: AsyncClient,
    owner_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """Owner can list all orders."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    _make_po_item(db_session, order, p1, owner_user.id)

    resp = await client.get(
        "/api/v1/purchase-orders",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [d["id"] for d in data]
    assert str(order.id) in ids


@pytest.mark.asyncio
async def test_list_orders_admin_ok(
    client: AsyncClient,
    admin_token: str,
    db_session: Session,
    admin_user,
):
    """Admin can list orders."""
    resp = await client.get(
        "/api/v1/purchase-orders",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_orders_cocinero_forbidden(
    client: AsyncClient,
    cocinero_token: str,
):
    """Cocinero cannot list orders (EP-2) — 403."""
    resp = await client.get(
        "/api/v1/purchase-orders",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_orders_filter_open(
    client: AsyncClient,
    owner_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """?status=open only returns open orders."""
    p1, p2 = two_products
    open_order = _make_order(db_session, owner_user.id, supplier="Open Supplier")
    _make_po_item(db_session, open_order, p1, owner_user.id, expected_qty="10")

    closed_order = _make_order(db_session, owner_user.id, supplier="Closed Supplier")
    _make_event(db_session, closed_order, "closed_manual", owner_user.id)

    resp = await client.get(
        "/api/v1/purchase-orders?status=open",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = [d["id"] for d in data]
    assert str(open_order.id) in ids
    assert str(closed_order.id) not in ids


@pytest.mark.asyncio
async def test_list_orders_filter_closed(
    client: AsyncClient,
    owner_token: str,
    db_session: Session,
    owner_user,
):
    """?status=closed only returns closed orders."""
    closed_order = _make_order(db_session, owner_user.id, supplier="Closed One")
    _make_event(db_session, closed_order, "closed_auto", owner_user.id)

    open_order = _make_order(db_session, owner_user.id, supplier="Still Open")

    resp = await client.get(
        "/api/v1/purchase-orders?status=closed",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    ids = [d["id"] for d in data]
    assert str(closed_order.id) in ids
    assert str(open_order.id) not in ids


@pytest.mark.asyncio
async def test_list_orders_derived_status_correct(
    client: AsyncClient,
    owner_token: str,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """Create order → partial partida → partially_received; final partida → closed."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id, supplier="Status Test")
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="20")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="5.00")

    # First partial partida via EP-6.
    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [
                {"purchase_order_item_id": str(po_item.id), "received_qty": "10"}
            ]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["order_status"] == "partially_received"

    # Check EP-2 shows partially_received.
    resp2 = await client.get(
        "/api/v1/purchase-orders",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    data = resp2.json()
    order_data = next((d for d in data if d["id"] == str(order.id)), None)
    assert order_data is not None
    assert order_data["derived_status"] == "partially_received"

    # Final partida — completes order.
    resp3 = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [
                {"purchase_order_item_id": str(po_item.id), "received_qty": "10"}
            ]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp3.status_code == 201
    assert resp3.json()["order_status"] == "closed"

    # EP-2 now shows closed.
    resp4 = await client.get(
        "/api/v1/purchase-orders",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    data4 = resp4.json()
    order_data4 = next((d for d in data4 if d["id"] == str(order.id)), None)
    assert order_data4["derived_status"] == "closed"


@pytest.mark.asyncio
async def test_list_orders_pending_summary_correct(
    client: AsyncClient,
    owner_token: str,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """pending_summary shows 'faltan X kg PRODUCT' for partially_received orders."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id, supplier="Summary Test")
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="40")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="7.00")

    # Receive partial.
    await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "5"}]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )

    resp = await client.get(
        "/api/v1/purchase-orders",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    data = resp.json()
    order_data = next((d for d in data if d["id"] == str(order.id)), None)
    assert order_data is not None
    assert order_data["pending_summary"] is not None
    assert "35" in order_data["pending_summary"]
    assert "POLLO" in order_data["pending_summary"]


@pytest.mark.asyncio
async def test_list_orders_total_ordered_calculation(
    client: AsyncClient,
    owner_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """total_ordered = Σ(expected_qty × unit_cost)."""
    p1, p2 = two_products
    order = _make_order(db_session, owner_user.id, supplier="Totals Test")
    item1 = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="100")
    _make_po_cost(db_session, item1, owner_user.id, unit_cost="7.00")
    item2 = _make_po_item(db_session, order, p2, owner_user.id, expected_qty="20")
    _make_po_cost(db_session, item2, owner_user.id, unit_cost="9.50")

    resp = await client.get(
        "/api/v1/purchase-orders",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    data = resp.json()
    order_data = next((d for d in data if d["id"] == str(order.id)), None)
    # 100×7 + 20×9.5 = 700 + 190 = 890
    assert float(order_data["total_ordered"]) == pytest.approx(890.0)


# ---------------------------------------------------------------------------
# EP-3: GET /api/v1/purchase-orders/{order_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_order_owner_ok(
    client: AsyncClient,
    owner_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """Owner can fetch order detail."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")
    _make_po_cost(db_session, item, owner_user.id, unit_cost="5.00")

    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(order.id)
    assert "items" in data
    assert "total_ordered" in data
    assert "partida_count" in data


@pytest.mark.asyncio
async def test_get_order_admin_ok(
    client: AsyncClient,
    admin_token: str,
    db_session: Session,
    admin_user,
):
    """Admin can fetch order detail."""
    order = _make_order(db_session, admin_user.id)
    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_order_cocinero_forbidden(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
):
    """Cocinero cannot access order detail — 403."""
    order = _make_order(db_session, owner_user.id)
    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_order_404(
    client: AsyncClient,
    owner_token: str,
):
    """Non-existent order_id → 404."""
    resp = await client.get(
        f"/api/v1/purchase-orders/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_order_items_include_pending_qty(
    client: AsyncClient,
    owner_token: str,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """Items in detail response show correct pending_qty after a partida."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="100")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="7.00")

    # Partial partida.
    await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "60"}]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )

    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    data = resp.json()
    item_data = data["items"][0]
    assert float(item_data["received_qty"]) == pytest.approx(60.0)
    assert float(item_data["pending_qty"]) == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# EP-4: GET /api/v1/purchase-orders/pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_cocinero_ok(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """Cocinero can fetch pending orders."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    _make_po_item(db_session, order, p1, owner_user.id)

    resp = await client.get(
        "/api/v1/purchase-orders/pending",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [d["id"] for d in data]
    assert str(order.id) in ids


@pytest.mark.asyncio
async def test_pending_admin_ok(
    client: AsyncClient,
    admin_token: str,
):
    """Admin can also fetch pending orders."""
    resp = await client.get(
        "/api/v1/purchase-orders/pending",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_pending_owner_forbidden(
    client: AsyncClient,
    owner_token: str,
):
    """Owner does NOT use /pending (uses EP-2 with filters) — 403."""
    resp = await client.get(
        "/api/v1/purchase-orders/pending",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pending_no_monetary_fields(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """REGLA DE ORO: pending response must not contain any monetary fields."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    item = _make_po_item(db_session, order, p1, owner_user.id)
    _make_po_cost(db_session, item, owner_user.id, unit_cost="99.99")

    resp = await client.get(
        "/api/v1/purchase-orders/pending",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 200
    raw_text = resp.text

    # These fields must not appear in the response at all.
    for forbidden_key in ("unit_cost", "total_ordered", "total_received", "pending_amount"):
        assert forbidden_key not in raw_text, (
            f"Monetary field '{forbidden_key}' found in /pending response — REGLA DE ORO violation"
        )

    # Also check the schema explicitly.
    for item_data in resp.json():
        assert "unit_cost" not in item_data
        assert "total_ordered" not in item_data
        assert "total_received" not in item_data
        assert "pending_amount" not in item_data


@pytest.mark.asyncio
async def test_pending_only_open_and_partially_received(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """Closed and annulled orders must not appear in /pending."""
    p1, _ = two_products
    open_order = _make_order(db_session, owner_user.id, supplier="Open")
    _make_po_item(db_session, open_order, p1, owner_user.id)

    closed_order = _make_order(db_session, owner_user.id, supplier="Closed")
    _make_event(db_session, closed_order, "closed_auto", owner_user.id)

    annulled_order = _make_order(db_session, owner_user.id, supplier="Annulled")
    _make_event(db_session, annulled_order, "annulled", owner_user.id)

    resp = await client.get(
        "/api/v1/purchase-orders/pending",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    data = resp.json()
    ids = {d["id"] for d in data}

    assert str(open_order.id) in ids
    assert str(closed_order.id) not in ids
    assert str(annulled_order.id) not in ids


@pytest.mark.asyncio
async def test_pending_summary_string_format(
    client: AsyncClient,
    cocinero_token: str,
    owner_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """pending_items_summary format is correct for partial and open orders."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id, supplier="Format Test")
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="40")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="7.00")

    # Open order → "todo pendiente".
    resp = await client.get(
        "/api/v1/purchase-orders/pending",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    data = resp.json()
    order_item = next((d for d in data if d["id"] == str(order.id)), None)
    assert order_item is not None
    assert order_item["pending_items_summary"] == "todo pendiente"

    # Partial partida → summary with numbers.
    await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "5"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )

    resp2 = await client.get(
        "/api/v1/purchase-orders/pending",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    data2 = resp2.json()
    order_item2 = next((d for d in data2 if d["id"] == str(order.id)), None)
    assert order_item2 is not None
    summary = order_item2["pending_items_summary"]
    assert summary.startswith("faltan ")
    assert "POLLO" in summary
    assert "35" in summary


# ---------------------------------------------------------------------------
# EP-5: GET /api/v1/purchase-orders/{id}/partida-draft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partida_draft_cocinero_ok(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """Cocinero can fetch the partida draft."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="50")

    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}/partida-draft",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["order_id"] == str(order.id)
    assert data["partida_number"] == 1
    assert len(data["items"]) == 1
    assert float(data["items"][0]["pending_qty"]) == pytest.approx(50.0)
    assert float(data["items"][0]["already_received"]) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_partida_draft_admin_ok(
    client: AsyncClient,
    admin_token: str,
    db_session: Session,
    admin_user,
):
    """Admin can also fetch partida draft."""
    order = _make_order(db_session, admin_user.id)
    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}/partida-draft",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_partida_draft_owner_forbidden(
    client: AsyncClient,
    owner_token: str,
    db_session: Session,
    owner_user,
):
    """Owner does not use the capture screen — 403."""
    order = _make_order(db_session, owner_user.id)
    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}/partida-draft",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_partida_draft_404(
    client: AsyncClient,
    cocinero_token: str,
):
    """Non-existent order → 404."""
    resp = await client.get(
        f"/api/v1/purchase-orders/{uuid.uuid4()}/partida-draft",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_partida_draft_409_on_closed_order(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
):
    """Closed order → 409."""
    order = _make_order(db_session, owner_user.id)
    _make_event(db_session, order, "closed_auto", owner_user.id)

    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}/partida-draft",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_partida_draft_409_on_annulled_order(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
):
    """Annulled order → 409."""
    order = _make_order(db_session, owner_user.id)
    _make_event(db_session, order, "annulled", owner_user.id)

    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}/partida-draft",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_partida_draft_no_monetary_fields(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """REGLA DE ORO: partida-draft must not expose monetary fields."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="99.99")

    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}/partida-draft",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 200
    raw_text = resp.text

    for forbidden_key in ("unit_cost", "total_ordered", "total_received", "pending_amount"):
        assert forbidden_key not in raw_text, (
            f"Monetary field '{forbidden_key}' found in partida-draft — REGLA DE ORO violation"
        )


@pytest.mark.asyncio
async def test_partida_draft_number_increments(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """partida_number increments after each validated partida."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="30")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="5.00")

    resp1 = await client.get(
        f"/api/v1/purchase-orders/{order.id}/partida-draft",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp1.json()["partida_number"] == 1

    # Validate partial partida.
    await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "10"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )

    resp2 = await client.get(
        f"/api/v1/purchase-orders/{order.id}/partida-draft",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp2.json()["partida_number"] == 2


@pytest.mark.asyncio
async def test_partida_draft_pending_qty_after_previous_partida(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """pending_qty reflects what's left after previous partidas."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="40")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="5.00")

    # Receive 25 in first partida.
    await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "25"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )

    resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}/partida-draft",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    data = resp.json()
    assert float(data["items"][0]["pending_qty"]) == pytest.approx(15.0)
    assert float(data["items"][0]["already_received"]) == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# EP-6: POST /api/v1/purchase-orders/{id}/partidas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_partida_cocinero_ok(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """Cocinero validates a partial partida — delivery + delivery_items created."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="100")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="7.00")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "60"}]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["partida_number"] == 1
    assert data["order_id"] == str(order.id)
    assert data["order_status"] == "partially_received"
    assert "delivery_id" in data

    # Verify delivery was created in DB.
    delivery_id = uuid.UUID(data["delivery_id"])
    delivery = db_session.get(Delivery, delivery_id)
    assert delivery is not None
    assert delivery.status == "validada"
    assert delivery.purchase_order_id == order.id


@pytest.mark.asyncio
async def test_validate_partida_admin_ok(
    client: AsyncClient,
    admin_token: str,
    db_session: Session,
    admin_user,
    two_products,
):
    """Admin can validate partidas."""
    p1, _ = two_products
    order = _make_order(db_session, admin_user.id)
    po_item = _make_po_item(db_session, order, p1, admin_user.id, expected_qty="10")
    _make_po_cost(db_session, po_item, admin_user.id, unit_cost="5.00")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "5"}]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_validate_partida_owner_forbidden(
    client: AsyncClient,
    owner_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """Owner cannot validate partidas — 403."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "5"}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_validate_partida_missing_items_400(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """Body missing items from the order → 400."""
    p1, p2 = two_products
    order = _make_order(db_session, owner_user.id)
    po_item1 = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")
    _make_po_item(db_session, order, p2, owner_user.id, expected_qty="5")

    # Only sending one item when two exist.
    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item1.id), "received_qty": "5"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_validate_partida_extra_items_400(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """Body includes item IDs not belonging to the order → 400."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")

    # Send a fake item ID.
    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [
                {"purchase_order_item_id": str(po_item.id), "received_qty": "5"},
                {"purchase_order_item_id": str(uuid.uuid4()), "received_qty": "3"},
            ]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_validate_partida_item_not_leaf_400(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """Body references a corrected (non-leaf) item → 400."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    root_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")
    _make_po_item(
        db_session, order, p1, owner_user.id, expected_qty="15", corrects_id=root_item.id
    )

    # Body uses the OLD (root) item — should fail.
    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [{"purchase_order_item_id": str(root_item.id), "received_qty": "10"}]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_validate_partida_negative_qty_400(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """received_qty < 0 → 422 (schema validation)."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "-1"}]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validate_partida_404(
    client: AsyncClient,
    cocinero_token: str,
):
    """Non-existent order → 404."""
    resp = await client.post(
        f"/api/v1/purchase-orders/{uuid.uuid4()}/partidas",
        json={"items": [{"purchase_order_item_id": str(uuid.uuid4()), "received_qty": "1"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_validate_partida_409_on_annulled(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    two_products,
):
    """Annulled order → 409."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")
    _make_event(db_session, order, "annulled", owner_user.id)

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "5"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_validate_partida_zero_qty_ok(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """received_qty = 0 is valid (product did not arrive)."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="5.00")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "0"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["order_status"] == "open"  # nothing received → order stays open


@pytest.mark.asyncio
async def test_validate_partida_all_zero_keeps_order_open(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """Validating a partida with all received_qty=0 must keep order_status='open'.

    Verifies consistency between EP-6 response and EP-3 GET detail:
    derive_status is the single source of truth and must agree on both paths.
    """
    p1, p2 = two_products
    order = _make_order(db_session, owner_user.id, supplier="All-Zero Test")
    po_item1 = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")
    _make_po_cost(db_session, po_item1, owner_user.id, unit_cost="3.00")
    po_item2 = _make_po_item(db_session, order, p2, owner_user.id, expected_qty="5")
    _make_po_cost(db_session, po_item2, owner_user.id, unit_cost="2.00")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [
                {"purchase_order_item_id": str(po_item1.id), "received_qty": "0"},
                {"purchase_order_item_id": str(po_item2.id), "received_qty": "0"},
            ]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["order_status"] == "open"

    # Also verify the GET detail (EP-3) agrees — derive_status is consistent.
    from cocina_control.security.tokens import create_access_token
    owner_token_local = create_access_token(owner_user.id, "owner")
    detail_resp = await client.get(
        f"/api/v1/purchase-orders/{order.id}",
        headers={"Authorization": f"Bearer {owner_token_local}"},
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["derived_status"] == "open"


@pytest.mark.asyncio
async def test_validate_partida_excess_qty_ok(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """received_qty > expected_qty is accepted and recorded (excess)."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="5.00")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "15"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 201
    # Excess → order is closed (saldo = 10 - 15 = -5 <= 0)
    assert resp.json()["order_status"] == "closed"


@pytest.mark.asyncio
async def test_validate_partida_triggers_closed_auto(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """When all items reach pending_qty <= 0, closed_auto event is created."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="5.00")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "10"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["order_status"] == "closed"

    # Verify closed_auto event in DB.
    events = db_session.scalars(
        sa_select(PurchaseOrderStatusEvent).where(
            PurchaseOrderStatusEvent.purchase_order_id == order.id
        )
    ).all()
    assert any(e.event_type == "closed_auto" for e in events)


@pytest.mark.asyncio
async def test_validate_partida_partial_no_closed_auto(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """A partial partida does NOT trigger closed_auto."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="100")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="5.00")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "50"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["order_status"] == "partially_received"

    events = db_session.scalars(
        sa_select(PurchaseOrderStatusEvent).where(
            PurchaseOrderStatusEvent.purchase_order_id == order.id
        )
    ).all()
    assert not any(e.event_type == "closed_auto" for e in events)


@pytest.mark.asyncio
async def test_validate_partida_response_status(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """Verify order_status field in response is correct for each scenario."""
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="20")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="5.00")

    # Partial → partially_received.
    resp1 = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "10"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp1.json()["order_status"] == "partially_received"

    # Complete → closed.
    resp2 = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={"items": [{"purchase_order_item_id": str(po_item.id), "received_qty": "10"}]},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp2.json()["order_status"] == "closed"


@pytest.mark.asyncio
async def test_validate_partida_persists_correct_delivery_and_items(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """Verify that Delivery and DeliveryItem rows are correctly persisted."""
    p1, p2 = two_products
    order = _make_order(db_session, owner_user.id, supplier="Persistencia Partida")
    po_item1 = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="50")
    _make_po_cost(db_session, po_item1, owner_user.id, unit_cost="7.00")
    po_item2 = _make_po_item(db_session, order, p2, owner_user.id, expected_qty="20")
    _make_po_cost(db_session, po_item2, owner_user.id, unit_cost="2.50")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [
                {"purchase_order_item_id": str(po_item1.id), "received_qty": "30"},
                {"purchase_order_item_id": str(po_item2.id), "received_qty": "20"},
            ]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 201
    delivery_id = uuid.UUID(resp.json()["delivery_id"])

    # Delivery row.
    delivery = db_session.get(Delivery, delivery_id)
    assert delivery is not None
    assert delivery.status == "validada"
    assert delivery.supplier_name == "Persistencia Partida"
    assert delivery.purchase_order_id == order.id
    assert delivery.validated_at is not None

    # DeliveryItem rows.
    di_rows = db_session.scalars(
        sa_select(DeliveryItem).where(DeliveryItem.delivery_id == delivery_id)
    ).all()
    assert len(di_rows) == 2

    received_map = {di.purchase_order_item_id: di.received_qty for di in di_rows}
    assert received_map[po_item1.id] == Decimal("30")
    assert received_map[po_item2.id] == Decimal("20")


# ---------------------------------------------------------------------------
# EP-6 — Fix 3: anti-duplicate validator in PartidaCreate (SEG-BAJO H-3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_partida_duplicate_item_ids_422(
    client: AsyncClient,
    cocinero_token: str,
    db_session: Session,
    owner_user,
    cocinero_user,
    two_products,
):
    """POST /partidas with duplicate purchase_order_item_id entries must return 422.

    Without the model_validator, the second duplicate silently overwrites the
    first in the dict comprehension, losing data without raising an error.
    The Pydantic validator catches this at deserialization time.
    """
    p1, _ = two_products
    order = _make_order(db_session, owner_user.id)
    po_item = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="10")
    _make_po_cost(db_session, po_item, owner_user.id, unit_cost="5.00")

    resp = await client.post(
        f"/api/v1/purchase-orders/{order.id}/partidas",
        json={
            "items": [
                {"purchase_order_item_id": str(po_item.id), "received_qty": "3"},
                {"purchase_order_item_id": str(po_item.id), "received_qty": "7"},
            ]
        },
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert resp.status_code == 422
    # Verify the validation error message references the duplicate constraint.
    detail = resp.json()["detail"]
    assert any("duplicate" in str(e).lower() for e in detail)


# ---------------------------------------------------------------------------
# GET /purchase-orders/received — historial de partidas (issue #146)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_received_lists_validated_partidas_newest_first(
    client: AsyncClient,
    db_session: Session,
    cocinero_token: str,
    cocinero_user,
    owner_user,
) -> None:
    """El historial devuelve partidas validadas con resumen humano, sin dinero."""
    p1 = _make_product(db_session, owner_user.id, "CERDO HISTORIAL", unit="kg")
    order = _make_order(db_session, owner_user.id, supplier="CARNICERIA HISTORIAL")
    poi = _make_po_item(db_session, order, p1, owner_user.id, expected_qty="30")
    d1 = _make_validated_delivery(db_session, order, cocinero_user.id)
    _make_delivery_item(
        db_session, d1, p1, poi, cocinero_user.id,
        announced_qty="18", received_qty="18",
    )
    db_session.flush()

    response = await client.get(
        "/api/v1/purchase-orders/received",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    ours = [r for r in data if r["supplier_name"] == "CARNICERIA HISTORIAL"]
    assert len(ours) == 1
    partida = ours[0]
    assert partida["received_summary"] == "18 kg CERDO HISTORIAL"
    assert partida["validated_by_name"] == cocinero_user.name
    assert partida["validated_at"] is not None
    # Regla de oro: sin campos monetarios en pantallas de cocinero
    for campo in ("unit_cost", "total_ordered", "total_received", "pending_amount"):
        assert campo not in partida


@pytest.mark.asyncio
async def test_received_owner_returns_403(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """El historial de ENTRADA es pantalla de cocinero/admin — owner 403."""
    response = await client.get(
        "/api/v1/purchase-orders/received",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 403
