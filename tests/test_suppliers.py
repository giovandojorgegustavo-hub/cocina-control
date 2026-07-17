"""Tests for the suppliers registry endpoints (issue #129).

All fixtures (owner_user, admin_user, cocinero_user, tokens, client, db_session)
come from conftest.py.
"""

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# POST /api/v1/suppliers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_supplier_owner_success(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """Owner can create a supplier; name is normalised to UPPER CASE."""
    response = await client.post(
        "/api/v1/suppliers",
        json={"name": "verduleria  nuñez", "phone": "999888777"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "VERDULERIA NUÑEZ"
    assert data["phone"] == "999888777"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_supplier_admin_success(
    client: AsyncClient,
    admin_token: str,
) -> None:
    """Admin can create a supplier (creacion inline desde la orden)."""
    response = await client.post(
        "/api/v1/suppliers",
        json={"name": "carniceria lopez"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "CARNICERIA LOPEZ"
    assert data["phone"] is None


@pytest.mark.asyncio
async def test_create_supplier_cocinero_returns_403(
    client: AsyncClient,
    cocinero_token: str,
) -> None:
    """Cocinero cannot create suppliers."""
    response = await client.post(
        "/api/v1/suppliers",
        json={"name": "mercado central"},
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_supplier_duplicate_name_returns_409(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """Same normalised name twice among active suppliers -> 409."""
    headers = {"Authorization": f"Bearer {owner_token}"}
    first = await client.post(
        "/api/v1/suppliers", json={"name": "avicola sur"}, headers=headers
    )
    assert first.status_code == 201

    dup = await client.post(
        "/api/v1/suppliers", json={"name": "  AVICOLA   sur "}, headers=headers
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_create_supplier_blank_name_rejected(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """Whitespace-only name is rejected with a validation error."""
    response = await client.post(
        "/api/v1/suppliers",
        json={"name": "   "},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_create_supplier_phone_whitespace_becomes_null(
    client: AsyncClient,
    owner_token: str,
) -> None:
    """A whitespace-only phone is stored as NULL, not as an empty string."""
    response = await client.post(
        "/api/v1/suppliers",
        json={"name": "distribuidora norte", "phone": "   "},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 201
    assert response.json()["phone"] is None


# ---------------------------------------------------------------------------
# GET /api/v1/suppliers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_suppliers_ordered_and_authenticated(
    client: AsyncClient,
    owner_token: str,
    cocinero_token: str,
) -> None:
    """Any authenticated user can list; results ordered by name."""
    headers = {"Authorization": f"Bearer {owner_token}"}
    await client.post("/api/v1/suppliers", json={"name": "zeta carnes"}, headers=headers)
    await client.post("/api/v1/suppliers", json={"name": "alfa verduras"}, headers=headers)

    response = await client.get(
        "/api/v1/suppliers",
        headers={"Authorization": f"Bearer {cocinero_token}"},
    )
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert "ALFA VERDURAS" in names
    assert "ZETA CARNES" in names
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_list_suppliers_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/suppliers")
    assert response.status_code in (401, 403)
