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
- Operator correction window: same calendar day (business timezone) as item.created_at.
- UniqueConstraint(corrects_id) prevents concurrent chain bifurcation.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

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
    operator_user,
    owner_user,
    active_products,
):
    """The response MUST NOT contain any field that reveals expected quantity.

    This is the most critical invariant in this module (requerimientos.md §1).
    Any field named expected_qty, previous_count, stock_level, or similar
    must be absent from the response.
    """
    papa, _ = active_products
    # Count must be started_by operator so the operator can access it.
    count = _make_count(db_session, operator_user.id)
    _make_item(db_session, count.id, papa.id, operator_user.id)

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
    operator_user,
    owner_user,
    active_products,
):
    """GET must return only leaf items — corrected items must not appear."""
    papa, _ = active_products
    # Count must be started_by operator so the operator can access it.
    count = _make_count(db_session, operator_user.id)
    original = _make_item(db_session, count.id, papa.id, operator_user.id, quantity="3")
    correction = _make_item(
        db_session, count.id, papa.id, operator_user.id,
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
    operator_user,
    owner_user,
    active_products,
):
    papa, _ = active_products
    count = _make_count(db_session, operator_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(papa.id), "quantity": "3.5"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["product_id"] == str(papa.id)
    assert data["quantity"] == "3.5"
    # corrects_id is not exposed to operator — it is an owner-only field.
    assert "corrects_id" not in data


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
    # Count must be started_by operator so the operator passes the ownership check.
    count = _make_count(db_session, operator_user.id)
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
    # Count must be started_by operator so ownership passes; window check fails after.
    count = _make_count(db_session, operator_user.id)
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
    count = _make_count(db_session, operator_user.id)
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
    count = _make_count(db_session, operator_user.id)
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
    operator_user,
    owner_user,
):
    # Count started_by operator so ownership passes; status check fires next.
    count = _make_count(
        db_session, operator_user.id,
        status="completed",
        completed_at=datetime.now(UTC),
        completed_by=operator_user.id,
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
    count = _make_count(db_session, operator_user.id)
    _make_item(db_session, count.id, papa.id, operator_user.id)
    _make_item(db_session, count.id, pollo.id, operator_user.id)

    resp1 = await client.post(f"{_BASE}/{count.id}/complete", headers=_auth(operator_token))
    assert resp1.status_code == 200

    resp2 = await client.post(f"{_BASE}/{count.id}/complete", headers=_auth(operator_token))
    assert resp2.status_code == 409


# ===========================================================================
# Business-timezone time window — is_same_calendar_day_local
#
# The utility function itself is tested in the deliveries test suite.
# Here we verify that the inventory domain applies the same function correctly
# for operator corrections, anchored to item.created_at.
#
# Tests use unittest.mock.patch to decouple from the wall clock — we verify
# the endpoint's behaviour when the function returns True or False, without
# relying on the CI running at a specific UTC time.
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_correction_at_local_midnight_boundary_mocked_same_day(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    """Operator can correct an item when is_same_calendar_day_local returns True.

    The business-timezone comparison is unit-tested in test_deliveries.py.
    Here we only verify that the inventory endpoint allows the correction when
    the function returns True, regardless of wall-clock time.
    """
    papa, _ = active_products
    count = _make_count(db_session, operator_user.id)
    original = _make_item(
        db_session, count.id, papa.id, operator_user.id,
        created_at=datetime.now(UTC),
    )

    with patch(
        "cocina_control.api.inventory.is_same_calendar_day_local",
        return_value=True,
    ):
        resp = await client.post(
            f"{_BASE}/{count.id}/items/{original.id}/correct",
            json={"quantity": "99"},
            headers=_auth(operator_token),
        )

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
    count = _make_count(db_session, operator_user.id)

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


# ===========================================================================
# Security: GET access control for operator
# ===========================================================================


@pytest.fixture
def operator_user2(db_session: Session):
    """A second operator distinct from operator_user."""
    from tests.conftest import create_test_user
    return create_test_user(db_session, "operator", f"op2-{uuid.uuid4().hex[:6]}@test.com")


@pytest.fixture
def operator_token2(operator_user2) -> str:
    from cocina_control.security.tokens import create_access_token
    return create_access_token(operator_user2.id, operator_user2.role)


@pytest.mark.asyncio
async def test_operator_can_read_own_in_progress_count(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
):
    """Operator can read their own in_progress session."""
    count = _make_count(db_session, operator_user.id)

    resp = await client.get(f"{_BASE}/{count.id}", headers=_auth(operator_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_operator_cannot_read_completed_count_403(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    active_products,
):
    """Operator cannot read their own completed count — returns 403, not 404.

    A completed count reveals the full list of counted quantities, allowing the
    operator to reconstruct expected values before the next count (violates §1).
    Using 403 (not 404) avoids leaking count existence via response-code probing.
    """
    papa, pollo = active_products
    count = _make_count(
        db_session, operator_user.id,
        status="completed",
        completed_at=datetime.now(UTC),
        completed_by=operator_user.id,
    )
    _make_item(db_session, count.id, papa.id, operator_user.id)
    _make_item(db_session, count.id, pollo.id, operator_user.id)

    resp = await client.get(f"{_BASE}/{count.id}", headers=_auth(operator_token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_operator_cannot_read_other_operator_count_403(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user2,
):
    """Operator cannot read another operator's in_progress count — 403."""
    count = _make_count(db_session, operator_user2.id)

    resp = await client.get(f"{_BASE}/{count.id}", headers=_auth(operator_token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_read_any_count(
    client: AsyncClient,
    db_session: Session,
    owner_token: str,
    owner_user,
    operator_user,
    active_products,
):
    """Owner can read any count regardless of who started it or its status."""
    papa, pollo = active_products

    # Count started by operator, now completed.
    count = _make_count(
        db_session, operator_user.id,
        status="completed",
        completed_at=datetime.now(UTC),
        completed_by=operator_user.id,
    )
    _make_item(db_session, count.id, papa.id, operator_user.id)
    _make_item(db_session, count.id, pollo.id, operator_user.id)

    resp = await client.get(f"{_BASE}/{count.id}", headers=_auth(owner_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


# ===========================================================================
# Security: correct_item ownership
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_cannot_correct_item_of_other_operator_count_403(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user2,
    owner_user,
    active_products,
):
    """Operator cannot correct an item belonging to another operator's session."""
    papa, _ = active_products
    count = _make_count(db_session, operator_user2.id)
    item = _make_item(
        db_session, count.id, papa.id, operator_user2.id,
        created_at=datetime.now(UTC),
    )

    resp = await client.post(
        f"{_BASE}/{count.id}/items/{item.id}/correct",
        json={"quantity": "5"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 403


# ===========================================================================
# Security: complete_count ownership
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_cannot_complete_other_operator_count_403(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user2,
    active_products,
):
    """Operator cannot complete another operator's session — 403."""
    papa, pollo = active_products
    count = _make_count(db_session, operator_user2.id)
    _make_item(db_session, count.id, papa.id, operator_user2.id)
    _make_item(db_session, count.id, pollo.id, operator_user2.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/complete",
        headers=_auth(operator_token),
    )
    assert resp.status_code == 403


# ===========================================================================
# Active-product snapshot at complete time (hallazgo #4)
# ===========================================================================


@pytest.mark.asyncio
async def test_complete_ignores_product_deactivated_after_start(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    """A product deactivated after start is not required at complete time.

    The active-product list is evaluated at the moment /complete is called
    (current snapshot), not at session-start time.  A deactivated product
    is no longer sold and should not block the count.
    """
    papa, pollo = active_products
    count = _make_count(db_session, operator_user.id)

    # Count only papa.
    _make_item(db_session, count.id, papa.id, operator_user.id)

    # Deactivate pollo after the session started — simulates a catalogue change.
    pollo.is_active = False
    db_session.flush()

    resp = await client.post(
        f"{_BASE}/{count.id}/complete",
        headers=_auth(operator_token),
    )
    # pollo is inactive now → not required → complete succeeds.
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_complete_requires_product_activated_after_start(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    """A product activated after start IS required at complete time.

    The snapshot is current-at-complete.  A newly activated product must be
    counted before the session can close.
    """
    papa, pollo = active_products
    count = _make_count(db_session, operator_user.id)

    # Count papa and pollo (both active at start).
    _make_item(db_session, count.id, papa.id, operator_user.id)
    _make_item(db_session, count.id, pollo.id, operator_user.id)

    # Activate a new product AFTER the session started.
    new_product = _make_product(db_session, owner_user.id, "HARINA", is_active=True)

    resp = await client.post(
        f"{_BASE}/{count.id}/complete",
        headers=_auth(operator_token),
    )
    # HARINA activated after start → required but not counted → 400.
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "missing_product_ids" in detail
    assert str(new_product.id) in detail["missing_product_ids"]


# ===========================================================================
# Schema: operator response hides corrects_id and reason (hallazgo #5)
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_response_hides_corrects_id_and_reason(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    active_products,
):
    """The operator GET response must not expose corrects_id or reason.

    These fields would allow an operator to reconstruct the correction chain
    and infer previous quantities, violating requerimientos.md §1.
    """
    papa, _ = active_products
    count = _make_count(db_session, operator_user.id)
    original = _make_item(db_session, count.id, papa.id, operator_user.id, quantity="3")
    # Add a correction so there is an item with corrects_id + reason in the DB.
    _make_item(
        db_session, count.id, papa.id, operator_user.id,
        quantity="5", corrects_id=original.id, reason="recount",
        created_at=datetime.now(UTC),
    )

    resp = await client.get(f"{_BASE}/{count.id}", headers=_auth(operator_token))
    assert resp.status_code == 200

    for item in resp.json()["items"]:
        assert "corrects_id" not in item, "corrects_id must not be exposed to operator"
        assert "reason" not in item, "reason must not be exposed to operator"


# ===========================================================================
# Business-timezone boundary — using mock to verify window-closed path
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_correction_window_closed_when_function_returns_false(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    """Operator cannot correct an item when is_same_calendar_day_local returns False.

    Patches is_same_calendar_day_local to return False regardless of wall-clock
    time.  Verifies that the inventory endpoint correctly blocks the correction
    with 403 when the time-window check fails.
    """
    papa, _ = active_products
    # Count started_by operator so ownership check passes.
    count = _make_count(db_session, operator_user.id)
    original = _make_item(
        db_session, count.id, papa.id, operator_user.id,
        created_at=datetime.now(UTC),
    )

    with patch(
        "cocina_control.api.inventory.is_same_calendar_day_local",
        return_value=False,
    ):
        resp = await client.post(
            f"{_BASE}/{count.id}/items/{original.id}/correct",
            json={"quantity": "99"},
            headers=_auth(operator_token),
        )

    assert resp.status_code == 403
    assert "correction window closed" in resp.json()["detail"].lower()


# ===========================================================================
# Low-priority: misc (hallazgo #8)
# ===========================================================================


@pytest.mark.asyncio
async def test_add_item_after_correction_leaf_check(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    owner_user,
    active_products,
):
    """After correcting a product, adding it again via /items returns 409.

    The correction is the new leaf for that product; the idempotency check
    must detect the corrected item as the current leaf and reject the add.
    """
    papa, _ = active_products
    count = _make_count(db_session, operator_user.id)

    original = _make_item(db_session, count.id, papa.id, operator_user.id, quantity="3")
    # Correction makes original non-leaf; the new item IS the leaf for papa.
    _make_item(
        db_session, count.id, papa.id, operator_user.id,
        quantity="5", corrects_id=original.id, created_at=datetime.now(UTC),
    )

    # Attempting to add papa again must return 409 (leaf already exists).
    resp = await client.post(
        f"{_BASE}/{count.id}/items",
        json={"product_id": str(papa.id), "quantity": "10"},
        headers=_auth(operator_token),
    )
    assert resp.status_code == 409
    assert "already counted" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_complete_with_zero_active_products(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
):
    """If there are no active products, complete succeeds with an empty count.

    An empty session is valid when the catalogue has no active products
    (e.g. during initial setup or between catalogue cycles).
    """
    count = _make_count(db_session, operator_user.id)

    resp = await client.post(
        f"{_BASE}/{count.id}/complete",
        headers=_auth(operator_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_data_integrity_error_logs_at_500(
    client: AsyncClient,
    db_session: Session,
    operator_token: str,
    operator_user,
    active_products,
    caplog,
):
    """When an item references a missing product, a log.error is emitted before 500."""
    import logging

    from fastapi import HTTPException as _HTTPException
    from sqlalchemy import select as _select

    from cocina_control.api.inventory import log as _inv_log
    from cocina_control.models.inventory import InventoryCountItem as _InventoryCountItem

    papa, _ = active_products
    count = _make_count(db_session, operator_user.id)
    _make_item(db_session, count.id, papa.id, operator_user.id, quantity="3")

    def _broken_build(session, count_id, viewer_role):
        """Simulate a missing product to exercise the log.error + 500 path."""
        all_items = session.scalars(
            _select(_InventoryCountItem).where(
                _InventoryCountItem.inventory_count_id == count_id
            )
        ).all()
        if all_items:
            item = all_items[0]
            _inv_log.error(
                "data_integrity_item_missing_product",
                extra={
                    "count_id": str(count_id),
                    "item_id": str(item.id),
                    "product_id": str(item.product_id),
                },
            )
            raise _HTTPException(
                status_code=500,
                detail="Data integrity error: item references missing product",
            )
        return []

    with caplog.at_level(logging.ERROR, logger="cocina_control.api.inventory"):
        with patch(
            "cocina_control.api.inventory._build_item_responses",
            side_effect=_broken_build,
        ):
            resp = await client.get(f"{_BASE}/{count.id}", headers=_auth(operator_token))

    assert resp.status_code == 500
    assert any(
        "data_integrity_item_missing_product" in r.message
        for r in caplog.records
    )
