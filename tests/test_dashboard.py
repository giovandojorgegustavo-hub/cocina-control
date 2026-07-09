"""Integration tests for dashboard endpoints (issue #14).

Covers all 3 endpoints:
  GET /api/v1/dashboard/summary
  GET /api/v1/dashboard/traceability/{product_id}
  GET /api/v1/dashboard/export

Fixtures inherited from conftest.py:
  owner_user, operator_user, owner_token, operator_token,
  client, db_session.
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.delivery_order import DeliveryOrder, DeliveryOrderItem
from cocina_control.models.inventory import InventoryCount, InventoryCountItem
from cocina_control.models.product import Product

_BASE = "/api/v1/dashboard"
_TZ_ARG = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# Helper: auth header
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helpers: seed helpers
# ---------------------------------------------------------------------------


def _make_product(
    session: Session,
    owner_id: uuid.UUID,
    name: str,
    unit: str = "kg",
    is_active: bool = True,
    low_stock_threshold: str | None = None,
) -> Product:
    p = Product(
        id=uuid.uuid4(),
        name=name.upper(),
        unit=unit,
        is_active=is_active,
        low_stock_threshold=low_stock_threshold,
        created_by=owner_id,
    )
    session.add(p)
    session.flush()
    return p


def _make_delivery(
    session: Session,
    owner_id: uuid.UUID,
    status: str = "validada",
    validated_at: datetime | None = None,
) -> Delivery:
    now = datetime.now(UTC)
    d = Delivery(
        id=uuid.uuid4(),
        supplier_name="TEST SUPPLIER",
        status=status,
        created_by=owner_id,
        created_at=now,
        validated_at=validated_at,
        validated_by=owner_id if validated_at else None,
    )
    session.add(d)
    session.flush()
    return d


def _make_delivery_item(
    session: Session,
    delivery_id: uuid.UUID,
    product_id: uuid.UUID,
    created_by: uuid.UUID,
    announced_qty: str = "10",
    received_qty: str | None = "10",
    corrects_id: uuid.UUID | None = None,
    reason: str | None = None,
    created_at: datetime | None = None,
) -> DeliveryItem:
    item = DeliveryItem(
        id=uuid.uuid4(),
        delivery_id=delivery_id,
        product_id=product_id,
        announced_qty=announced_qty,
        received_qty=received_qty,
        corrects_id=corrects_id,
        reason=reason,
        created_by=created_by,
        created_at=created_at or datetime.now(UTC),
    )
    session.add(item)
    session.flush()
    return item


def _make_delivery_order(
    session: Session,
    created_by: uuid.UUID,
    status: str = "completed",
    completed_at: datetime | None = None,
) -> DeliveryOrder:
    now = datetime.now(UTC)
    o = DeliveryOrder(
        id=uuid.uuid4(),
        status=status,
        photo_url="/photos/test.jpg",
        photo_at=now,
        photo_by=created_by,
        completed_at=completed_at or (now if status == "completed" else None),
        completed_by=created_by if status == "completed" else None,
        created_by=created_by,
        created_at=now,
    )
    session.add(o)
    session.flush()
    return o


def _make_delivery_order_item(
    session: Session,
    order_id: uuid.UUID,
    product_id: uuid.UUID,
    created_by: uuid.UUID,
    quantity: str = "2",
    corrects_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> DeliveryOrderItem:
    item = DeliveryOrderItem(
        id=uuid.uuid4(),
        delivery_order_id=order_id,
        product_id=product_id,
        quantity=quantity,
        corrects_id=corrects_id,
        created_by=created_by,
        created_at=created_at or datetime.now(UTC),
    )
    session.add(item)
    session.flush()
    return item


def _make_count(
    session: Session,
    created_by: uuid.UUID,
    status: str = "completed",
    completed_at: datetime | None = None,
) -> InventoryCount:
    now = datetime.now(UTC)
    c = InventoryCount(
        id=uuid.uuid4(),
        status=status,
        started_at=now,
        started_by=created_by,
        completed_at=completed_at or (now if status == "completed" else None),
        completed_by=created_by if status == "completed" else None,
        created_by=created_by,
        created_at=now,
    )
    session.add(c)
    session.flush()
    return c


def _make_count_item(
    session: Session,
    count_id: uuid.UUID,
    product_id: uuid.UUID,
    created_by: uuid.UUID,
    quantity: str = "10",
    corrects_id: uuid.UUID | None = None,
    reason: str | None = None,
    created_at: datetime | None = None,
) -> InventoryCountItem:
    item = InventoryCountItem(
        id=uuid.uuid4(),
        inventory_count_id=count_id,
        product_id=product_id,
        quantity=quantity,
        corrects_id=corrects_id,
        reason=reason,
        created_by=created_by,
        created_at=created_at or datetime.now(UTC),
    )
    session.add(item)
    session.flush()
    return item


# ---------------------------------------------------------------------------
# Date helpers — build from/to query params for "today" in Argentina time.
# ---------------------------------------------------------------------------


def _arg_today() -> str:
    """Today in Argentina (UTC-3) as YYYY-MM-DD string."""
    return datetime.now(_TZ_ARG).strftime("%Y-%m-%d")


def _arg_yesterday() -> str:
    """Yesterday in Argentina (UTC-3) as YYYY-MM-DD string."""
    return (datetime.now(_TZ_ARG) - timedelta(days=1)).strftime("%Y-%m-%d")


def _arg_tomorrow() -> str:
    """Tomorrow in Argentina (UTC-3) as YYYY-MM-DD string."""
    return (datetime.now(_TZ_ARG) + timedelta(days=1)).strftime("%Y-%m-%d")


def _arg_past(days: int) -> str:
    """N days ago in Argentina."""
    return (datetime.now(_TZ_ARG) - timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# seed_scenario: a complete standard scenario for summary tests
#
# Creates:
#   - 2 active products (PALTA with threshold=5, POLLO without threshold)
#   - 1 completed count BEFORE from_date   → stock_inicio for PALTA and POLLO
#   - 1 validated delivery IN range        → entries for PALTA
#   - 1 completed delivery order IN range  → consumed for PALTA
#   - Returns refs for assertions
# ---------------------------------------------------------------------------


def seed_scenario(session: Session, owner_id: uuid.UUID, operator_id: uuid.UUID):
    """Seed a predictable scenario:
      PALTA:
        stock_inicio (count 10 days ago) = 20
        entries_qty  (delivery in range, validated today) = 8
        stock_actual (count in range, completed today)    = 25
        consumption = 20 + 8 - 25 = 3   (positive, no alert)
      POLLO:
        no prior count → consumption_available=False
      Expected query range: from=today&to=today
    """
    palta = _make_product(session, owner_id, "PALTA", low_stock_threshold="5")
    pollo = _make_product(session, owner_id, "POLLO")

    # Count 10 days ago (BEFORE from_date = today) — stock_inicio for PALTA.
    ten_days_ago = datetime.now(UTC) - timedelta(days=10)
    prior_count = _make_count(session, operator_id, completed_at=ten_days_ago)
    prior_count.started_at = ten_days_ago
    prior_count.created_at = ten_days_ago
    session.flush()
    _make_count_item(session, prior_count.id, palta.id, operator_id, "20", created_at=ten_days_ago)

    # Validated delivery today (IN range) — entries_qty = 8.
    in_range_ts = datetime.now(UTC) - timedelta(minutes=30)
    delivery = _make_delivery(session, owner_id, "validada", validated_at=in_range_ts)
    delivery.created_at = in_range_ts
    session.flush()
    _make_delivery_item(session, delivery.id, palta.id, owner_id, "8", "8", created_at=in_range_ts)

    # Count today (IN range) — stock_actual for PALTA = 25.
    count_in_range = _make_count(session, operator_id, completed_at=in_range_ts)
    count_in_range.started_at = in_range_ts
    count_in_range.created_at = in_range_ts
    session.flush()
    _make_count_item(
        session, count_in_range.id, palta.id, operator_id, "25", created_at=in_range_ts
    )

    return palta, pollo


# ===========================================================================
# SUMMARY — GET /dashboard/summary
# ===========================================================================


@pytest.mark.asyncio
async def test_summary_no_prior_count_shows_consumption_unavailable(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """A product with no prior count returns consumption_available=False."""
    _make_product(db_session, owner_user.id, "HARINA")

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    products = resp.json()["products"]
    assert len(products) == 1
    p = products[0]
    assert p["name"] == "HARINA"
    assert p["consumption_available"] is False
    assert p["consumption"] is None


@pytest.mark.asyncio
async def test_summary_consumption_formula_correct(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Verify consumption = stock_inicio + entries - stock_actual.

    Scenario:
      stock_inicio = 20 (count before range)
      entries_qty  = 8  (validated delivery in range)
      stock_actual = 25 (count in range)
      consumption  = 20 + 8 - 25 = 3
    """
    palta, _ = seed_scenario(db_session, owner_user.id, operator_user.id)

    # Range: today only (seed_scenario puts in-range events in the last 30 minutes).
    today = _arg_today()

    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    products = {p["name"]: p for p in resp.json()["products"]}
    palta_row = products["PALTA"]

    assert palta_row["consumption_available"] is True
    assert palta_row["entries_qty"] == "8"
    assert palta_row["consumption"] == "3"
    assert palta_row["alert"] is False


@pytest.mark.asyncio
async def test_summary_alert_on_negative_consumption(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """consumption < 0 triggers alert.

    stock_inicio=5, entries=0, stock_actual=10 → consumption = 5+0-10 = -5.
    """
    palta = _make_product(db_session, owner_user.id, "PALTA")

    ten_days_ago = datetime.now(UTC) - timedelta(days=10)
    prior_count = _make_count(db_session, operator_user.id, completed_at=ten_days_ago)
    prior_count.started_at = ten_days_ago
    prior_count.created_at = ten_days_ago
    db_session.flush()
    _make_count_item(
        db_session, prior_count.id, palta.id, operator_user.id, "5", created_at=ten_days_ago
    )

    # Count in range: today, 30 minutes ago.
    in_range_ts = datetime.now(UTC) - timedelta(minutes=30)
    count_in_range = _make_count(db_session, operator_user.id, completed_at=in_range_ts)
    count_in_range.started_at = in_range_ts
    count_in_range.created_at = in_range_ts
    db_session.flush()
    _make_count_item(
        db_session, count_in_range.id, palta.id, operator_user.id, "10", created_at=in_range_ts
    )

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    products = {p["name"]: p for p in resp.json()["products"]}
    palta_row = products["PALTA"]

    assert palta_row["consumption_available"] is True
    assert palta_row["alert"] is True
    # consumption = 5 + 0 - 10 = -5
    assert palta_row["consumption"] == "-5"


@pytest.mark.asyncio
async def test_summary_low_stock_list_filters_by_threshold(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Product without threshold never appears in low_stock; with threshold and
    stock below threshold it does appear."""
    # PALTA: threshold=5, we'll give it stock_now=3 (below threshold).
    palta = _make_product(db_session, owner_user.id, "PALTA", low_stock_threshold="5")
    # POLLO: no threshold.
    pollo = _make_product(db_session, owner_user.id, "POLLO")

    # Completed count with stock_now=3 for PALTA and 1 for POLLO.
    now = datetime.now(UTC)
    count = _make_count(db_session, operator_user.id, completed_at=now)
    count.started_at = now
    count.created_at = now
    db_session.flush()
    _make_count_item(db_session, count.id, palta.id, operator_user.id, "3", created_at=now)
    _make_count_item(db_session, count.id, pollo.id, operator_user.id, "1", created_at=now)

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    low_stock = resp.json()["low_stock"]
    low_stock_names = {i["name"] for i in low_stock}

    # PALTA is below threshold → appears.
    assert "PALTA" in low_stock_names
    # POLLO has no threshold → never appears, regardless of qty.
    assert "POLLO" not in low_stock_names


@pytest.mark.asyncio
async def test_summary_orders_summary_counts_photo_only(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """orders_summary splits completed vs photo-only (pending)."""
    now = datetime.now(UTC)

    # 2 completed orders.
    for _ in range(2):
        o = _make_delivery_order(db_session, operator_user.id, status="completed", completed_at=now)
        o.created_at = now
        db_session.flush()

    # 1 photo-only (pending).
    pending = _make_delivery_order(db_session, operator_user.id, status="pending")
    pending.created_at = now
    db_session.flush()

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    summary = resp.json()["orders_summary"]
    assert summary["completed_count"] == 2
    assert summary["photo_only_count"] == 1


@pytest.mark.asyncio
async def test_summary_operator_returns_403(
    client: AsyncClient,
    operator_token: str,
):
    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(operator_token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_summary_no_auth_returns_401(client: AsyncClient):
    today = _arg_today()
    resp = await client.get(f"{_BASE}/summary?from={today}&to={today}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_summary_only_considers_validated_deliveries(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """A delivery in status pending or en_verificacion must NOT count as entries."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    ten_days_ago = datetime.now(UTC) - timedelta(days=10)
    prior_count = _make_count(db_session, operator_user.id, completed_at=ten_days_ago)
    prior_count.started_at = ten_days_ago
    prior_count.created_at = ten_days_ago
    db_session.flush()
    _make_count_item(
        db_session, prior_count.id, palta.id, operator_user.id, "10", created_at=ten_days_ago
    )

    # Count in range = 10 (same as inicio, no change if no entries counted).
    in_range_ts = datetime.now(UTC) - timedelta(minutes=30)
    count_in_range = _make_count(db_session, operator_user.id, completed_at=in_range_ts)
    count_in_range.started_at = in_range_ts
    count_in_range.created_at = in_range_ts
    db_session.flush()
    _make_count_item(
        db_session, count_in_range.id, palta.id, operator_user.id, "10", created_at=in_range_ts
    )

    # Pending delivery (should NOT count as entries).
    pending_delivery = _make_delivery(
        db_session, owner_user.id, status="no_leida", validated_at=None
    )
    pending_delivery.created_at = in_range_ts
    db_session.flush()
    _make_delivery_item(
        db_session, pending_delivery.id, palta.id, owner_user.id, "15", None, created_at=in_range_ts
    )

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    products = {p["name"]: p for p in resp.json()["products"]}
    palta_row = products["PALTA"]

    # entries_qty must be 0 — the pending delivery should not count.
    assert palta_row["entries_qty"] == "0"
    # consumption = 10 + 0 - 10 = 0.
    assert palta_row["consumption"] == "0"


@pytest.mark.asyncio
async def test_summary_only_considers_completed_orders(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Pending orders must NOT affect stock_now or consumption."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    # Completed count gives stock baseline = 20.
    now = datetime.now(UTC)
    count = _make_count(db_session, operator_user.id, completed_at=now - timedelta(hours=2))
    count.started_at = now - timedelta(hours=2)
    count.created_at = now - timedelta(hours=2)
    db_session.flush()
    _make_count_item(
        db_session, count.id, palta.id, operator_user.id, "20",
        created_at=now - timedelta(hours=2),
    )

    # Pending order (photo-only) should NOT deduct from stock.
    pending_order = _make_delivery_order(db_session, operator_user.id, status="pending")
    pending_order.created_at = now
    db_session.flush()
    _make_delivery_order_item(db_session, pending_order.id, palta.id, operator_user.id, "5")

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    products = {p["name"]: p for p in resp.json()["products"]}
    palta_row = products["PALTA"]

    # stock_now = 20 (count) + 0 entries - 0 orders (pending doesn't count).
    assert palta_row["stock_now"] == "20"


@pytest.mark.asyncio
async def test_summary_uses_leaf_items(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """A corrected delivery item must not double-count: only the leaf counts."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    # Count before range.
    ten_days_ago = datetime.now(UTC) - timedelta(days=10)
    prior_count = _make_count(db_session, operator_user.id, completed_at=ten_days_ago)
    prior_count.started_at = ten_days_ago
    prior_count.created_at = ten_days_ago
    db_session.flush()
    _make_count_item(
        db_session, prior_count.id, palta.id, operator_user.id, "10", created_at=ten_days_ago
    )

    # Validated delivery today (in range) with a correction.
    in_range_ts = datetime.now(UTC) - timedelta(minutes=30)
    delivery = _make_delivery(db_session, owner_user.id, "validada", validated_at=in_range_ts)
    delivery.created_at = in_range_ts
    db_session.flush()

    # Original item: received_qty=5; corrected to 8.
    original = _make_delivery_item(
        db_session, delivery.id, palta.id, owner_user.id, "8", "5", created_at=in_range_ts
    )
    _make_delivery_item(
        db_session, delivery.id, palta.id, owner_user.id, "8", "8",
        corrects_id=original.id, created_at=in_range_ts
    )

    # Count in range (today).
    count_in_range = _make_count(db_session, operator_user.id, completed_at=in_range_ts)
    count_in_range.started_at = in_range_ts
    count_in_range.created_at = in_range_ts
    db_session.flush()
    _make_count_item(
        db_session, count_in_range.id, palta.id, operator_user.id, "18", created_at=in_range_ts
    )

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    products = {p["name"]: p for p in resp.json()["products"]}
    palta_row = products["PALTA"]

    # Only the leaf (received=8) counts, not the original (received=5).
    # entries_qty = 8; consumption = 10 + 8 - 18 = 0.
    assert palta_row["entries_qty"] == "8"
    assert palta_row["consumption"] == "0"


# ===========================================================================
# TRACEABILITY — GET /dashboard/traceability/{product_id}
# ===========================================================================


@pytest.mark.asyncio
async def test_traceability_returns_all_events_for_product(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Traceability returns delivery_item, delivery_order_item, and count_item events."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    now = datetime.now(UTC)

    # Validated delivery.
    delivery = _make_delivery(db_session, owner_user.id, "validada", validated_at=now)
    delivery.created_at = now
    db_session.flush()
    d_item = _make_delivery_item(
        db_session, delivery.id, palta.id, operator_user.id, "10", "10", created_at=now
    )

    # Completed order.
    order = _make_delivery_order(db_session, operator_user.id, status="completed", completed_at=now)
    order.created_at = now
    db_session.flush()
    o_item = _make_delivery_order_item(
        db_session, order.id, palta.id, operator_user.id, "3", created_at=now
    )

    # Completed count.
    count = _make_count(db_session, operator_user.id, completed_at=now)
    count.started_at = now
    count.created_at = now
    db_session.flush()
    c_item = _make_count_item(db_session, count.id, palta.id, operator_user.id, "7", created_at=now)

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/traceability/{palta.id}?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    events = resp.json()
    event_ids = {e["id"] for e in events}
    assert str(d_item.id) in event_ids
    assert str(o_item.id) in event_ids
    assert str(c_item.id) in event_ids


@pytest.mark.asyncio
async def test_traceability_ordered_by_date_asc(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Events are ordered by date ascending."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    now = datetime.now(UTC)
    t1 = now - timedelta(hours=5)
    t2 = now - timedelta(hours=3)
    t3 = now - timedelta(hours=1)

    delivery = _make_delivery(db_session, owner_user.id, "validada", validated_at=t1)
    delivery.created_at = t1
    db_session.flush()
    _make_delivery_item(
        db_session, delivery.id, palta.id, operator_user.id, "5", "5", created_at=t1
    )

    count = _make_count(db_session, operator_user.id, completed_at=t2)
    count.started_at = t2
    count.created_at = t2
    db_session.flush()
    _make_count_item(db_session, count.id, palta.id, operator_user.id, "12", created_at=t2)

    order = _make_delivery_order(db_session, operator_user.id, status="completed", completed_at=t3)
    order.created_at = t3
    db_session.flush()
    _make_delivery_order_item(db_session, order.id, palta.id, operator_user.id, "2", created_at=t3)

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/traceability/{palta.id}?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    events = resp.json()
    # Verify ascending order.
    dates = [e["date"] for e in events]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_traceability_includes_corrections(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Traceability includes both the original and the correction row."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    now = datetime.now(UTC)
    delivery = _make_delivery(db_session, owner_user.id, "validada", validated_at=now)
    delivery.created_at = now
    db_session.flush()

    original = _make_delivery_item(
        db_session, delivery.id, palta.id, operator_user.id, "10", "10", created_at=now
    )
    correction = _make_delivery_item(
        db_session, delivery.id, palta.id, operator_user.id, "10", "8",
        corrects_id=original.id, created_at=now
    )

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/traceability/{palta.id}?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    events = resp.json()
    event_ids = {e["id"] for e in events}
    assert str(original.id) in event_ids
    assert str(correction.id) in event_ids

    # Correction event must reference the original.
    corr_event = next(e for e in events if e["id"] == str(correction.id))
    assert corr_event["corrects_id"] == str(original.id)


@pytest.mark.asyncio
async def test_traceability_operator_returns_403(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
):
    palta = _make_product(db_session, owner_user.id, "PALTA")
    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/traceability/{palta.id}?from={today}&to={today}",
        headers=_auth(operator_token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_traceability_nonexistent_product_returns_404(
    client: AsyncClient,
    owner_token: str,
):
    fake_id = uuid.uuid4()
    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/traceability/{fake_id}?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 404


# ===========================================================================
# EXPORT — GET /dashboard/export
# ===========================================================================


@pytest.mark.asyncio
async def test_export_csv_bom_utf8(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """CSV starts with UTF-8 BOM (\xef\xbb\xbf)."""
    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/export?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    content = resp.content
    # BOM is 3 bytes: EF BB BF.
    assert content[:3] == b"\xef\xbb\xbf"


@pytest.mark.asyncio
async def test_export_csv_content_type(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Content-Type must be text/csv; charset=utf-8."""
    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/export?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "utf-8" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_export_csv_filename_from_range(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
):
    """Content-Disposition contains the correct filename with from/to dates."""
    from_d = "2026-07-01"
    to_d = "2026-07-07"
    resp = await client.get(
        f"{_BASE}/export?from={from_d}&to={to_d}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert f"cocina-control_{from_d}_{to_d}.csv" in cd


@pytest.mark.asyncio
async def test_export_csv_includes_all_rows_original_and_corrections(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """CSV must include both the original row and the correction row."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    now = datetime.now(UTC)
    delivery = _make_delivery(db_session, owner_user.id, "validada", validated_at=now)
    delivery.created_at = now
    db_session.flush()

    original = _make_delivery_item(
        db_session, delivery.id, palta.id, operator_user.id, "10", "10", created_at=now
    )
    correction = _make_delivery_item(
        db_session, delivery.id, palta.id, operator_user.id, "10", "8",
        corrects_id=original.id, created_at=now
    )

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/export?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    body = resp.content.decode("utf-8-sig")  # strip BOM
    assert str(original.id) in body
    assert str(correction.id) in body


@pytest.mark.asyncio
async def test_export_csv_filter_by_type_delivery(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """type=delivery returns only delivery_item rows, not count or order rows."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    now = datetime.now(UTC)

    # Delivery item.
    delivery = _make_delivery(db_session, owner_user.id, "validada", validated_at=now)
    delivery.created_at = now
    db_session.flush()
    d_item = _make_delivery_item(
        db_session, delivery.id, palta.id, operator_user.id, "10", "10", created_at=now
    )

    # Count item.
    count = _make_count(db_session, operator_user.id, completed_at=now)
    count.started_at = now
    count.created_at = now
    db_session.flush()
    c_item = _make_count_item(db_session, count.id, palta.id, operator_user.id, "5", created_at=now)

    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/export?from={today}&to={today}&type=delivery",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    body = resp.content.decode("utf-8-sig")
    assert str(d_item.id) in body
    assert str(c_item.id) not in body
    # All rows in the filtered CSV must be delivery_item.
    lines = [
        row for row in body.splitlines()
        if row.strip() and not row.startswith("event_type")
    ]
    for line in lines:
        assert line.startswith("delivery_item")


@pytest.mark.asyncio
async def test_export_csv_operator_returns_403(
    client: AsyncClient,
    operator_token: str,
):
    today = _arg_today()
    resp = await client.get(
        f"{_BASE}/export?from={today}&to={today}",
        headers=_auth(operator_token),
    )
    assert resp.status_code == 403
