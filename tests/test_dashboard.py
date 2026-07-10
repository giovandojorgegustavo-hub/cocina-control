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
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.config import get_settings
from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.delivery_order import DeliveryOrder, DeliveryOrderItem
from cocina_control.models.inventory import InventoryCount, InventoryCountItem
from cocina_control.models.product import Product

_BASE = "/api/v1/dashboard"


def _business_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().business_timezone)


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
    photo_at: datetime | None = None,
) -> DeliveryOrder:
    now = datetime.now(UTC)
    resolved_photo_at = photo_at if photo_at is not None else now
    o = DeliveryOrder(
        id=uuid.uuid4(),
        status=status,
        photo_url="/photos/test.jpg",
        photo_at=resolved_photo_at,
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
# Date helpers — build from/to query params for "today" in the business timezone.
# ---------------------------------------------------------------------------


def _local_today() -> str:
    """Today in the business timezone as YYYY-MM-DD string."""
    return datetime.now(_business_tz()).strftime("%Y-%m-%d")


def _local_yesterday() -> str:
    """Yesterday in the business timezone as YYYY-MM-DD string."""
    return (datetime.now(_business_tz()) - timedelta(days=1)).strftime("%Y-%m-%d")


def _local_tomorrow() -> str:
    """Tomorrow in the business timezone as YYYY-MM-DD string."""
    return (datetime.now(_business_tz()) + timedelta(days=1)).strftime("%Y-%m-%d")


def _local_past(days: int) -> str:
    """N days ago in the business timezone."""
    return (datetime.now(_business_tz()) - timedelta(days=days)).strftime("%Y-%m-%d")


def _local_midday_today_utc() -> datetime:
    """Today at 12:00 in the business timezone, as an aware UTC datetime.

    Used to seed 'in-range' events deterministically: midday of the calendar
    day in the business timezone is always within [today 00:00, today 23:59],
    no matter what UTC time the CI runs at.
    """
    now_local = datetime.now(_business_tz())
    midday_local = now_local.replace(hour=12, minute=0, second=0, microsecond=0)
    return midday_local.astimezone(UTC)


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
    # Use midday in the business timezone so this is always within today's range
    # regardless of what UTC time the CI runs at.
    in_range_ts = _local_midday_today_utc()
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

    today = _local_today()
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
    today = _local_today()

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
    in_range_ts = _local_midday_today_utc()
    count_in_range = _make_count(db_session, operator_user.id, completed_at=in_range_ts)
    count_in_range.started_at = in_range_ts
    count_in_range.created_at = in_range_ts
    db_session.flush()
    _make_count_item(
        db_session, count_in_range.id, palta.id, operator_user.id, "10", created_at=in_range_ts
    )

    today = _local_today()
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

    today = _local_today()
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

    today = _local_today()
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
    today = _local_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(operator_token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_summary_no_auth_returns_401(client: AsyncClient):
    today = _local_today()
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
    in_range_ts = _local_midday_today_utc()
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

    today = _local_today()
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

    today = _local_today()
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
    in_range_ts = _local_midday_today_utc()
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

    today = _local_today()
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

    today = _local_today()
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

    today = _local_today()
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

    today = _local_today()
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
    today = _local_today()
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
    today = _local_today()
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
    today = _local_today()
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
    today = _local_today()
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

    today = _local_today()
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

    today = _local_today()
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
    today = _local_today()
    resp = await client.get(
        f"{_BASE}/export?from={today}&to={today}",
        headers=_auth(operator_token),
    )
    assert resp.status_code == 403


# ===========================================================================
# NEW TESTS — QA/security fixes applied in this iteration
# ===========================================================================


# ---------------------------------------------------------------------------
# Fix 1: CSV injection sanitization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_csv_sanitizes_formula_injection(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Fields starting with formula prefixes (=, +, -, @) must be prefixed with
    a single quote so that Excel/LibreOffice treats them as plain text."""
    # Create a product whose name starts with '=', a classic injection payload.
    p = _make_product(db_session, owner_user.id, "=HACK()")
    # Override the auto-uppercase in _make_product by patching directly.
    # The model uppercases in the helper; set the name directly so we test the
    # actual sanitization path.
    p.name = "=HACK()"
    db_session.flush()

    now = datetime.now(UTC)
    delivery = _make_delivery(db_session, owner_user.id, "validada", validated_at=now)
    delivery.created_at = now
    db_session.flush()
    # Reason field also starts with '='.
    _make_delivery_item(
        db_session,
        delivery.id,
        p.id,
        operator_user.id,
        "5",
        "5",
        reason="=INJECTED()",
        created_at=now,
    )

    today = _local_today()
    resp = await client.get(
        f"{_BASE}/export?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    body = resp.content.decode("utf-8-sig")

    # The sanitized form must appear: the field is prefixed with a single quote.
    assert "'=HACK()" in body
    assert "'=INJECTED()" in body

    # Verify the raw unsanitized forms do NOT appear at a field boundary.
    # A raw injection would appear after a comma (start of field) or at the
    # very start of a CSV cell — both cases produce ",=".  The sanitized form
    # produces ",'=", so checking for ",=" (or the BOM + "=" for first column)
    # is sufficient.
    assert ",=HACK()" not in body
    assert ",=INJECTED()" not in body


# ---------------------------------------------------------------------------
# Fix 2: traceability excludes items from non-completed parents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_traceability_excludes_items_from_pending_orders(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Items of a pending (photo-only) delivery order must NOT appear in
    traceability — pending orders represent unconfirmed consumption."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    now = datetime.now(UTC)

    # A completed order — its item SHOULD appear.
    completed_order = _make_delivery_order(
        db_session, operator_user.id, status="completed", completed_at=now
    )
    completed_order.created_at = now
    db_session.flush()
    completed_item = _make_delivery_order_item(
        db_session, completed_order.id, palta.id, operator_user.id, "3", created_at=now
    )

    # A pending order — its item must NOT appear.
    pending_order = _make_delivery_order(db_session, operator_user.id, status="pending")
    pending_order.created_at = now
    db_session.flush()
    pending_item = _make_delivery_order_item(
        db_session, pending_order.id, palta.id, operator_user.id, "7", created_at=now
    )

    today = _local_today()
    resp = await client.get(
        f"{_BASE}/traceability/{palta.id}?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    event_ids = {e["id"] for e in resp.json()}
    assert str(completed_item.id) in event_ids
    assert str(pending_item.id) not in event_ids


@pytest.mark.asyncio
async def test_traceability_excludes_items_from_no_leida_deliveries(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Items of a non-validated delivery (no_leida) must NOT appear in
    traceability — only items from deliveries in status 'validada' count."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    now = datetime.now(UTC)

    # A validated delivery — its item SHOULD appear.
    validated = _make_delivery(db_session, owner_user.id, "validada", validated_at=now)
    validated.created_at = now
    db_session.flush()
    valid_item = _make_delivery_item(
        db_session, validated.id, palta.id, operator_user.id, "10", "10", created_at=now
    )

    # An unread delivery — its item must NOT appear.
    unread = _make_delivery(db_session, owner_user.id, "no_leida", validated_at=None)
    unread.created_at = now
    db_session.flush()
    unread_item = _make_delivery_item(
        db_session, unread.id, palta.id, operator_user.id, "20", None, created_at=now
    )

    today = _local_today()
    resp = await client.get(
        f"{_BASE}/traceability/{palta.id}?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    event_ids = {e["id"] for e in resp.json()}
    assert str(valid_item.id) in event_ids
    assert str(unread_item.id) not in event_ids


# ---------------------------------------------------------------------------
# Fix 3: orders_summary uses completed_at / photo_at, not created_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orders_summary_uses_completion_dates(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """completed_count must count orders whose completed_at is in range.
    photo_only_count must count pending orders whose photo_at is in range.
    Orders whose created_at is in range but whose event timestamp is outside
    the range must NOT be counted.
    """
    now = datetime.now(UTC)
    yesterday_utc = now - timedelta(days=1)

    # Order created yesterday but completed today → must appear in today's completed_count.
    o1 = _make_delivery_order(
        db_session, operator_user.id, status="completed", completed_at=now
    )
    o1.created_at = yesterday_utc
    db_session.flush()

    # Order created AND completed yesterday → must NOT appear in today's completed_count.
    o2 = _make_delivery_order(
        db_session, operator_user.id, status="completed", completed_at=yesterday_utc
    )
    o2.created_at = yesterday_utc
    db_session.flush()

    # Pending order with photo taken today → must appear in today's photo_only_count.
    o3 = _make_delivery_order(
        db_session, operator_user.id, status="pending", photo_at=now
    )
    o3.created_at = yesterday_utc
    db_session.flush()

    # Pending order with photo taken yesterday → must NOT appear in today's photo_only_count.
    o4 = _make_delivery_order(
        db_session, operator_user.id, status="pending", photo_at=yesterday_utc
    )
    o4.created_at = yesterday_utc
    db_session.flush()

    today = _local_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    summary = resp.json()["orders_summary"]
    assert summary["completed_count"] == 1   # only o1
    assert summary["photo_only_count"] == 1  # only o3


# ---------------------------------------------------------------------------
# Fix 4: invalid type returns 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_invalid_type_returns_400(
    client: AsyncClient,
    owner_token: str,
):
    """An invalid 'type' query param must return HTTP 400, not silently default to 'all'."""
    today = _local_today()
    resp = await client.get(
        f"{_BASE}/export?from={today}&to={today}&type=invalid_value",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "invalid_value" in detail.lower() or "type" in detail.lower()


# ---------------------------------------------------------------------------
# Fix 5: announced_qty column in CSV for delivery_items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_csv_includes_announced_qty_for_delivery_items(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """The CSV must have an 'announced_qty' column.  For delivery_item rows it
    must contain the announced quantity; for other event types it must be empty."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    now = datetime.now(UTC)

    # Delivery item: announced=12, received=10.
    delivery = _make_delivery(db_session, owner_user.id, "validada", validated_at=now)
    delivery.created_at = now
    db_session.flush()
    _make_delivery_item(
        db_session, delivery.id, palta.id, operator_user.id,
        announced_qty="12", received_qty="10", created_at=now
    )

    # Count item (announced_qty must be empty in its row).
    count = _make_count(db_session, operator_user.id, completed_at=now)
    count.started_at = now
    count.created_at = now
    db_session.flush()
    _make_count_item(db_session, count.id, palta.id, operator_user.id, "8", created_at=now)

    today = _local_today()
    resp = await client.get(
        f"{_BASE}/export?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    body = resp.content.decode("utf-8-sig")
    lines = body.splitlines()

    # Header must contain announced_qty column.
    header = lines[0]
    assert "announced_qty" in header

    # Parse header to find column positions.
    cols = header.split(",")
    announced_idx = cols.index("announced_qty")
    event_type_idx = cols.index("event_type")

    delivery_rows = [
        line.split(",") for line in lines[1:]
        if line and line.split(",")[event_type_idx] == "delivery_item"
    ]
    count_rows = [
        line.split(",") for line in lines[1:]
        if line and line.split(",")[event_type_idx] == "inventory_count_item"
    ]

    assert len(delivery_rows) >= 1
    # announced_qty for the delivery row must be "12".
    assert delivery_rows[0][announced_idx] == "12"

    assert len(count_rows) >= 1
    # announced_qty for count rows must be empty.
    assert count_rows[0][announced_idx] == ""


# ---------------------------------------------------------------------------
# Fix 7: orders_summary excludes cancelled (corrected) pending orders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orders_summary_excludes_cancelled(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """A pending order that has been 'cancelled' (corrected by another order) must
    not appear in photo_only_count.  In this model, a corrector row pointing to a
    pending order makes that original a non-leaf — the leaf filter must exclude it."""
    now = datetime.now(UTC)

    # Original pending order.
    original = _make_delivery_order(db_session, operator_user.id, status="pending", photo_at=now)
    original.created_at = now
    db_session.flush()

    # Corrector order (the "cancellation"): a pending order with corrects_id pointing
    # to the original.  Its existence makes the original a non-leaf.
    canceller = DeliveryOrder(
        id=uuid.uuid4(),
        status="pending",
        photo_url="/photos/cancel.jpg",
        photo_at=now,
        photo_by=operator_user.id,
        completed_at=None,
        completed_by=None,
        created_by=operator_user.id,
        created_at=now,
        corrects_id=original.id,
    )
    db_session.add(canceller)
    db_session.flush()

    today = _local_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    summary = resp.json()["orders_summary"]
    # 'original' is a non-leaf (corrected) → excluded.
    # 'canceller' is a leaf with status=pending → counted.
    assert summary["photo_only_count"] == 1


# ---------------------------------------------------------------------------
# Fix 8a: full-day boundary coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timing
async def test_from_equals_to_covers_full_day(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """Events at 00:00:01 and 23:59:59 in the business timezone on the same day
    must both appear when from==to is that day.

    Marked with pytest.mark.timing so it can be excluded from fast runs.
    """
    from datetime import time as dt_time

    tz = _business_tz()
    today_local = datetime.now(tz).date()
    start_of_day = datetime.combine(today_local, dt_time(0, 0, 1), tzinfo=tz)
    end_of_day = datetime.combine(today_local, dt_time(23, 59, 59), tzinfo=tz)

    palta = _make_product(db_session, owner_user.id, "PALTA")

    # Event at 00:00:01 local time.
    d1 = _make_delivery(db_session, owner_user.id, "validada", validated_at=start_of_day)
    d1.created_at = start_of_day
    db_session.flush()
    item1 = _make_delivery_item(
        db_session, d1.id, palta.id, operator_user.id, "5", "5", created_at=start_of_day
    )

    # Event at 23:59:59 local time.
    d2 = _make_delivery(db_session, owner_user.id, "validada", validated_at=end_of_day)
    d2.created_at = end_of_day
    db_session.flush()
    item2 = _make_delivery_item(
        db_session, d2.id, palta.id, operator_user.id, "3", "3", created_at=end_of_day
    )

    date_str = today_local.strftime("%Y-%m-%d")
    resp = await client.get(
        f"{_BASE}/traceability/{palta.id}?from={date_str}&to={date_str}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    event_ids = {e["id"] for e in resp.json()}
    assert str(item1.id) in event_ids, "Event at 00:00:01 must be included"
    assert str(item2.id) in event_ids, "Event at 23:59:59 must be included"


# ---------------------------------------------------------------------------
# Fix 8b: alert=False when consumption is zero (no variance)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_false_when_consumption_zero(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
):
    """When stock_inicio + entries_qty == stock_actual, consumption==0 and
    alert must be False (numbers add up perfectly, no leak detected)."""
    palta = _make_product(db_session, owner_user.id, "PALTA")

    # Count before range: stock_inicio = 10.
    ten_days_ago = datetime.now(UTC) - timedelta(days=10)
    prior_count = _make_count(db_session, operator_user.id, completed_at=ten_days_ago)
    prior_count.started_at = ten_days_ago
    prior_count.created_at = ten_days_ago
    db_session.flush()
    _make_count_item(
        db_session, prior_count.id, palta.id, operator_user.id, "10", created_at=ten_days_ago
    )

    # Delivery in range: entries = 5.
    in_range_ts = _local_midday_today_utc()
    delivery = _make_delivery(db_session, owner_user.id, "validada", validated_at=in_range_ts)
    delivery.created_at = in_range_ts
    db_session.flush()
    _make_delivery_item(
        db_session, delivery.id, palta.id, owner_user.id, "5", "5", created_at=in_range_ts
    )

    # Count in range: stock_actual = 15 (10 + 5 = 15, no variance).
    count_in_range = _make_count(db_session, operator_user.id, completed_at=in_range_ts)
    count_in_range.started_at = in_range_ts
    count_in_range.created_at = in_range_ts
    db_session.flush()
    _make_count_item(
        db_session, count_in_range.id, palta.id, operator_user.id, "15", created_at=in_range_ts
    )

    today = _local_today()
    resp = await client.get(
        f"{_BASE}/summary?from={today}&to={today}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    products = {p["name"]: p for p in resp.json()["products"]}
    palta_row = products["PALTA"]

    assert palta_row["consumption"] == "0"
    assert palta_row["alert"] is False
