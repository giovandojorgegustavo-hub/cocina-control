"""Integration tests for the delivery pre-load endpoints (issue #10).

Covers POST / GET (list) / GET (detail) / PATCH on /api/v1/deliveries.
Verification endpoints (open/confirm/validate/correct) are issue #11.

Fixtures inherited from conftest.py:
  owner_user, operator_user, owner_token, operator_token,
  client, db_session.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from httpx import AsyncClient
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
    corrects_id: uuid.UUID | None = None,
) -> DeliveryItem:
    item = DeliveryItem(
        id=uuid.uuid4(),
        delivery_id=delivery.id,
        product_id=product.id,
        announced_qty=announced_qty,
        received_qty=None,
        corrects_id=corrects_id,
        created_by=owner_id,
    )
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
