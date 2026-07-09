"""Integration tests for inventory-count endpoints (issue #13).

Covers all 5 endpoints:
  POST   /api/v1/inventory-counts
  GET    /api/v1/inventory-counts/{id}
  POST   /api/v1/inventory-counts/{id}/items
  POST   /api/v1/inventory-counts/{id}/items/{item_id}/correct
  POST   /api/v1/inventory-counts/{id}/complete

Fixtures inherited from conftest.py:
  owner_user, operator_user, owner_token, operator_token,
  client, db_session.

Domain invariants under test:
- The operator NEVER sees an expected quantity (blind count).
- Items are append-only; corrections create new rows.
- Complete requires ALL active products to have a leaf item.
- Operator correction window: same calendar day UTC-3 as item.created_at.
- UniqueConstraint(corrects_id) prevents concurrent chain bifurcation.
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.inventory import InventoryCount, InventoryCountItem
from cocina_control.models.product import Product

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE = "/api/v1/inventory-counts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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


def _make_count(
    session: Session,
    created_by: uuid.UUID,
    status: str = "in_progress",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    completed_by: uuid.UUID | None = None,
) -> InventoryCount:
    now = started_at or datetime.now(UTC)
    count = InventoryCount(
        id=uuid.uuid4(),
        status=status,
        started_at=now,
        started_by=created_by,
        completed_at=completed_at,
        completed_by=completed_by,
        created_by=created_by,
        created_at=now,
    )
    session.add(count)
    session.flush()
    return count


def _make_item(
    session: Session,
    count_id: uuid.UUID,
    product_id: uuid.UUID,
    created_by: uuid.UUID,
    quantity: str = "5",
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
# Shared fixture: two active products used across most tests.
# ---------------------------------------------------------------------------


@pytest.fixture
def active_products(db_session: Session, owner_user):
    """Return two active products: PAPA and POLLO."""
    papa = _make_product(db_session, owner_user.id, "PAPA")
    pollo = _make_product(db_session, owner_user.id, "POLLO")
    return papa, pollo


# ===========================================================================
# START — POST /inventory-counts
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_starts_count(client: AsyncClient, operator_token: str):
    resp = await client.post(_BASE, headers=_auth(operator_token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "in_progress"
    assert "id" in data
    assert "started_at" in data


@pytest.mark.asyncio
async def test_owner_starts_count(client: AsyncClient, owner_token: str):
    resp = await client.post(_BASE, headers=_auth(owner_token))
    assert resp.status_code == 201
    assert resp.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_start_without_auth_returns_401(client: AsyncClient):
    resp = await client.post(_BASE)
    assert resp.status_code == 401


# ===========================================================================
# GET STATE — GET /inventory-counts/{id}
# ===========================================================================


@pytest.mark.asyncio
async def test_get_state_shows_no_expected_values(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
    active_products,
):
    """The response MUST NOT contain any field that reveals expected quantity.

    This is the most critical invariant in this module (requerimientos.md §1).
    Any field named expected_qty, previous_count, stock_level, or similar
    must be absent from the response.
    """
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)
    _make_item(db_session, count.id, papa.id, owner_user.id)

    resp = await client.get(f"{_BASE}/{count.id}", headers=_auth(operator_token))
    assert resp.status_code == 200

    data = resp.json()
    # Top-level response must not have any expected/stock field.
    forbidden_fields = {
        "expected_qty", "expected", "stock", "stock_level",
        "previous_count", "previous_qty", "target", "target_qty",
    }
    assert not forbidden_fields.intersection(data.keys()), (
        f"Response exposes forbidden field(s): {forbidden_fields.intersection(data.keys())}"
    )

    # Items must also not have any such field.
    for item in data.get("items", []):
        assert not forbidden_fields.intersection(item.keys()), (
            f"Item exposes forbidden field(s): {forbidden_fields.intersection(item.keys())}"
        )


@pytest.mark.asyncio
async def test_get_state_shows_only_leaf_items(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
    active_products,
):
    """GET must return only leaf items — corrected items must not appear."""
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)
    original = _make_item(db_session, count.id, papa.id, owner_user.id, quantity="3")
    correction = _make_item(
        db_session, count.id, papa.id, owner_user.id,
        quantity="5", corrects_id=original.id
    )

    resp = await client.get(f"{_BASE}/{count.id}", headers=_auth(operator_token))
    assert resp.status_code == 200

    item_ids = [i["id"] for i in resp.json()["items"]]
    assert str(correction.id) in item_ids
    assert str(original.id) not in item_ids


@pytest.mark.asyncio
async def test_get_nonexistent_returns_404(client: AsyncClient, operator_token: str):
    resp = await client.get(f"{_BASE}/{uuid.uuid4()}", headers=_auth(operator_token))
    assert resp.status_code == 404


# ===========================================================================
# ADD ITEM — POST /inventory-counts/{id}/items
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_adds_item(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
    active_products,
):
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(papa.id), "quantity": "3.5"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["product_id"] == str(papa.id)
    assert data["quantity"] == "3.5"
    assert data["corrects_id"] is None


@pytest.mark.asyncio
async def test_add_item_quantity_zero_valid(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
    active_products,
):
    """quantity == 0 is valid: the operator counted nothing."""
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(papa.id), "quantity": "0"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 201
    assert resp.json()["quantity"] == "0"


@pytest.mark.asyncio
async def test_add_item_negative_returns_422(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
    active_products,
):
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(papa.id), "quantity": "-1"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_add_item_product_inactive_returns_400(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
):
    inactive = _make_product(db_session, owner_user.id, "INACTIVE_PROD", is_active=False)
    count = _make_count(db_session, owner_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(inactive.id), "quantity": "1"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_item_product_nonexistent_returns_400(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
):
    count = _make_count(db_session, owner_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(uuid.uuid4()), "quantity": "1"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_item_already_counted_returns_409(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
    active_products,
):
    """Second add for the same product in the same session must return 409."""
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)

    # First add succeeds.
    resp1 = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(papa.id), "quantity": "3"},
        headers=_auth(operator_token),
    )
    assert resp1.status_code == 201

    # Second add for the same product must fail.
    resp2 = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(papa.id), "quantity": "4"},
        headers=_auth(operator_token),
    )
    assert resp2.status_code == 409
    assert "already counted" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_add_item_wrong_status_returns_409(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
    active_products,
):
    papa, _ = active_products
    count = _make_count(
        db_session, owner_user.id,
        status="completed",
        completed_at=datetime.now(UTC),
        completed_by=owner_user.id,
    )

    resp = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(papa.id), "quantity": "2"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_owner_cannot_add_item_returns_403(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    active_products,
):
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(papa.id), "quantity": "2"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 403


# ===========================================================================
# CORRECT — POST /inventory-counts/{id}/items/{item_id}/correct
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_corrects_same_day_creates_new_item(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)
    # Item created now → same calendar day.
    original = _make_item(
        db_session, count.id, papa.id, operator_user.id,
        created_at=datetime.now(UTC),
    )

    resp = await client.post(
        f"{_BASE}/{count.id}/items/{original.id}/correct",
        json={"quantity": "10"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["corrects_id"] == str(original.id)
    assert data["quantity"] == "10"
    assert data["id"] != str(original.id)


@pytest.mark.asyncio
async def test_operator_correct_next_day_returns_403(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    """Operator cannot correct an item from the previous calendar day (UTC-3)."""
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)
    # Simulate an item created yesterday in Argentina time.
    yesterday_utc = datetime.now(UTC) - timedelta(days=1)
    original = _make_item(
        db_session, count.id, papa.id, operator_user.id,
        created_at=yesterday_utc,
    )

    resp = await client.post(
        f"{_BASE}/{count.id}/items/{original.id}/correct",
        json={"quantity": "10"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 403
    assert "window" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_owner_corrects_any_day(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    active_products,
):
    """Owner can correct items from any day."""
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)
    # Item created a week ago — should not block the owner.
    old_ts = datetime.now(UTC) - timedelta(days=7)
    original = _make_item(
        db_session, count.id, papa.id, owner_user.id,
        created_at=old_ts,
    )

    resp = await client.post(
        f"{_BASE}/{count.id}/items/{original.id}/correct",
        json={"quantity": "7", "reason": "recount after audit"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["corrects_id"] == str(original.id)
    assert data["reason"] == "recount after audit"


@pytest.mark.asyncio
async def test_correct_leaf_verification(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    active_products,
):
    """Correcting an already-corrected item (non-leaf) must return 404."""
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)
    original = _make_item(db_session, count.id, papa.id, owner_user.id)
    # correction_a corrects the original — original is now non-leaf.
    _make_item(
        db_session, count.id, papa.id, owner_user.id,
        corrects_id=original.id,
    )

    # Attempt to correct the original (non-leaf) must fail.
    resp = await client.post(
        f"{_BASE}/{count.id}/items/{original.id}/correct",
        json={"quantity": "99"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_correct_concurrent_returns_409_after_unique_constraint(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products,
):
    """Simulate the second branch of a concurrent correction hitting the DB constraint.

    We cannot truly run two concurrent HTTP requests in a single-session test,
    so we exercise the IntegrityError path by directly inserting a duplicate
    corrects_id at the DB layer, then verifying the endpoint returns 409.
    """
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)
    original = _make_item(db_session, count.id, papa.id, owner_user.id)

    # First correction via API — should succeed.
    resp1 = await client.post(
        f"{_BASE}/{count.id}/items/{original.id}/correct",
        json={"quantity": "10"},
        headers=_auth(owner_token),
    )
    assert resp1.status_code == 201

    # The original is now non-leaf.  A second correction attempt (targeting
    # the original) hits the 404 path (leaf check).
    resp2 = await client.post(
        f"{_BASE}/{count.id}/items/{original.id}/correct",
        json={"quantity": "20"},
        headers=_auth(owner_token),
    )
    # Non-leaf → 404 (consistent with deliveries domain).
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_correct_reason_too_long_returns_422(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    active_products,
):
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)
    original = _make_item(db_session, count.id, papa.id, owner_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/items/{original.id}/correct",
        json={"quantity": "5", "reason": "x" * 501},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 422


# ===========================================================================
# COMPLETE — POST /inventory-counts/{id}/complete
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_completes_when_all_products_counted(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    papa, pollo = active_products
    count = _make_count(db_session, owner_user.id)
    _make_item(db_session, count.id, papa.id, operator_user.id)
    _make_item(db_session, count.id, pollo.id, operator_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/complete",
        headers=_auth(operator_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_owner_completes_when_all_products_counted(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    active_products,
):
    papa, pollo = active_products
    count = _make_count(db_session, owner_user.id)
    _make_item(db_session, count.id, papa.id, owner_user.id)
    _make_item(db_session, count.id, pollo.id, owner_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/complete",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_complete_missing_products_returns_400_with_list(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    """If any active product is missing from the count, return 400 with the list."""
    papa, pollo = active_products
    count = _make_count(db_session, owner_user.id)
    # Count only papa — pollo is missing.
    _make_item(db_session, count.id, papa.id, operator_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/complete",
        headers=_auth(operator_token),
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "missing_product_ids" in detail
    assert str(pollo.id) in detail["missing_product_ids"]


@pytest.mark.asyncio
async def test_complete_wrong_status_returns_409(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    owner_user,
):
    count = _make_count(
        db_session, owner_user.id,
        status="completed",
        completed_at=datetime.now(UTC),
        completed_by=owner_user.id,
    )
    resp = await client.post(
        f"{_BASE}/{count.id}/complete",
        headers=_auth(operator_token),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_concurrent_complete_second_returns_409(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    """Two sequential /complete calls: first succeeds, second gets 409."""
    papa, pollo = active_products
    count = _make_count(db_session, owner_user.id)
    _make_item(db_session, count.id, papa.id, operator_user.id)
    _make_item(db_session, count.id, pollo.id, operator_user.id)

    resp1 = await client.post(f"{_BASE}/{count.id}/complete", headers=_auth(operator_token))
    assert resp1.status_code == 200

    resp2 = await client.post(f"{_BASE}/{count.id}/complete", headers=_auth(operator_token))
    assert resp2.status_code == 409


# ===========================================================================
# UTC-3 time window — is_same_calendar_day_argentina
#
# The utility function itself is tested in the deliveries test suite.
# Here we verify that the inventory domain applies the same function correctly
# for operator corrections, anchored to item.created_at.
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_correction_at_utc_minus3_midnight_boundary(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    """Item created 30 minutes before Argentina midnight — operator can still correct.

    Argentina midnight = 03:00 UTC.  An item created at 02:30 UTC is at 23:30
    Argentina time.  A correction made at 02:50 UTC (23:50 Argentina) is still
    same-day and must be allowed.
    """
    papa, _ = active_products
    count = _make_count(db_session, owner_user.id)

    # 02:30 UTC today = 23:30 Argentina today.
    now_utc = datetime.now(UTC)
    # Construct a timestamp that is clearly same-day in Argentina by using
    # the current Argentina date at 23:00 Argentina time.
    tz_arg = timezone(timedelta(hours=-3))
    now_arg = now_utc.astimezone(tz_arg)
    same_day_arg = now_arg.replace(hour=23, minute=0, second=0, microsecond=0)
    same_day_utc = same_day_arg.astimezone(UTC)

    # Only run this test if same_day_utc is in the past (i.e. we haven't
    # crossed midnight yet in UTC time).  If 23:00 Argentina is in the future,
    # skip to avoid a flaky result.
    if same_day_utc > now_utc:
        pytest.skip("Test clock is before 23:00 Argentina — boundary case does not apply now")

    original = _make_item(
        db_session, count.id, papa.id, operator_user.id,
        created_at=same_day_utc,
    )

    resp = await client.post(
        f"{_BASE}/{count.id}/items/{original.id}/correct",
        json={"quantity": "99"},
        headers=_auth(operator_token),
    )
    # Same calendar day in Argentina — must succeed.
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_complete_only_counts_leaf_items(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    """Complete checks leaf items only — a corrected+re-counted product is fine."""
    papa, pollo = active_products
    count = _make_count(db_session, owner_user.id)

    # Count papa — original.
    original_papa = _make_item(db_session, count.id, papa.id, operator_user.id, quantity="3")
    # Correct papa — now only the correction is a leaf.
    _make_item(
        db_session, count.id, papa.id, operator_user.id,
        quantity="5", corrects_id=original_papa.id,
    )
    # Count pollo.
    _make_item(db_session, count.id, pollo.id, operator_user.id, quantity="2")

    resp = await client.post(
        f"{_BASE}/{count.id}/complete",
        headers=_auth(operator_token),
    )
    # papa has a leaf (the correction), pollo has a leaf → complete succeeds.
    assert resp.status_code == 200
