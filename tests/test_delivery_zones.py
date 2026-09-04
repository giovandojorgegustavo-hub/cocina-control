"""Integration tests de la administracion de zonas de reparto.

La propiedad que se prueba aca: **la lista de distritos con cobertura la
decide el dueno desde el panel, y el asistente solo ve lo que esta encendido**.
Un cocinero no toca tarifas, un distrito no se duplica por escribirlo con otra
tilde, y apagar uno lo saca del cotizador sin borrar su historia.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.delivery_zone import DeliveryZone

from .conftest import create_test_user
from .test_sales_orders import _auth
from .test_service_principals import create_service_principal, svc_headers

ZONES_URL = "/api/v1/delivery-zones"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def asistente_user(db_session: Session):
    return create_test_user(db_session, "asistente_pedidos", f"bot-{uuid.uuid4().hex[:6]}@test.com")


@pytest.fixture
def bot_headers(db_session: Session, asistente_user) -> dict[str, str]:
    """Como llega de verdad el asistente: service token + X-Act-As."""
    _, token = create_service_principal(db_session, name=f"wa-{uuid.uuid4().hex[:6]}")
    return svc_headers(token, asistente_user.email)


@pytest.fixture
def zona(db_session: Session, owner_user) -> DeliveryZone:
    zone = DeliveryZone(
        id=uuid.uuid4(),
        district="Jesús María",
        fee=Decimal("5.00"),
        is_active=True,
        created_by=owner_user.id,
    )
    db_session.add(zone)
    db_session.flush()
    return zone


# ---------------------------------------------------------------------------
# POST /delivery-zones
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_admin_da_de_alta_un_distrito(client: AsyncClient, admin_token, admin_user):
    resp = await client.post(
        ZONES_URL,
        json={"district": "  Lince ", "fee": "7"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["district"] == "Lince"
    assert body["fee"] == "7.00"
    assert body["is_active"] is True
    assert body["updated_at"] is None
    uuid.UUID(body["id"])


@pytest.mark.anyio
async def test_el_cocinero_no_da_de_alta_distritos(client: AsyncClient, cocinero_token):
    resp = await client.post(
        ZONES_URL, json={"district": "Lince", "fee": "7"}, headers=_auth(cocinero_token)
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_el_asistente_no_da_de_alta_distritos(client: AsyncClient, bot_headers):
    resp = await client.post(ZONES_URL, json={"district": "Lince", "fee": "7"}, headers=bot_headers)
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_el_mismo_distrito_con_otra_tilde_es_409(client: AsyncClient, owner_token, zona):
    """ "jesus maria" y "Jesús María" son el mismo distrito: un solo precio."""
    resp = await client.post(
        ZONES_URL, json={"district": "jesus  maria", "fee": "9"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 409, resp.text
    assert "Jesús María" in resp.json()["detail"]


@pytest.mark.anyio
async def test_un_distrito_apagado_tambien_bloquea_el_alta(
    client: AsyncClient, owner_token, db_session, zona
):
    """Lo correcto es volver a encender la fila, no crear una melliza."""
    zona.is_active = False
    db_session.flush()
    resp = await client.post(
        ZONES_URL, json={"district": "JESUS MARIA", "fee": "5"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_la_tarifa_negativa_es_422(client: AsyncClient, owner_token):
    resp = await client.post(
        ZONES_URL, json={"district": "Lince", "fee": "-1"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_el_distrito_vacio_es_422(client: AsyncClient, owner_token):
    resp = await client.post(
        ZONES_URL, json={"district": "   ", "fee": "5"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /delivery-zones/{id}
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_owner_cambia_la_tarifa(client: AsyncClient, owner_token, owner_user, zona):
    resp = await client.patch(
        f"{ZONES_URL}/{zona.id}", json={"fee": "6.5"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["fee"] == "6.50"
    assert body["district"] == "Jesús María"
    assert body["updated_at"] is not None
    assert zona.updated_by == owner_user.id


@pytest.mark.anyio
async def test_el_cocinero_no_cambia_tarifas(client: AsyncClient, cocinero_token, zona):
    resp = await client.patch(
        f"{ZONES_URL}/{zona.id}", json={"fee": "6.5"}, headers=_auth(cocinero_token)
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_una_zona_inexistente_es_404(client: AsyncClient, owner_token):
    resp = await client.patch(
        f"{ZONES_URL}/{uuid.uuid4()}", json={"fee": "6.5"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_el_patch_vacio_es_422(client: AsyncClient, owner_token, zona):
    resp = await client.patch(f"{ZONES_URL}/{zona.id}", json={}, headers=_auth(owner_token))
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_renombrar_a_un_distrito_existente_es_409(
    client: AsyncClient, owner_token, db_session, owner_user, zona
):
    otra = DeliveryZone(
        id=uuid.uuid4(),
        district="Lince",
        fee=Decimal("7.00"),
        is_active=True,
        created_by=owner_user.id,
    )
    db_session.add(otra)
    db_session.flush()

    resp = await client.patch(
        f"{ZONES_URL}/{otra.id}", json={"district": "jesús maría"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 409

    # Renombrarse a si misma con otra caja no choca con su propia fila.
    resp = await client.patch(
        f"{ZONES_URL}/{otra.id}", json={"district": "LINCE"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["district"] == "LINCE"


# ---------------------------------------------------------------------------
# Apagar una zona: desaparece para el asistente, sigue para el dueno
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_una_zona_apagada_deja_de_cotizar(
    client: AsyncClient, owner_token, bot_headers, zona
):
    resp = await client.get(
        f"{ZONES_URL}/quote", params={"district": "jesus maria"}, headers=bot_headers
    )
    assert resp.json()["covered"] is True

    resp = await client.patch(
        f"{ZONES_URL}/{zona.id}", json={"is_active": False}, headers=_auth(owner_token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    resp = await client.get(
        f"{ZONES_URL}/quote", params={"district": "jesus maria"}, headers=bot_headers
    )
    assert resp.status_code == 200
    assert resp.json() == {"district": "jesus maria", "covered": False, "fee": None}

    resp = await client.get(ZONES_URL, headers=bot_headers)
    assert resp.status_code == 200
    assert [z["id"] for z in resp.json()] == []


@pytest.mark.anyio
async def test_el_owner_ve_las_apagadas_con_all(client: AsyncClient, owner_token, db_session, zona):
    zona.is_active = False
    db_session.flush()

    resp = await client.get(ZONES_URL, headers=_auth(owner_token))
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.get(ZONES_URL, params={"all": "true"}, headers=_auth(owner_token))
    assert resp.status_code == 200
    ids = [z["id"] for z in resp.json()]
    assert ids == [str(zona.id)]
    assert resp.json()[0]["is_active"] is False


@pytest.mark.anyio
async def test_el_cocinero_no_ve_las_apagadas(client: AsyncClient, cocinero_token, zona):
    """Sin all sigue leyendo; con all=true es 403, no una lista vacia."""
    resp = await client.get(ZONES_URL, headers=_auth(cocinero_token))
    assert resp.status_code == 200

    resp = await client.get(ZONES_URL, params={"all": "true"}, headers=_auth(cocinero_token))
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_el_asistente_tampoco_ve_las_apagadas(client: AsyncClient, bot_headers, zona):
    resp = await client.get(ZONES_URL, params={"all": "true"}, headers=bot_headers)
    assert resp.status_code == 403
