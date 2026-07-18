"""Integration tests for the product catalogue endpoints.

All fixtures (owner_user, cocinero_user, owner_token, cocinero_token, client,
db_session) are provided by conftest.py.

Every test runs inside a SAVEPOINT that is rolled back after the test, so
product rows created here never persist to other tests.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

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
    low_stock_threshold=None,
) -> Product:
    """Insert a Product directly into the DB, bypassing the API."""
    product = Product(
        id=uuid.uuid4(),
        name=name.upper(),
        unit=unit,
        is_active=is_active,
        created_by=owner_id,
        low_stock_threshold=low_stock_threshold,
    )
    session.add(product)
    session.flush()
    return product


# ---------------------------------------------------------------------------
# GET /api/v1/products
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_products_returns_only_active(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """List endpoint returns only active products; inactive ones are hidden."""
    _make_product(db_session, owner_user.id, "POLLO")
    _make_product(db_session, owner_user.id, "PAPA")
    _make_product(db_session, owner_user.id, "PALTA", is_active=False)

    response = await client.get(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert "POLLO" in names
    assert "PAPA" in names
    assert "PALTA" not in names
    assert len(names) == 2


@pytest.mark.asyncio
async def test_list_products_alphabetical_order(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """Products are returned sorted alphabetically by name."""
    _make_product(db_session, owner_user.id, "ZAPALLO")
    _make_product(db_session, owner_user.id, "AJO")
    _make_product(db_session, owner_user.id, "MAIZ")

    response = await client.get(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_list_products_no_auth_returns_401(client: AsyncClient) -> None:
    """GET /products without a token must return 401."""
    response = await client.get("/api/v1/products")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/products
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_product_owner_success(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """Owner can create a product; name is returned in UPPER CASE."""
    response = await client.post(
        "/api/v1/products",
        json={"name": "palta", "unit": "un"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "PALTA"
    assert data["unit"] == "un"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_product_admin_success(
    client: AsyncClient,
    admin_token: str,
) -> None:
    """Admin can create a product (creacion inline desde la orden, issue #126)."""
    response = await client.post(
        "/api/v1/products",
        json={"name": "papas fritas", "unit": "kg"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "PAPAS FRITAS"
    assert data["unit"] == "kg"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_product_default_flags_purchase_only(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """Sin flags explicitos, el producto nace como compra (no venta) — issue #140."""
    response = await client.post(
        "/api/v1/products",
        json={"name": "arroz", "unit": "kg"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["is_purchase"] is True
    assert data["is_sale"] is False


@pytest.mark.asyncio
async def test_create_product_sale_and_both_flags(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """Se puede crear un producto solo-venta y uno de ambos flujos — issue #140."""
    r_sale = await client.post(
        "/api/v1/products",
        json={"name": "bowl clasico", "unit": "un", "is_purchase": False, "is_sale": True},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r_sale.status_code == 201
    assert r_sale.json()["is_sale"] is True
    assert r_sale.json()["is_purchase"] is False

    r_both = await client.post(
        "/api/v1/products",
        json={"name": "gaseosa lata", "unit": "un", "is_purchase": True, "is_sale": True},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r_both.status_code == 201
    assert r_both.json()["is_purchase"] is True
    assert r_both.json()["is_sale"] is True


@pytest.mark.asyncio
async def test_create_product_neither_flag_rejected(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """Un producto que no es de compra NI de venta se rechaza con 422 — issue #140."""
    response = await client.post(
        "/api/v1/products",
        json={"name": "fantasma", "unit": "un", "is_purchase": False, "is_sale": False},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_products_flow_filter(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """?flow=purchase y ?flow=sale filtran el catalogo por flujo — issue #140."""
    headers = {"Authorization": f"Bearer {owner_token}"}
    await client.post(
        "/api/v1/products",
        json={"name": "papa insumo", "unit": "kg"},
        headers=headers,
    )
    await client.post(
        "/api/v1/products",
        json={"name": "bowl venta", "unit": "un", "is_purchase": False, "is_sale": True},
        headers=headers,
    )

    r_purchase = await client.get("/api/v1/products?flow=purchase", headers=headers)
    assert r_purchase.status_code == 200
    purchase_names = [p["name"] for p in r_purchase.json()]
    assert "PAPA INSUMO" in purchase_names
    assert "BOWL VENTA" not in purchase_names

    r_sale = await client.get("/api/v1/products?flow=sale", headers=headers)
    assert r_sale.status_code == 200
    sale_names = [p["name"] for p in r_sale.json()]
    assert "BOWL VENTA" in sale_names
    assert "PAPA INSUMO" not in sale_names


@pytest.mark.asyncio
async def test_update_product_cannot_clear_both_flags(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """PATCH que dejaria el producto sin ningun flujo se rechaza con 422 — issue #140."""
    headers = {"Authorization": f"Bearer {owner_token}"}
    created = await client.post(
        "/api/v1/products",
        json={"name": "quinua", "unit": "kg"},
        headers=headers,
    )
    product_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/products/{product_id}",
        json={"is_purchase": False},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_product_operator_returns_403(
    client: AsyncClient,
    cocinero_token: str,
) -> None:
    """Operator cannot create products — must receive 403."""
    response = await client.post(
        "/api/v1/products",
        json={"name": "pollo", "unit": "kg"},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_product_duplicate_name_returns_409(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """Creating a product whose name (after normalisation) already exists as active returns 409."""
    _make_product(db_session, owner_user.id, "ZAPALLO")

    response = await client.post(
        "/api/v1/products",
        json={"name": "zapallo", "unit": "kg"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 409
    assert "ZAPALLO" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_product_duplicate_name_after_deactivating_prev_allowed(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """A name that belongs to an *inactive* product can be reused."""
    _make_product(db_session, owner_user.id, "TOMATE", is_active=False)

    response = await client.post(
        "/api/v1/products",
        json={"name": "tomate", "unit": "kg"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "TOMATE"


@pytest.mark.asyncio
async def test_create_product_invalid_unit_returns_422(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """An unsupported unit value must return 422 (Pydantic validation)."""
    response = await client.post(
        "/api/v1/products",
        json={"name": "papa", "unit": "xyz"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_product_negative_threshold_returns_422(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """A negative low_stock_threshold must return 422 (Field(gt=0))."""
    response = await client.post(
        "/api/v1/products",
        json={"name": "pollo", "unit": "kg", "low_stock_threshold": -1},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_product_name_whitespace_only_returns_400_or_422(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """A name composed only of whitespace is rejected (400 or 422)."""
    for bad_name in ("   ", "\t", "\n"):
        response = await client.post(
            "/api/v1/products",
            json={"name": bad_name, "unit": "kg"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert response.status_code in (400, 422), (
            f"Expected 400 or 422 for name={bad_name!r}, got {response.status_code}"
        )


@pytest.mark.asyncio
async def test_create_product_normalizes_internal_whitespace(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """Internal whitespace runs (spaces, tabs) are collapsed to a single space and uppercased."""
    for raw_name in ("palta\tsemilla", "palta  semilla"):
        response = await client.post(
            "/api/v1/products",
            json={"name": raw_name, "unit": "kg"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        # One of them will succeed (201) and the other will conflict (409) because
        # both normalise to the same "PALTA SEMILLA". We only assert the name shape
        # when the creation succeeds.
        if response.status_code == 201:
            assert response.json()["name"] == "PALTA SEMILLA"
        else:
            assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_product_normalized_name_conflict(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """After inserting 'PALTA SEMILLA', sending 'palta semilla' (tab) must return 409."""
    _make_product(db_session, owner_user.id, "PALTA SEMILLA")

    response = await client.post(
        "/api/v1/products",
        json={"name": "palta\tsemilla", "unit": "kg"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_product_name_too_long_returns_422(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """A name exceeding 255 characters must return 422."""
    long_name = "A" * 300
    response = await client.post(
        "/api/v1/products",
        json={"name": long_name, "unit": "kg"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/v1/products/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_product_updates_threshold(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """PATCH with only low_stock_threshold updates that field."""
    product = _make_product(db_session, owner_user.id, "ARROZ")

    response = await client.patch(
        f"/api/v1/products/{product.id}",
        json={"low_stock_threshold": "5.5"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    assert float(response.json()["low_stock_threshold"]) == pytest.approx(5.5)


@pytest.mark.asyncio
async def test_patch_product_rename_normalizes_uppercase(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """PATCH with a lowercase name stores it in UPPER CASE."""
    product = _make_product(db_session, owner_user.id, "HARINA")

    response = await client.patch(
        f"/api/v1/products/{product.id}",
        json={"name": "harina fina"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "HARINA FINA"


@pytest.mark.asyncio
async def test_patch_product_inactive_returns_404(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """PATCH on an inactive product must return 404 (not a visible conflict)."""
    product = _make_product(db_session, owner_user.id, "CEBOLLA", is_active=False)

    response = await client.patch(
        f"/api/v1/products/{product.id}",
        json={"unit": "kg"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_product_operator_returns_403(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    cocinero_token: str,
) -> None:
    """Operator cannot patch products."""
    product = _make_product(db_session, owner_user.id, "ACEITE")

    response = await client.patch(
        f"/api/v1/products/{product.id}",
        json={"unit": "lt"},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_nonexistent_product_returns_404(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """PATCH on a non-existent product UUID must return 404."""
    response = await client.patch(
        f"/api/v1/products/{uuid.uuid4()}",
        json={"unit": "kg"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_operator_on_nonexistent_returns_403(
    client: AsyncClient,
    cocinero_token: str,
) -> None:
    """Operator hitting PATCH on a non-existent product gets 403, not 404.

    Authorization is checked before loading the resource, so the operator
    cannot probe whether a product exists or not.
    """
    response = await client.patch(
        f"/api/v1/products/{uuid.uuid4()}",
        json={"unit": "kg"},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_records_updated_by(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """PATCH as owner sets updated_by to the owner's id in the database."""
    product = _make_product(db_session, owner_user.id, "FIDEOS")

    response = await client.patch(
        f"/api/v1/products/{product.id}",
        json={"unit": "un"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200

    db_session.expire(product)
    refreshed = db_session.get(Product, product.id)
    assert refreshed is not None
    assert refreshed.updated_by == owner_user.id
    assert refreshed.updated_at is not None


# ---------------------------------------------------------------------------
# DELETE /api/v1/products/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_product_soft_delete_only(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """DELETE sets is_active=False; the row must still exist in the DB."""
    product = _make_product(db_session, owner_user.id, "MANTECA")

    response = await client.delete(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 204

    # Verify row still exists with is_active = False
    db_session.expire(product)
    refreshed = db_session.get(Product, product.id)
    assert refreshed is not None
    assert refreshed.is_active is False


@pytest.mark.asyncio
async def test_delete_product_already_inactive_returns_404(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """DELETEing an already inactive product must return 404."""
    product = _make_product(db_session, owner_user.id, "VINAGRE", is_active=False)

    response = await client.delete(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_product_operator_returns_403(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    cocinero_token: str,
) -> None:
    """Operator cannot delete (deactivate) products."""
    product = _make_product(db_session, owner_user.id, "SAL")

    response = await client.delete(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_nonexistent_product_returns_404(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """DELETE with an invented UUID as owner must return 404."""
    response = await client.delete(
        f"/api/v1/products/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_operator_on_nonexistent_returns_403(
    client: AsyncClient,
    cocinero_token: str,
) -> None:
    """Operator hitting DELETE on a non-existent product gets 403, not 404.

    Authorization is checked before loading the resource, so the operator
    cannot probe whether a product exists or not.
    """
    response = await client.delete(
        f"/api/v1/products/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_records_updated_by(
    client: AsyncClient,
    db_session: Session,
    owner_user,
    owner_token: str,
) -> None:
    """DELETE (soft) as owner sets updated_by to the owner's id in the database."""
    product = _make_product(db_session, owner_user.id, "AZUCAR")

    response = await client.delete(
        f"/api/v1/products/{product.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 204

    db_session.expire(product)
    refreshed = db_session.get(Product, product.id)
    assert refreshed is not None
    assert refreshed.is_active is False
    assert refreshed.updated_by == owner_user.id
    assert refreshed.updated_at is not None
