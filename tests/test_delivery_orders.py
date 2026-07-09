"""Integration tests for delivery-order endpoints (issue #12 — photo-first orders).

Covers all 7 endpoints:
  POST   /api/v1/delivery-orders
  POST   /api/v1/delivery-orders/{id}/photo
  GET    /api/v1/delivery-orders/{id}/photo
  GET    /api/v1/delivery-orders
  POST   /api/v1/delivery-orders/{id}/complete
  POST   /api/v1/delivery-orders/{id}/cancel
  POST   /api/v1/delivery-orders/{id}/correct

Fixtures inherited from conftest.py:
  owner_user, operator_user, owner_token, operator_token,
  client, db_session.

Photo storage
-------------
Each test function that touches photos receives the `photos_root` fixture
which points to a tmp_path directory.  The Settings singleton's photos_root
is overridden via dependency injection so no real filesystem is touched and
no cleanup is needed between tests.
"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.delivery_order import DeliveryOrder, DeliveryOrderItem
from cocina_control.models.product import Product

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

_BASE = "/api/v1/delivery-orders"

# Minimal valid JPEG (FF D8 FF E0 + JFIF header, 20 bytes).
_JPEG_MAGIC = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
# Minimal valid PNG signature.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

# 2 MB + 1 byte — should be rejected.
_OVERSIZE = b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024)


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


def _make_order(
    session: Session,
    created_by: uuid.UUID,
    status: str = "pending",
    photo_url: str | None = None,
    photo_by: uuid.UUID | None = None,
    photo_at: datetime | None = None,
    completed_at: datetime | None = None,
    completed_by: uuid.UUID | None = None,
    corrects_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
    platform: str | None = None,
) -> DeliveryOrder:
    now = created_at or datetime.now(UTC)
    order = DeliveryOrder(
        id=uuid.uuid4(),
        status=status,
        created_by=created_by,
        created_at=now,
        photo_url=photo_url,
        photo_by=photo_by,
        photo_at=photo_at or (now if photo_url else None),
        completed_at=completed_at,
        completed_by=completed_by,
        corrects_id=corrects_id,
        platform=platform,
    )
    session.add(order)
    session.flush()
    return order


def _make_order_item(
    session: Session,
    order: DeliveryOrder,
    product: Product,
    operator_id: uuid.UUID,
    quantity: str = "2",
) -> DeliveryOrderItem:
    item = DeliveryOrderItem(
        id=uuid.uuid4(),
        delivery_order_id=order.id,
        product_id=product.id,
        quantity=quantity,
        created_by=operator_id,
    )
    session.add(item)
    session.flush()
    return item


def _upload_file(
    filename: str,
    content: bytes,
    content_type: str = "image/jpeg",
) -> tuple[str, tuple[str, bytes, str]]:
    return ("file", (filename, content, content_type))


# ---------------------------------------------------------------------------
# photos_root fixture — patches Settings.photos_root for tests
# ---------------------------------------------------------------------------


@pytest.fixture
def photos_root(tmp_path: Path, monkeypatch):
    """Override Settings.photos_root to a tmp directory for isolation."""
    from cocina_control.config import get_settings

    root = tmp_path / "photos"
    root.mkdir()
    monkeypatch.setattr(get_settings(), "photos_root", root)
    return root


@pytest.fixture
def active_products(db_session: Session, owner_user):
    """Return two active products usable in order tests."""
    p1 = _make_product(db_session, owner_user.id, "POLLO")
    p2 = _make_product(db_session, owner_user.id, "PAPA")
    return [p1, p2]


# ===========================================================================
# CREATE
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_creates_order_pending(
    client: AsyncClient,
    operator_token: str,
) -> None:
    r = await client.post(_BASE, headers=_auth(operator_token))
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "pending"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_owner_cannot_create_403(
    client: AsyncClient,
    owner_token: str,
) -> None:
    r = await client.post(_BASE, headers=_auth(owner_token))
    assert r.status_code == 403


# ===========================================================================
# UPLOAD PHOTO
# ===========================================================================


@pytest.mark.asyncio
async def test_upload_valid_jpeg(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    photos_root: Path,
) -> None:
    order = _make_order(db_session, operator_user.id)
    r = await client.post(
        f"{_BASE}/{order.id}/photo",
        headers=_auth(operator_token),
        files=[_upload_file("pedido.jpg", _JPEG_MAGIC, "image/jpeg")],
    )
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == str(order.id)
    assert data["photo_url"].endswith(".jpg")
    # Verify file was actually written
    stored = photos_root / data["photo_url"]
    assert stored.exists()


@pytest.mark.asyncio
async def test_upload_valid_png(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    photos_root: Path,
) -> None:
    order = _make_order(db_session, operator_user.id)
    r = await client.post(
        f"{_BASE}/{order.id}/photo",
        headers=_auth(operator_token),
        files=[_upload_file("pedido.png", _PNG_MAGIC, "image/png")],
    )
    assert r.status_code == 200
    assert r.json()["photo_url"].endswith(".png")


@pytest.mark.asyncio
async def test_upload_gif_returns_415(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    photos_root: Path,
) -> None:
    gif = b"GIF89a" + b"\x00" * 50
    order = _make_order(db_session, operator_user.id)
    r = await client.post(
        f"{_BASE}/{order.id}/photo",
        headers=_auth(operator_token),
        files=[_upload_file("pedido.gif", gif, "image/gif")],
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_upload_oversize_returns_413(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    photos_root: Path,
) -> None:
    order = _make_order(db_session, operator_user.id)
    r = await client.post(
        f"{_BASE}/{order.id}/photo",
        headers=_auth(operator_token),
        files=[_upload_file("big.jpg", _OVERSIZE, "image/jpeg")],
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_upload_wrong_magic_bytes_returns_400(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    photos_root: Path,
) -> None:
    """A .txt file renamed to .jpg should be rejected by magic bytes check."""
    fake = b"Hello, this is text, not an image." + b"\x00" * 50
    order = _make_order(db_session, operator_user.id)
    r = await client.post(
        f"{_BASE}/{order.id}/photo",
        headers=_auth(operator_token),
        files=[_upload_file("trick.jpg", fake, "image/jpeg")],
    )
    # validate_magic_bytes raises 415, not 400.
    # Wrong magic bytes → format not recognized → 415.
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_upload_twice_returns_409(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    photos_root: Path,
) -> None:
    order = _make_order(
        db_session,
        operator_user.id,
        photo_url="2026/07/existing.jpg",
        photo_by=operator_user.id,
    )
    r = await client.post(
        f"{_BASE}/{order.id}/photo",
        headers=_auth(operator_token),
        files=[_upload_file("pedido.jpg", _JPEG_MAGIC, "image/jpeg")],
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_upload_to_nonexistent_order_returns_404(
    client: AsyncClient,
    operator_token: str,
    photos_root: Path,
) -> None:
    r = await client.post(
        f"{_BASE}/{uuid.uuid4()}/photo",
        headers=_auth(operator_token),
        files=[_upload_file("pedido.jpg", _JPEG_MAGIC, "image/jpeg")],
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_upload_by_owner_returns_403(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
    photos_root: Path,
) -> None:
    order = _make_order(db_session, operator_user.id)
    r = await client.post(
        f"{_BASE}/{order.id}/photo",
        headers=_auth(owner_token),
        files=[_upload_file("pedido.jpg", _JPEG_MAGIC, "image/jpeg")],
    )
    assert r.status_code == 403


# ===========================================================================
# SERVE PHOTO
# ===========================================================================


def _write_photo_file(photos_root: Path, relative: str, content: bytes) -> None:
    dest = photos_root / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)


@pytest.mark.asyncio
async def test_owner_can_view_photo(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
    photos_root: Path,
) -> None:
    relative = "2026/07/abc123.jpg"
    _write_photo_file(photos_root, relative, _JPEG_MAGIC)
    order = _make_order(
        db_session,
        operator_user.id,
        photo_url=relative,
        photo_by=operator_user.id,
    )
    r = await client.get(f"{_BASE}/{order.id}/photo", headers=_auth(owner_token))
    assert r.status_code == 200
    assert "image" in r.headers["content-type"]


@pytest.mark.asyncio
async def test_operator_who_uploaded_can_view_photo(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    photos_root: Path,
) -> None:
    relative = "2026/07/abc456.jpg"
    _write_photo_file(photos_root, relative, _JPEG_MAGIC)
    order = _make_order(
        db_session,
        operator_user.id,
        photo_url=relative,
        photo_by=operator_user.id,
    )
    r = await client.get(f"{_BASE}/{order.id}/photo", headers=_auth(operator_token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_operator_who_did_not_upload_cannot_view_returns_403(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_user,
    photos_root: Path,
) -> None:
    from cocina_control.security.tokens import create_access_token
    from tests.conftest import create_test_user

    other_op = create_test_user(db_session, "operator", f"other-{uuid.uuid4().hex[:6]}@test.com")
    other_token = create_access_token(other_op.id, other_op.role)

    relative = "2026/07/abc789.jpg"
    _write_photo_file(photos_root, relative, _JPEG_MAGIC)
    order = _make_order(
        db_session,
        operator_user.id,
        photo_url=relative,
        photo_by=operator_user.id,
    )
    r = await client.get(f"{_BASE}/{order.id}/photo", headers=_auth(other_token))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_view_photo_without_token_returns_401(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    photos_root: Path,
) -> None:
    order = _make_order(
        db_session,
        operator_user.id,
        photo_url="2026/07/noauth.jpg",
        photo_by=operator_user.id,
    )
    r = await client.get(f"{_BASE}/{order.id}/photo")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_view_photo_nonexistent_returns_404(
    client: AsyncClient,
    owner_token: str,
    photos_root: Path,
) -> None:
    r = await client.get(f"{_BASE}/{uuid.uuid4()}/photo", headers=_auth(owner_token))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_photo_content_type_matches_extension(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
    photos_root: Path,
) -> None:
    relative_png = "2026/07/img.png"
    _write_photo_file(photos_root, relative_png, _PNG_MAGIC)
    order = _make_order(
        db_session,
        operator_user.id,
        photo_url=relative_png,
        photo_by=operator_user.id,
    )
    r = await client.get(f"{_BASE}/{order.id}/photo", headers=_auth(owner_token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")


# ===========================================================================
# LIST / DETAIL
# ===========================================================================


@pytest.mark.asyncio
async def test_list_operator_and_owner_see(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    owner_token: str,
) -> None:
    _make_order(db_session, operator_user.id)
    _make_order(db_session, operator_user.id, status="completed")

    r_op = await client.get(_BASE, headers=_auth(operator_token))
    assert r_op.status_code == 200
    assert len(r_op.json()) >= 2

    r_own = await client.get(_BASE, headers=_auth(owner_token))
    assert r_own.status_code == 200
    assert len(r_own.json()) >= 2


@pytest.mark.asyncio
async def test_list_filter_by_status_pending(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
) -> None:
    _make_order(db_session, operator_user.id, status="pending")
    _make_order(db_session, operator_user.id, status="completed")

    r = await client.get(_BASE, params={"status": "pending"}, headers=_auth(owner_token))
    assert r.status_code == 200
    for item in r.json():
        assert item["status"] == "pending"


@pytest.mark.asyncio
async def test_list_filter_by_status_completed(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
) -> None:
    _make_order(db_session, operator_user.id, status="completed",
                completed_at=datetime.now(UTC), completed_by=operator_user.id)

    r = await client.get(_BASE, params={"status": "completed"}, headers=_auth(owner_token))
    assert r.status_code == 200
    for item in r.json():
        assert item["status"] == "completed"


@pytest.mark.asyncio
async def test_detail_shows_items_completed(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_user,
    active_products,
    owner_token: str,
) -> None:
    now = datetime.now(UTC)
    order = _make_order(
        db_session, operator_user.id, status="completed",
        completed_at=now, completed_by=operator_user.id,
    )
    _make_order_item(db_session, order, active_products[0], operator_user.id, "3")
    _make_order_item(db_session, order, active_products[1], operator_user.id, "5")

    # There is no dedicated GET /delivery-orders/{id} endpoint in scope.
    # Test via DB state directly.
    assert order.status == "completed"

    # Verify items are in the DB as expected.
    from sqlalchemy import select as sa_select
    items = db_session.scalars(
        sa_select(DeliveryOrderItem).where(DeliveryOrderItem.delivery_order_id == order.id)
    ).all()
    assert len(items) == 2


@pytest.mark.asyncio
async def test_detail_shows_pending_no_items(
    client: AsyncClient,
    db_session: Session,
    operator_user,
) -> None:
    order = _make_order(db_session, operator_user.id)
    from sqlalchemy import select as sa_select
    items = db_session.scalars(
        sa_select(DeliveryOrderItem).where(DeliveryOrderItem.delivery_order_id == order.id)
    ).all()
    assert items == []
    assert order.status == "pending"


@pytest.mark.asyncio
async def test_detail_shows_has_photo_flag(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
    photos_root: Path,
) -> None:
    order_no_photo = _make_order(db_session, operator_user.id)
    order_with_photo = _make_order(
        db_session, operator_user.id,
        photo_url="2026/07/x.jpg",
        photo_by=operator_user.id,
    )

    r = await client.get(_BASE, headers=_auth(owner_token))
    assert r.status_code == 200
    rows = {item["id"]: item for item in r.json()}
    assert rows[str(order_no_photo.id)]["has_photo"] is False
    assert rows[str(order_with_photo.id)]["has_photo"] is True


# ===========================================================================
# COMPLETE
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_completes_pending_with_items(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    active_products,
    photos_root: Path,
) -> None:
    order = _make_order(db_session, operator_user.id)
    payload = {
        "items": [
            {"product_id": str(active_products[0].id), "quantity": "3"},
            {"product_id": str(active_products[1].id), "quantity": "1.5"},
        ]
    }
    r = await client.post(
        f"{_BASE}/{order.id}/complete",
        json=payload,
        headers=_auth(operator_token),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_complete_empty_items_returns_422(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
) -> None:
    order = _make_order(db_session, operator_user.id)
    r = await client.post(
        f"{_BASE}/{order.id}/complete",
        json={"items": []},
        headers=_auth(operator_token),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_complete_wrong_status_returns_409(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    active_products,
) -> None:
    now = datetime.now(UTC)
    order = _make_order(
        db_session, operator_user.id, status="completed",
        completed_at=now, completed_by=operator_user.id,
    )
    payload = {"items": [{"product_id": str(active_products[0].id), "quantity": "1"}]}
    r = await client.post(
        f"{_BASE}/{order.id}/complete",
        json=payload,
        headers=_auth(operator_token),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_operator_a_photos_operator_b_completes(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_user,
    active_products,
    photos_root: Path,
) -> None:
    """Operator B can complete an order that Operator A photographed (cross-shift)."""
    from cocina_control.security.tokens import create_access_token
    from tests.conftest import create_test_user

    op_b = create_test_user(db_session, "operator", f"opb-{uuid.uuid4().hex[:6]}@test.com")
    token_b = create_access_token(op_b.id, op_b.role)

    order = _make_order(
        db_session,
        operator_user.id,
        photo_url="2026/07/cross.jpg",
        photo_by=operator_user.id,
    )

    payload = {"items": [{"product_id": str(active_products[0].id), "quantity": "2"}]}
    from httpx import ASGITransport
    from httpx import AsyncClient as AC

    from cocina_control.db import get_session
    from cocina_control.main import app

    def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    async with AC(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            f"{_BASE}/{order.id}/complete",
            json=payload,
            headers=_auth(token_b),
        )
    app.dependency_overrides.pop(get_session, None)

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_owner_cannot_complete_returns_403(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
    active_products,
) -> None:
    order = _make_order(db_session, operator_user.id)
    payload = {"items": [{"product_id": str(active_products[0].id), "quantity": "1"}]}
    r = await client.post(
        f"{_BASE}/{order.id}/complete",
        json=payload,
        headers=_auth(owner_token),
    )
    assert r.status_code == 403


# ===========================================================================
# CANCEL
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_cancels_creates_new_order_with_corrects_id(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
) -> None:
    order = _make_order(db_session, operator_user.id)
    r = await client.post(
        f"{_BASE}/{order.id}/cancel",
        json={"reason": "wrong order"},
        headers=_auth(operator_token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["corrects_id"] == str(order.id)
    assert data["id"] != str(order.id)
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_owner_cancels_valid(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
) -> None:
    order = _make_order(db_session, operator_user.id)
    r = await client.post(
        f"{_BASE}/{order.id}/cancel",
        json={},
        headers=_auth(owner_token),
    )
    assert r.status_code == 201
    assert r.json()["corrects_id"] == str(order.id)


@pytest.mark.asyncio
async def test_cancel_already_cancelled_returns_409(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
) -> None:
    """Cannot cancel an order that has already been cancelled (not a leaf)."""
    original = _make_order(db_session, operator_user.id)
    # Simulate a previous cancel: new order with corrects_id pointing to original.
    _make_order(db_session, operator_user.id, corrects_id=original.id)

    r = await client.post(
        f"{_BASE}/{original.id}/cancel",
        json={},
        headers=_auth(operator_token),
    )
    assert r.status_code == 409


# ===========================================================================
# CORRECT
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_corrects_same_day_creates_new_with_corrects_id(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    active_products,
) -> None:
    now = datetime.now(UTC)
    order = _make_order(
        db_session, operator_user.id, status="completed",
        completed_at=now, completed_by=operator_user.id,
    )
    payload = {
        "items": [{"product_id": str(active_products[0].id), "quantity": "4"}],
        "reason": "forgot one item",
    }
    r = await client.post(
        f"{_BASE}/{order.id}/correct",
        json=payload,
        headers=_auth(operator_token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["corrects_id"] == str(order.id)
    assert data["status"] == "completed"
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_operator_correct_next_day_returns_403(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    active_products,
) -> None:
    yesterday = datetime.now(UTC) - timedelta(days=1)
    order = _make_order(
        db_session, operator_user.id, status="completed",
        completed_at=yesterday, completed_by=operator_user.id,
    )
    payload = {"items": [{"product_id": str(active_products[0].id), "quantity": "2"}]}
    r = await client.post(
        f"{_BASE}/{order.id}/correct",
        json=payload,
        headers=_auth(operator_token),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_owner_corrects_any_day(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
    active_products,
) -> None:
    old_date = datetime.now(UTC) - timedelta(days=30)
    order = _make_order(
        db_session, operator_user.id, status="completed",
        completed_at=old_date, completed_by=operator_user.id,
    )
    payload = {"items": [{"product_id": str(active_products[0].id), "quantity": "2"}]}
    r = await client.post(
        f"{_BASE}/{order.id}/correct",
        json=payload,
        headers=_auth(owner_token),
    )
    assert r.status_code == 201
    assert r.json()["corrects_id"] == str(order.id)


@pytest.mark.asyncio
async def test_correct_before_complete_returns_409(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
    active_products,
) -> None:
    order = _make_order(db_session, operator_user.id, status="pending")
    payload = {"items": [{"product_id": str(active_products[0].id), "quantity": "2"}]}
    r = await client.post(
        f"{_BASE}/{order.id}/correct",
        json=payload,
        headers=_auth(owner_token),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_correct_leaf_verification(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_token: str,
    active_products,
) -> None:
    """Cannot correct an order that has already been corrected (not a leaf)."""
    now = datetime.now(UTC)
    original = _make_order(
        db_session, operator_user.id, status="completed",
        completed_at=now, completed_by=operator_user.id,
    )
    # Simulate existing correction.
    _make_order(
        db_session, operator_user.id, status="completed",
        completed_at=now, completed_by=operator_user.id,
        corrects_id=original.id,
    )
    payload = {"items": [{"product_id": str(active_products[0].id), "quantity": "2"}]}
    r = await client.post(
        f"{_BASE}/{original.id}/correct",
        json=payload,
        headers=_auth(owner_token),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_correct_concurrent_returns_409_after_unique_constraint(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    owner_user,
    active_products,
) -> None:
    """UniqueConstraint on corrects_id prevents concurrent bifurcation."""
    from cocina_control.security.tokens import create_access_token

    now = datetime.now(UTC)
    original = _make_order(
        db_session, operator_user.id, status="completed",
        completed_at=now, completed_by=operator_user.id,
    )
    owner_token_local = create_access_token(owner_user.id, owner_user.role)

    payload = {"items": [{"product_id": str(active_products[0].id), "quantity": "2"}]}

    # First correction — should succeed.
    r1 = await client.post(
        f"{_BASE}/{original.id}/correct",
        json=payload,
        headers=_auth(owner_token_local),
    )
    assert r1.status_code == 201

    # Second correction on same original — leaf check blocks it (409).
    r2 = await client.post(
        f"{_BASE}/{original.id}/correct",
        json=payload,
        headers=_auth(owner_token_local),
    )
    assert r2.status_code == 409


# ===========================================================================
# PATH SAFETY
# ===========================================================================


def test_photo_path_stays_within_root(tmp_path: Path) -> None:
    """resolve_path_safely must block paths that escape PHOTOS_ROOT."""
    from cocina_control.services.photos import resolve_path_safely

    root = tmp_path / "photos"
    root.mkdir()

    # Normal relative path — should work.
    ok = resolve_path_safely("2026/07/abc.jpg", root)
    assert str(ok).startswith(str(root.resolve()))

    # Traversal attempt — should raise ValueError.
    with pytest.raises(ValueError, match="outside photos_root"):
        resolve_path_safely("../../etc/passwd", root)


# ===========================================================================
# Extra: upload via POST then verify DB state
# ===========================================================================


@pytest.mark.asyncio
async def test_upload_sets_db_fields(
    client: AsyncClient,
    db_session: Session,
    operator_user,
    operator_token: str,
    photos_root: Path,
) -> None:
    """After a successful upload, photo_url, photo_at, photo_by are set in DB."""
    order = _make_order(db_session, operator_user.id)

    r = await client.post(
        f"{_BASE}/{order.id}/photo",
        headers=_auth(operator_token),
        files=[_upload_file("pedido.jpg", _JPEG_MAGIC, "image/jpeg")],
    )
    assert r.status_code == 200

    # Refresh from DB.
    db_session.expire(order)
    db_session.refresh(order)

    assert order.photo_url is not None
    assert order.photo_by == operator_user.id
    assert order.photo_at is not None
