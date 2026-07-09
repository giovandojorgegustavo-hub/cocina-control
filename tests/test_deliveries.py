"""Integration tests for delivery endpoints (issue #10 pre-load + issue #11 verification).

Covers POST / GET (list) / GET (detail) / PATCH on /api/v1/deliveries (issue #10)
and open / confirm / validate / correct (issue #11).

Fixtures inherited from conftest.py:
  owner_user, operator_user, owner_token, operator_token,
  client, db_session.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from httpx import AsyncClient
from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.product import Product

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
    product = Product(
        id=uuid.uuid4(),
        name=name.upper(),
        unit=unit,
        is_active=is_active,
        created_by=owner_id,
    )
    session.add(product)
    session.flush()
    return product


def _make_delivery(
    session: Session,
    owner_id: uuid.UUID,
    status: Literal["no_leida", "en_verificacion", "validada"] = "no_leida",
    supplier_name: str = "Proveedor Test",
    created_at: datetime | None = None,
) -> Delivery:
    delivery = Delivery(
        id=uuid.uuid4(),
        supplier_name=supplier_name,
        status=status,
        created_by=owner_id,
        created_at=created_at or datetime.now(UTC),
    )
    session.add(delivery)
    session.flush()
    return delivery


def _make_delivery_item(
    session: Session,
    delivery: Delivery,
    product: Product,
    owner_id: uuid.UUID,
    announced_qty: str = "10",
    received_qty: str | None = None,
    corrects_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
    reason: str | None = None,
) -> DeliveryItem:
    item = DeliveryItem(
        id=uuid.uuid4(),
        delivery_id=delivery.id,
        product_id=product.id,
        announced_qty=announced_qty,
        received_qty=received_qty,
        corrects_id=corrects_id,
        created_by=owner_id,
        reason=reason,
    )
    if created_at is not None:
        item.created_at = created_at
    session.add(item)
    session.flush()
    return item


# ---------------------------------------------------------------------------
# Fixture: 3 active products ready to reference in deliveries.
# ---------------------------------------------------------------------------


@pytest.fixture
def active_products(db_session: Session, owner_user):
    """Create and return 3 active products."""
    p1 = _make_product(db_session, owner_user.id, "POLLO")
    p2 = _make_product(db_session, owner_user.id, "PAPA")
    p3 = _make_product(db_session, owner_user.id, "PALTA")
    return [p1, p2, p3]


# ---------------------------------------------------------------------------
# POST /api/v1/deliveries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_creates_delivery_with_items(
    client: AsyncClient,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """Happy path: owner creates a delivery with 2 items."""
    p1, p2, _ = active_products
    response = await client.post(
        "/api/v1/deliveries",
        json={
            "supplier_name": "Proveedor A",
            "items": [
                {"product_id": str(p1.id), "announced_qty": "10.5"},
                {"product_id": str(p2.id), "announced_qty": "5"},
            ],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["supplier_name"] == "Proveedor A"
    assert data["status"] == "no_leida"
    assert len(data["items"]) == 2
    assert "id" in data
    assert "created_at" in data
    # items include product_name
    names = {i["product_name"] for i in data["items"]}
    assert "POLLO" in names
    assert "PAPA" in names


@pytest.mark.asyncio
async def test_created_delivery_status_is_no_leida(
    client: AsyncClient,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """A newly created delivery always starts as no_leida."""
    p1, *_ = active_products
    response = await client.post(
        "/api/v1/deliveries",
        json={
            "supplier_name": "Proveedor B",
            "items": [{"product_id": str(p1.id), "announced_qty": "3"}],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "no_leida"


@pytest.mark.asyncio
async def test_operator_cannot_create_delivery_403(
    client: AsyncClient,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Operator cannot pre-load a delivery — must receive 403."""
    p1, *_ = active_products
    response = await client.post(
        "/api/v1/deliveries",
        json={
            "supplier_name": "X",
            "items": [{"product_id": str(p1.id), "announced_qty": "1"}],
        },
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_without_auth_returns_401(client: AsyncClient) -> None:
    """POST /deliveries without a token must return 401."""
    response = await client.post(
        "/api/v1/deliveries",
        json={"supplier_name": "X", "items": []},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_with_empty_items_returns_422(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """items = [] must be rejected by Pydantic (min_length=1) → 422."""
    response = await client.post(
        "/api/v1/deliveries",
        json={"supplier_name": "Proveedor C", "items": []},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_with_nonexistent_product_returns_400(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """A product_id that does not exist in the DB must return 400."""
    response = await client.post(
        "/api/v1/deliveries",
        json={
            "supplier_name": "Proveedor D",
            "items": [{"product_id": str(uuid.uuid4()), "announced_qty": "5"}],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 400
    body = response.json()
    assert "invalid_ids" in body["detail"]


@pytest.mark.asyncio
async def test_create_with_inactive_product_returns_400(
    client: AsyncClient,
    owner_token: str,
    db_session: Session,
    owner_user,
) -> None:
    """A product_id referencing an inactive product must return 400."""
    inactive = _make_product(db_session, owner_user.id, "CEBOLLA", is_active=False)

    response = await client.post(
        "/api/v1/deliveries",
        json={
            "supplier_name": "Proveedor E",
            "items": [{"product_id": str(inactive.id), "announced_qty": "2"}],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 400
    body = response.json()
    assert str(inactive.id) in body["detail"]["invalid_ids"]


@pytest.mark.asyncio
async def test_create_with_duplicate_product_returns_400(
    client: AsyncClient,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """Two items referencing the same product_id must return 422 (schema) or 400."""
    p1, *_ = active_products
    response = await client.post(
        "/api/v1/deliveries",
        json={
            "supplier_name": "Proveedor F",
            "items": [
                {"product_id": str(p1.id), "announced_qty": "5"},
                {"product_id": str(p1.id), "announced_qty": "3"},
            ],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    # Schema validator fires first → 422; if somehow bypassed → 400.
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_create_with_zero_qty_returns_422(
    client: AsyncClient,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """announced_qty = 0 must be rejected by Pydantic (gt=0) → 422."""
    p1, *_ = active_products
    response = await client.post(
        "/api/v1/deliveries",
        json={
            "supplier_name": "Proveedor G",
            "items": [{"product_id": str(p1.id), "announced_qty": "0"}],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_with_negative_qty_returns_422(
    client: AsyncClient,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """announced_qty < 0 must be rejected by Pydantic (gt=0) → 422."""
    p1, *_ = active_products
    response = await client.post(
        "/api/v1/deliveries",
        json={
            "supplier_name": "Proveedor H",
            "items": [{"product_id": str(p1.id), "announced_qty": "-1"}],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/deliveries (list)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_deliveries_operator_and_owner_both_see(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    operator_token: str,
) -> None:
    """Both owner and operator can list deliveries."""
    _make_delivery(db_session, owner_user.id, supplier_name="Proveedor Lista")

    for token in (owner_token, operator_token):
        response = await client.get(
            "/api/v1/deliveries",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        names = [d["supplier_name"] for d in response.json()]
        assert "Proveedor Lista" in names


@pytest.mark.asyncio
async def test_list_deliveries_ordered_desc_by_created_at(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """Deliveries are returned newest-first (created_at DESC)."""
    now = datetime.now(UTC)
    _make_delivery(
        db_session, owner_user.id, supplier_name="Antigua", created_at=now - timedelta(hours=2)
    )
    _make_delivery(db_session, owner_user.id, supplier_name="Nueva", created_at=now)

    response = await client.get(
        "/api/v1/deliveries",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    supplier_names = [d["supplier_name"] for d in data]
    assert supplier_names.index("Nueva") < supplier_names.index("Antigua")


@pytest.mark.asyncio
async def test_list_deliveries_filter_by_status(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """?status=no_leida returns only no_leida deliveries."""
    _make_delivery(db_session, owner_user.id, status="no_leida", supplier_name="Sin leer")
    _make_delivery(
        db_session, owner_user.id, status="en_verificacion", supplier_name="En verificacion"
    )

    response = await client.get(
        "/api/v1/deliveries?status=no_leida",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    statuses = {d["status"] for d in response.json()}
    assert statuses == {"no_leida"}


@pytest.mark.asyncio
async def test_list_deliveries_item_count(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """item_count reflects the number of current (leaf) items in the delivery."""
    p1, p2, _ = active_products
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Proveedor ItemCount")
    _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")
    _make_delivery_item(db_session, delivery, p2, owner_user.id, "5")

    response = await client.get(
        "/api/v1/deliveries",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    matching = [d for d in response.json() if d["supplier_name"] == "Proveedor ItemCount"]
    assert len(matching) == 1
    assert matching[0]["item_count"] == 2


@pytest.mark.asyncio
async def test_list_no_auth_401(client: AsyncClient) -> None:
    """GET /deliveries without token must return 401."""
    response = await client.get("/api/v1/deliveries")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/deliveries/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_delivery_detail_includes_items_with_product_name(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """GET /{id} returns full detail with product_name resolved per item."""
    p1, p2, _ = active_products
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Proveedor Detail")
    _make_delivery_item(db_session, delivery, p1, owner_user.id, "8")
    _make_delivery_item(db_session, delivery, p2, owner_user.id, "3")

    response = await client.get(
        f"/api/v1/deliveries/{delivery.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["supplier_name"] == "Proveedor Detail"
    assert len(data["items"]) == 2
    names = {i["product_name"] for i in data["items"]}
    assert "POLLO" in names
    assert "PAPA" in names


@pytest.mark.asyncio
async def test_get_delivery_received_qty_is_null_before_verification(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """received_qty is always null until an operator confirms (issue #11)."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Proveedor RecvNull")
    _make_delivery_item(db_session, delivery, p1, owner_user.id, "12")

    response = await client.get(
        f"/api/v1/deliveries/{delivery.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert item["received_qty"] is None


@pytest.mark.asyncio
async def test_get_nonexistent_delivery_404(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """GET with a non-existent UUID must return 404."""
    response = await client.get(
        f"/api/v1/deliveries/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_no_auth_401(client: AsyncClient) -> None:
    """GET /{id} without token must return 401."""
    response = await client.get(f"/api/v1/deliveries/{uuid.uuid4()}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/deliveries/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_can_edit_no_leida_delivery(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """Owner can update supplier_name and items while status == no_leida."""
    p1, p2, p3 = active_products
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Nombre Original")
    _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")

    response = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={
            "supplier_name": "Nombre Actualizado",
            "items": [
                {"product_id": str(p2.id), "announced_qty": "7"},
                {"product_id": str(p3.id), "announced_qty": "4"},
            ],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["supplier_name"] == "Nombre Actualizado"
    assert len(data["items"]) == 2
    names = {i["product_name"] for i in data["items"]}
    assert "PAPA" in names
    assert "PALTA" in names
    # Old item (POLLO) must be gone
    assert "POLLO" not in names


@pytest.mark.asyncio
async def test_owner_cannot_edit_en_verificacion_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """Editing a delivery in en_verificacion must return 409.

    The delivery is inserted directly in the DB because the /open endpoint
    (issue #11) does not exist yet in this PR.
    """
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    _make_delivery_item(db_session, delivery, p1, owner_user.id)

    response = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={"supplier_name": "Intento Fallido"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 409
    assert "cannot be edited" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_owner_cannot_edit_validada_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """Editing a validated delivery must return 409.

    The delivery is inserted directly in the DB because validate (issue #11)
    does not exist yet in this PR.
    """
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="validada")
    _make_delivery_item(db_session, delivery, p1, owner_user.id)

    response = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={"supplier_name": "Intento Fallido Validada"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_operator_cannot_edit_403(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
) -> None:
    """Operator cannot PATCH a delivery — must receive 403."""
    delivery = _make_delivery(db_session, owner_user.id)

    response = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={"supplier_name": "Operario Intruso"},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_replaces_items_completely_no_corrects_id_trail(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """After PATCH, only new items exist — old ones are physically removed.

    This verifies the draft-replacement strategy: no corrects_id trail is
    created while the delivery is no_leida.
    """
    from sqlalchemy import select as sa_select

    p1, p2, p3 = active_products
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Proveedor Replace")
    old_item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")

    response = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={
            "items": [
                {"product_id": str(p2.id), "announced_qty": "6"},
                {"product_id": str(p3.id), "announced_qty": "9"},
            ],
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200

    # Reload state from DB.
    db_session.expire_all()
    all_items = db_session.scalars(
        sa_select(DeliveryItem).where(DeliveryItem.delivery_id == delivery.id)
    ).all()

    # Old item must be gone.
    old_ids = {i.id for i in all_items}
    assert old_item.id not in old_ids

    # No corrects_id trail on the new items.
    assert all(i.corrects_id is None for i in all_items)

    # Exactly 2 items, one per new product.
    product_ids = {i.product_id for i in all_items}
    assert product_ids == {p2.id, p3.id}


@pytest.mark.asyncio
async def test_patch_with_empty_items_returns_422(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """PATCH with items=[] must be rejected by the schema validator (422)."""
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Proveedor EmptyItems")

    response = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={"items": []},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_supplier_name_empty_string_returns_422(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """PATCH with supplier_name='' must be rejected (min_length=1) → 422."""
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Proveedor EmptyName")

    response = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={"supplier_name": ""},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_records_updated_by(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """After a PATCH, updated_by in the DB must equal the owner's id."""
    from sqlalchemy import select as sa_select

    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Proveedor UpdatedBy")

    response = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={"supplier_name": "Nombre Modificado"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200

    db_session.expire_all()
    fresh = db_session.scalars(
        sa_select(Delivery).where(Delivery.id == delivery.id)
    ).one()
    assert fresh.updated_by == owner_user.id


@pytest.mark.asyncio
async def test_patch_records_updated_at(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """After a PATCH, updated_at in the DB must be a recent UTC timestamp."""
    from sqlalchemy import select as sa_select

    before = datetime.now(UTC)
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Proveedor UpdatedAt")

    response = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={"supplier_name": "Nombre Con Timestamp"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200

    db_session.expire_all()
    fresh = db_session.scalars(
        sa_select(Delivery).where(Delivery.id == delivery.id)
    ).one()
    assert fresh.updated_at is not None
    # Allow 5 seconds of clock slack; the timestamp must be after we started.
    from datetime import timedelta as td
    assert fresh.updated_at >= before - td(seconds=5)


@pytest.mark.asyncio
async def test_concurrent_patches_last_write_wins(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """Two sequential PATCHes from the same owner: the second one wins.

    This test documents the accepted last-write-wins behaviour for no_leida
    deliveries.  There is NO optimistic locking or ETag — the second commit
    simply overwrites the first.  See module docstring for rationale.
    """
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Proveedor Concurrent")

    first = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={"supplier_name": "Primer escritor"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert first.status_code == 200

    second = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={"supplier_name": "Segundo escritor gana"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert second.status_code == 200
    assert second.json()["supplier_name"] == "Segundo escritor gana"


@pytest.mark.asyncio
async def test_delivery_detail_does_not_expose_created_by(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """GET /{id} response must NOT contain the created_by field.

    The operator must not see the owner's UUID in the detail response.
    Traceability lives in the DB, not in the public API.
    """
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Proveedor NoCreadoPor")

    response = await client.get(
        f"/api/v1/deliveries/{delivery.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    assert "created_by" not in response.json()


@pytest.mark.asyncio
async def test_patch_no_change_returns_current(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """PATCH with only supplier_name (no items) returns the current state.

    Existing items are untouched when items key is omitted from the body.
    """
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, supplier_name="Nombre Viejo")
    _make_delivery_item(db_session, delivery, p1, owner_user.id, "5")

    response = await client.patch(
        f"/api/v1/deliveries/{delivery.id}",
        json={"supplier_name": "Nombre Nuevo"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["supplier_name"] == "Nombre Nuevo"
    # Item is still there.
    assert len(data["items"]) == 1
    assert data["items"][0]["product_name"] == "POLLO"


# ===========================================================================
# Issue #11 — Verification: open / confirm / validate / correct
# ===========================================================================

# ---------------------------------------------------------------------------
# Helpers: full verification flow shortcuts used by multiple tests
# ---------------------------------------------------------------------------


async def _open_delivery(
    client: AsyncClient, delivery_id: uuid.UUID, operator_token: str
) -> dict:
    r = await client.post(
        f"/api/v1/deliveries/{delivery_id}/open",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    return r


async def _confirm_item(
    client: AsyncClient,
    delivery_id: uuid.UUID,
    item_id: uuid.UUID,
    qty: str,
    operator_token: str,
):
    return await client.post(
        f"/api/v1/deliveries/{delivery_id}/items/{item_id}/confirm",
        json={"received_qty": qty},
        headers={"Authorization": f"Bearer {operator_token}"},
    )


async def _validate_delivery(
    client: AsyncClient, delivery_id: uuid.UUID, operator_token: str
):
    return await client.post(
        f"/api/v1/deliveries/{delivery_id}/validate",
        headers={"Authorization": f"Bearer {operator_token}"},
    )


# ---------------------------------------------------------------------------
# POST /deliveries/{id}/open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operator_opens_delivery_status_transitions(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Happy path: operator opens a no_leida delivery → en_verificacion."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="no_leida")
    _make_delivery_item(db_session, delivery, p1, owner_user.id)

    r = await _open_delivery(client, delivery.id, operator_token)

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "en_verificacion"
    assert data["id"] == str(delivery.id)
    # Items are returned in the detail response.
    assert len(data["items"]) == 1

    # DB reflects the change.
    db_session.expire_all()
    fresh = db_session.get(Delivery, delivery.id)
    assert fresh.status == "en_verificacion"
    assert fresh.updated_by == operator_user.id
    assert fresh.updated_at is not None


@pytest.mark.asyncio
async def test_operator_open_already_opened_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Opening an already-open delivery returns 409."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    _make_delivery_item(db_session, delivery, p1, owner_user.id)

    r = await _open_delivery(client, delivery.id, operator_token)

    assert r.status_code == 409
    assert "already open" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_operator_open_validated_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Opening a validated delivery returns 409."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="validada")
    _make_delivery_item(db_session, delivery, p1, owner_user.id)

    r = await _open_delivery(client, delivery.id, operator_token)

    assert r.status_code == 409
    assert "already validated" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_operator_open_nonexistent_returns_404(
    client: AsyncClient,
    operator_token: str,
) -> None:
    """Opening a non-existent delivery returns 404."""
    r = await _open_delivery(client, uuid.uuid4(), operator_token)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_owner_cannot_open_returns_403(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """Owner cannot open a delivery — endpoint is operator-only."""
    delivery = _make_delivery(db_session, owner_user.id, status="no_leida")

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/open",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# POST /deliveries/{id}/items/{item_id}/confirm
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operator_confirms_item_with_announced_qty(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Confirming with the announced qty: received_qty == announced_qty."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")

    r = await _confirm_item(client, delivery.id, item.id, "10", operator_token)

    assert r.status_code == 200
    data = r.json()
    assert data["received_qty"] == "10"
    assert data["id"] == str(item.id)


@pytest.mark.asyncio
async def test_operator_confirms_item_with_different_qty(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Confirming with a different qty (announced 10, received 8)."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")

    r = await _confirm_item(client, delivery.id, item.id, "8", operator_token)

    assert r.status_code == 200
    assert r.json()["received_qty"] == "8"
    assert r.json()["announced_qty"] == "10"

    db_session.expire_all()
    fresh = db_session.get(DeliveryItem, item.id)
    from decimal import Decimal
    assert fresh.received_qty == Decimal("8")


@pytest.mark.asyncio
async def test_operator_confirms_item_zero_qty(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Confirming with qty = 0 (product did not arrive) is valid."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")

    r = await _confirm_item(client, delivery.id, item.id, "0", operator_token)

    assert r.status_code == 200
    assert r.json()["received_qty"] == "0"


@pytest.mark.asyncio
async def test_operator_confirms_item_negative_returns_422(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """received_qty < 0 is rejected by Pydantic (ge=0) → 422."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{item.id}/confirm",
        json={"received_qty": "-1"},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_confirm_before_open_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Confirming an item on a no_leida delivery returns 409."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="no_leida")
    item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")

    r = await _confirm_item(client, delivery.id, item.id, "10", operator_token)

    assert r.status_code == 409
    assert "open" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_confirm_after_validate_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Confirming an item on a validated delivery returns 409."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="validada")
    item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10", received_qty="10")

    r = await _confirm_item(client, delivery.id, item.id, "10", operator_token)

    assert r.status_code == 409
    assert "validated" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_confirm_idempotent_same_qty_returns_200(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Confirming with the same qty a second time is idempotent → 200."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")

    # First confirm.
    r1 = await _confirm_item(client, delivery.id, item.id, "8", operator_token)
    assert r1.status_code == 200

    # Second confirm — same qty → idempotent.
    r2 = await _confirm_item(client, delivery.id, item.id, "8", operator_token)
    assert r2.status_code == 200
    assert r2.json()["received_qty"] == "8"


@pytest.mark.asyncio
async def test_confirm_different_qty_after_first_confirm_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Confirming with a DIFFERENT qty after first confirm → 409."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")

    r1 = await _confirm_item(client, delivery.id, item.id, "8", operator_token)
    assert r1.status_code == 200

    r2 = await _confirm_item(client, delivery.id, item.id, "9", operator_token)
    assert r2.status_code == 409
    assert "already confirmed" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_owner_cannot_confirm_returns_403(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """Owner cannot confirm items — endpoint is operator-only."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10")

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{item.id}/confirm",
        json={"received_qty": "10"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_confirm_item_not_in_delivery_returns_404(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Confirming an item that does not belong to the delivery returns 404."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{uuid.uuid4()}/confirm",
        json={"received_qty": "5"},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /deliveries/{id}/validate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_all_confirmed_success(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """All items confirmed → validate transitions to validada with audit fields."""
    p1, p2, _ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    _make_delivery_item(db_session, delivery, p1, owner_user.id, "10", received_qty="10")
    _make_delivery_item(db_session, delivery, p2, owner_user.id, "5", received_qty="4")

    r = await _validate_delivery(client, delivery.id, operator_token)

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "validada"
    assert data["validated_at"] is not None
    assert data["validated_by"] == str(operator_user.id)

    db_session.expire_all()
    fresh = db_session.get(Delivery, delivery.id)
    assert fresh.status == "validada"
    assert fresh.validated_by == operator_user.id
    assert fresh.validated_at is not None
    assert fresh.updated_by == operator_user.id


@pytest.mark.asyncio
async def test_validate_with_pending_items_returns_400_with_list(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """If any item lacks received_qty, validate returns 400 with the pending IDs."""
    p1, p2, _ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    i1 = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10", received_qty="10")
    i2 = _make_delivery_item(db_session, delivery, p2, owner_user.id, "5")  # not confirmed

    r = await _validate_delivery(client, delivery.id, operator_token)

    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "pending_item_ids" in detail
    assert str(i2.id) in detail["pending_item_ids"]
    assert str(i1.id) not in detail["pending_item_ids"]


@pytest.mark.asyncio
async def test_validate_wrong_status_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
) -> None:
    """Validating a no_leida delivery returns 409."""
    delivery = _make_delivery(db_session, owner_user.id, status="no_leida")

    r = await _validate_delivery(client, delivery.id, operator_token)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_concurrent_validate_second_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Two sequential validate calls: first succeeds, second returns 409.

    True concurrency is hard to test in a single-threaded test run.  This
    test validates the STATUS CHECK behaviour which is what the SELECT FOR
    UPDATE guard protects in production.  The race condition is: second
    request reads the now-validada status and returns 409.
    """
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    _make_delivery_item(db_session, delivery, p1, owner_user.id, "5", received_qty="5")

    r1 = await _validate_delivery(client, delivery.id, operator_token)
    assert r1.status_code == 200

    r2 = await _validate_delivery(client, delivery.id, operator_token)
    assert r2.status_code == 409
    assert "already validated" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_owner_cannot_validate_returns_403(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """Owner cannot validate a delivery — endpoint is operator-only."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    _make_delivery_item(db_session, delivery, p1, owner_user.id, "5", received_qty="5")

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/validate",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# POST /deliveries/{id}/items/{item_id}/correct
# ---------------------------------------------------------------------------


def _make_validated_delivery_with_item(
    db_session: Session,
    owner_id: uuid.UUID,
    product: Product,
    received_qty: str = "10",
    item_created_at: datetime | None = None,
) -> tuple[Delivery, DeliveryItem]:
    """Create a validated delivery with one confirmed item."""
    delivery = _make_delivery(db_session, owner_id, status="validada")
    item = _make_delivery_item(
        db_session,
        delivery,
        product,
        owner_id,
        "10",
        received_qty=received_qty,
        created_at=item_created_at,
    )
    return delivery, item


@pytest.mark.asyncio
async def test_operator_corrects_same_day_creates_new_item_with_corrects_id(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Same-day correction by operator: new row with corrects_id, original unchanged."""
    p1, *_ = active_products
    delivery, item = _make_validated_delivery_with_item(db_session, owner_user.id, p1)

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{item.id}/correct",
        json={"received_qty": "7", "reason": "supplier short-shipped"},
        headers={"Authorization": f"Bearer {operator_token}"},
    )

    assert r.status_code == 201
    data = r.json()
    assert data["corrects_id"] == str(item.id)
    assert data["received_qty"] == "7"
    assert data["reason"] == "supplier short-shipped"
    new_id = uuid.UUID(data["id"])
    assert new_id != item.id

    # Original item is untouched.
    db_session.expire_all()
    original = db_session.get(DeliveryItem, item.id)
    from decimal import Decimal
    assert original.received_qty == Decimal("10")
    assert original.corrects_id is None


@pytest.mark.asyncio
async def test_operator_correct_next_day_returns_403(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    operator_token: str,
    active_products: list[Product],
) -> None:
    """Operator cannot correct an item created on a previous calendar day (UTC-3)."""
    p1, *_ = active_products
    # Set item created_at to yesterday UTC-3 by using a timestamp 48 hours ago.
    yesterday = datetime.now(UTC) - timedelta(hours=48)
    delivery, item = _make_validated_delivery_with_item(
        db_session, owner_user.id, p1, item_created_at=yesterday
    )

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{item.id}/correct",
        json={"received_qty": "5"},
        headers={"Authorization": f"Bearer {operator_token}"},
    )

    assert r.status_code == 403
    assert "correction window closed" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_owner_correct_any_time_success(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """Owner can correct a validated item regardless of how old it is."""
    p1, *_ = active_products
    # Item created 10 days ago — outside any operator window.
    old_date = datetime.now(UTC) - timedelta(days=10)
    delivery, item = _make_validated_delivery_with_item(
        db_session, owner_user.id, p1, item_created_at=old_date
    )

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{item.id}/correct",
        json={"received_qty": "3"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert r.status_code == 201
    assert r.json()["received_qty"] == "3"
    assert r.json()["corrects_id"] == str(item.id)


@pytest.mark.asyncio
async def test_correct_before_validate_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """Correcting an item on a non-validated delivery returns 409."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="en_verificacion")
    item = _make_delivery_item(db_session, delivery, p1, owner_user.id, "10", received_qty="10")

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{item.id}/correct",
        json={"received_qty": "5"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert r.status_code == 409
    assert "not validated" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_correct_leaf_verification_cannot_correct_non_leaf(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """An item that has already been corrected (not a leaf) returns 404."""
    p1, *_ = active_products
    delivery = _make_delivery(db_session, owner_user.id, status="validada")
    original = _make_delivery_item(
        db_session, delivery, p1, owner_user.id, "10", received_qty="10"
    )
    # correction row points to original → original is no longer a leaf
    _correction = _make_delivery_item(
        db_session,
        delivery,
        p1,
        owner_user.id,
        "10",
        received_qty="8",
        corrects_id=original.id,
    )

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{original.id}/correct",
        json={"received_qty": "6"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_correct_creates_new_item_not_updates_original(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """Correction inserts a new row; the original row is never modified."""
    p1, *_ = active_products
    delivery, item = _make_validated_delivery_with_item(db_session, owner_user.id, p1)

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{item.id}/correct",
        json={"received_qty": "2"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201
    new_id = uuid.UUID(r.json()["id"])

    db_session.expire_all()

    # Original unchanged.
    original = db_session.get(DeliveryItem, item.id)
    from decimal import Decimal
    assert original.received_qty == Decimal("10")
    assert original.corrects_id is None

    # New row exists with corrects_id pointing to original.
    new_item = db_session.get(DeliveryItem, new_id)
    assert new_item is not None
    assert new_item.received_qty == Decimal("2")
    assert new_item.corrects_id == item.id

    # Two separate rows in total for this delivery + product.
    all_items = db_session.scalars(
        sa_select(DeliveryItem).where(DeliveryItem.delivery_id == delivery.id)
    ).all()
    assert len(all_items) == 2


@pytest.mark.asyncio
async def test_correct_records_updated_by_on_delivery(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """After a correction, delivery.updated_by reflects the correcting user."""
    p1, *_ = active_products
    delivery, item = _make_validated_delivery_with_item(db_session, owner_user.id, p1)

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{item.id}/correct",
        json={"received_qty": "1"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201

    db_session.expire_all()
    fresh = db_session.get(Delivery, delivery.id)
    assert fresh.updated_by == owner_user.id
    assert fresh.updated_at is not None


@pytest.mark.asyncio
async def test_correct_stores_reason(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """reason field is persisted in the new correction row (option b)."""
    p1, *_ = active_products
    delivery, item = _make_validated_delivery_with_item(db_session, owner_user.id, p1)

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{item.id}/correct",
        json={"received_qty": "4", "reason": "Counted wrong — was 4 not 10"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201
    assert r.json()["reason"] == "Counted wrong — was 4 not 10"

    new_id = uuid.UUID(r.json()["id"])
    db_session.expire_all()
    new_item = db_session.get(DeliveryItem, new_id)
    assert new_item.reason == "Counted wrong — was 4 not 10"


@pytest.mark.asyncio
async def test_correct_without_reason_stores_null(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
    active_products: list[Product],
) -> None:
    """When reason is omitted the column is stored as NULL."""
    p1, *_ = active_products
    delivery, item = _make_validated_delivery_with_item(db_session, owner_user.id, p1)

    r = await client.post(
        f"/api/v1/deliveries/{delivery.id}/items/{item.id}/correct",
        json={"received_qty": "6"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201
    assert r.json()["reason"] is None

    new_id = uuid.UUID(r.json()["id"])
    db_session.expire_all()
    new_item = db_session.get(DeliveryItem, new_id)
    assert new_item.reason is None


# ---------------------------------------------------------------------------
# Unit tests: time_windows helpers
# ---------------------------------------------------------------------------


def test_is_same_calendar_day_argentina_edge_cases() -> None:
    """Test edge cases for the UTC-3 calendar-day comparison."""
    from cocina_control.security.time_windows import (
        ARGENTINA_TZ,
        is_same_calendar_day_argentina,
    )

    # 23:59 UTC-3 and 00:00 UTC-3 the next calendar day → different days.
    d1 = datetime(2026, 7, 9, 23, 59, tzinfo=ARGENTINA_TZ)   # 23:59 on July 9 in AR
    d2 = datetime(2026, 7, 10, 0, 0, tzinfo=ARGENTINA_TZ)    # 00:00 on July 10 in AR
    assert not is_same_calendar_day_argentina(d1, d2)

    # 00:01 UTC is 21:01 UTC-3 on July 8 in AR →
    # 23:59 UTC-3 on July 9 is the NEXT day → different.
    d3 = datetime(2026, 7, 9, 0, 1, tzinfo=UTC)             # 21:01 AR July 8
    d4 = datetime(2026, 7, 9, 23, 59, tzinfo=ARGENTINA_TZ)  # 23:59 AR July 9
    assert not is_same_calendar_day_argentina(d3, d4)

    # Same instant expressed in two timezones → same calendar day.
    d5 = datetime(2026, 7, 9, 15, 0, tzinfo=ARGENTINA_TZ)   # 15:00 AR July 9
    d6 = datetime(2026, 7, 9, 18, 0, tzinfo=UTC)             # 15:00 AR July 9 (UTC+0+3)
    assert is_same_calendar_day_argentina(d5, d6)

    # Noon UTC (09:00 AR) and 23:59 AR → same calendar day.
    d7 = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)             # 09:00 AR July 9
    d8 = datetime(2026, 7, 9, 23, 59, tzinfo=ARGENTINA_TZ)  # 23:59 AR July 9
    assert is_same_calendar_day_argentina(d7, d8)

    # Midnight UTC (21:00 AR previous day) and 23:00 AR → same calendar day.
    d9 = datetime(2026, 7, 10, 0, 0, tzinfo=UTC)             # 21:00 AR July 9
    d10 = datetime(2026, 7, 9, 23, 0, tzinfo=ARGENTINA_TZ)  # 23:00 AR July 9
    assert is_same_calendar_day_argentina(d9, d10)
