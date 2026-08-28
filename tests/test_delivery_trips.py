"""Tests del viaje de reparto.

Las dos propiedades que importan y que estos tests fijan:

1. **Un pedido no puede salir en dos viajes.** Reasignarlo en silencio borraria
   el rastro del primero, y con el rastro se va el margen del reparto.
2. **Si inDrive no responde, el viaje se registra igual.** Un reparto real no
   se puede bloquear porque un tercero cambio su JSON o se cayo.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.customer import Customer, CustomerAddress
from cocina_control.models.delivery_trip import DeliveryTrip
from cocina_control.models.product import Product
from cocina_control.models.sales_order import SalesOrder
from cocina_control.services.indrive import ViajeLeido, url_de_api

from .conftest import create_test_user

URL = "/api/v1/delivery-trips"
LINK = "https://sharetrip.indrive.com/delivery/cust/abc123/tok456"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def despachador_token(db_session: Session) -> str:
    from cocina_control.security.tokens import create_access_token

    u = create_test_user(db_session, "owner", f"desp-{uuid.uuid4().hex[:6]}@test.com")
    return create_access_token(u.id, u.role)


@pytest.fixture
def pedido(db_session: Session, owner_user) -> SalesOrder:
    p = Product(
        id=uuid.uuid4(), name=f"BOWL {uuid.uuid4().hex[:5]}", unit="un",
        is_active=True, is_purchase=False, is_sale=True,
        sale_price=Decimal("33.00"), created_by=owner_user.id,
    )
    c = Customer(id=uuid.uuid4(), phone="+51900000009", name="Ana", created_by=owner_user.id)
    db_session.add_all([p, c]); db_session.flush()
    a = CustomerAddress(
        id=uuid.uuid4(), customer_id=c.id, district="Surco",
        address_line="Av 1", is_default=True, created_by=owner_user.id,
    )
    db_session.add(a); db_session.flush()
    o = SalesOrder(
        id=uuid.uuid4(), customer_id=c.id, address_id=a.id, channel="whatsapp",
        status="confirmed", items_total=Decimal("33.00"),
        delivery_fee=Decimal("10.00"), total=Decimal("43.00"), created_by=owner_user.id,
    )
    db_session.add(o); db_session.flush()
    return o


@pytest.fixture(autouse=True)
def indrive_falso(monkeypatch):
    """Por defecto inDrive responde bien. Cada test lo cambia si lo necesita."""
    monkeypatch.setattr(
        "cocina_control.api.delivery_trips.leer_viaje",
        lambda url: ViajeLeido("on_delivery", Decimal("14.50"), True),
    )


def test_el_link_se_convierte_en_url_de_api():
    """El link que ve una persona no devuelve JSON; el de la API sí."""
    assert url_de_api(LINK) == (
        "https://sharetrip.indrive.com/proxy/share/api/v2/share/delivery/cust/abc123/tok456"
    )
    assert url_de_api("https://otro-dominio.com/x") is None
    # Idempotente: si ya viene convertido, no se convierte dos veces.
    ya = url_de_api(LINK)
    assert url_de_api(ya) == ya


@pytest.mark.anyio
async def test_registra_el_viaje_y_despacha_el_pedido(
    client: AsyncClient, despachador_token, pedido, db_session
):
    r = await client.post(
        URL,
        json={"tracking_url": LINK, "sales_order_ids": [str(pedido.id)]},
        headers=_auth(despachador_token),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["trip_cost"] == "14.50"
    assert body["status"] == "on_delivery"
    # Lo que el asistente necesita para avisarle al cliente.
    assert body["orders"][0]["customer_phone"] == "+51900000009"

    db_session.refresh(pedido)
    assert pedido.status == "dispatched"
    assert pedido.delivery_trip_id is not None


@pytest.mark.anyio
async def test_un_pedido_no_puede_salir_en_dos_viajes(
    client: AsyncClient, despachador_token, pedido
):
    body = {"tracking_url": LINK, "sales_order_ids": [str(pedido.id)]}
    assert (await client.post(URL, json=body, headers=_auth(despachador_token))).status_code == 201
    otro = {"tracking_url": LINK + "2", "sales_order_ids": [str(pedido.id)]}
    r = await client.post(URL, json=otro, headers=_auth(despachador_token))
    assert r.status_code == 409
    assert "otro viaje" in r.json()["detail"]


@pytest.mark.anyio
async def test_el_mismo_link_no_se_registra_dos_veces(
    client: AsyncClient, despachador_token, pedido, db_session, owner_user
):
    """Contarlo dos veces duplicaría el costo y el margen saldría mal."""
    assert (
        await client.post(
            URL, json={"tracking_url": LINK, "sales_order_ids": [str(pedido.id)]},
            headers=_auth(despachador_token),
        )
    ).status_code == 201

    otro = SalesOrder(
        id=uuid.uuid4(), customer_id=pedido.customer_id, address_id=pedido.address_id,
        channel="whatsapp", status="confirmed", items_total=Decimal("28.00"),
        delivery_fee=Decimal("10.00"), total=Decimal("38.00"), created_by=owner_user.id,
    )
    db_session.add(otro); db_session.flush()

    r = await client.post(
        URL, json={"tracking_url": LINK, "sales_order_ids": [str(otro.id)]},
        headers=_auth(despachador_token),
    )
    assert r.status_code == 409
    assert "ya está registrado" in r.json()["detail"]


@pytest.mark.anyio
async def test_si_indrive_no_responde_el_viaje_igual_se_registra(
    client: AsyncClient, despachador_token, pedido, db_session, monkeypatch
):
    """EL TEST QUE IMPORTA: un tercero caído no puede frenar un reparto real."""
    monkeypatch.setattr(
        "cocina_control.api.delivery_trips.leer_viaje",
        lambda url: ViajeLeido(None, None, False),
    )
    r = await client.post(
        URL, json={"tracking_url": LINK, "sales_order_ids": [str(pedido.id)]},
        headers=_auth(despachador_token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["trip_cost"] is None
    assert r.json()["status"] is None
    db_session.refresh(pedido)
    assert pedido.status == "dispatched"


@pytest.mark.anyio
async def test_un_link_que_no_es_de_indrive_se_rechaza(
    client: AsyncClient, despachador_token, pedido
):
    r = await client.post(
        URL,
        json={"tracking_url": "https://algo-raro.com/rastreo/123", "sales_order_ids": [str(pedido.id)]},
        headers=_auth(despachador_token),
    )
    assert r.status_code == 422


@pytest.mark.anyio
async def test_dos_pedidos_un_viaje_y_el_margen_queda_medible(
    client: AsyncClient, despachador_token, pedido, db_session, owner_user
):
    otro = SalesOrder(
        id=uuid.uuid4(), customer_id=pedido.customer_id, address_id=pedido.address_id,
        channel="whatsapp", status="confirmed", items_total=Decimal("28.00"),
        delivery_fee=Decimal("10.00"), total=Decimal("38.00"), created_by=owner_user.id,
    )
    db_session.add(otro); db_session.flush()

    r = await client.post(
        URL,
        json={"tracking_url": LINK, "sales_order_ids": [str(pedido.id), str(otro.id)]},
        headers=_auth(despachador_token),
    )
    assert r.status_code == 201, r.text
    assert len(r.json()["orders"]) == 2

    viaje = db_session.get(DeliveryTrip, uuid.UUID(r.json()["id"]))
    cobrado = pedido.delivery_fee + otro.delivery_fee   # 20.00
    assert cobrado - viaje.trip_cost == Decimal("5.50")  # margen del reparto
