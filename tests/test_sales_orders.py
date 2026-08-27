"""Integration tests del pedido de venta, la carta, las tarifas y los pagos.

Este modulo existe sobre todo por una propiedad, y es la que da nombre a la
mitad de los tests: **el asistente de WhatsApp puede cobrar pero no puede
firmar**. Puede crear un pedido, calcular su total y registrar el pago con su
foto; no puede declarar que la plata llego. Esa frontera se prueba desde los dos
lados — que el camino legitimo funcione, y que el ilegitimo devuelva error.

La segunda propiedad, menos visible pero igual de cara si se rompe: **el cliente
no manda importes**. Los precios salen de products.sale_price y delivery_zones.
Si viajaran en el request, quien tenga el token del asistente podria crear un
pedido de dos bowls por S/ 1 y todos los CHECK de la base cuadrarian.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.delivery_zone import DeliveryZone
from cocina_control.models.payment import Payment
from cocina_control.models.product import Product

from .conftest import create_test_user
from .test_service_principals import create_service_principal, svc_headers

MENU_URL = "/api/v1/catalog/menu"
ZONES_URL = "/api/v1/delivery-zones"
ORDERS_URL = "/api/v1/sales-orders"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def asistente_user(db_session: Session):
    return create_test_user(
        db_session, "asistente_pedidos", f"bot-{uuid.uuid4().hex[:6]}@test.com"
    )


@pytest.fixture
def bot_headers(db_session: Session, asistente_user) -> dict[str, str]:
    """Como llega de verdad el asistente: service token + X-Act-As."""
    _, token = create_service_principal(db_session, name=f"wa-{uuid.uuid4().hex[:6]}")
    return svc_headers(token, asistente_user.email)


@pytest.fixture
def zona(db_session: Session, owner_user) -> DeliveryZone:
    zone = DeliveryZone(
        id=uuid.uuid4(),
        district="Pueblo Libre",
        fee=Decimal("5.00"),
        is_active=True,
        created_by=owner_user.id,
    )
    db_session.add(zone)
    db_session.flush()
    return zone


def _make_product(session: Session, owner, name: str, price: str | None) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name=name,
        unit="un",
        is_active=True,
        is_purchase=False,
        is_sale=True,
        sale_price=Decimal(price) if price is not None else None,
        created_by=owner.id,
    )
    session.add(product)
    session.flush()
    return product


@pytest.fixture
def energy_bowl(db_session: Session, owner_user) -> Product:
    return _make_product(db_session, owner_user, f"ENERGY BOWL {uuid.uuid4().hex[:4]}", "33.00")


@pytest.fixture
def pollo_extra(db_session: Session, owner_user) -> Product:
    return _make_product(db_session, owner_user, f"FILETE POLLO {uuid.uuid4().hex[:4]}", "7.00")


def _order_payload(product_id, district="Pueblo Libre", quantity=2, options=None):
    return {
        "customer": {"phone": "+51966497671", "name": "Katy"},
        "address": {
            "district": district,
            "address_line": "Av. La Marina 1234",
            "reference": "puerta verde",
        },
        "channel": "whatsapp",
        "conversation_ref": "conv-abc",
        "items": [
            {
                "product_id": str(product_id),
                "quantity": quantity,
                "options": options or [],
            }
        ],
    }


# ---------------------------------------------------------------------------
# La cuenta la hace el servidor
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_servidor_calcula_el_total(
    client: AsyncClient, bot_headers, zona, energy_bowl
):
    resp = await client.post(
        ORDERS_URL, json=_order_payload(energy_bowl.id), headers=bot_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # 2 x 33 = 66, mas 5 de reparto.
    assert body["items_total"] == "66.00"
    assert body["delivery_fee"] == "5.00"
    assert body["total"] == "71.00"
    assert body["status"] == "confirmed"


@pytest.mark.anyio
async def test_la_opcion_con_producto_suma_su_precio(
    client: AsyncClient, bot_headers, zona, energy_bowl, pollo_extra
):
    payload = _order_payload(
        energy_bowl.id,
        quantity=1,
        options=[
            {
                "option_group": "proteina-extra",
                "option_name": "Filete de pollo",
                "product_id": str(pollo_extra.id),
            },
            # Preferencia sin costo: no nombra producto.
            {"option_group": "nota", "option_name": "sin palta"},
        ],
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["items_total"] == "40.00"  # 33 + 7
    assert body["total"] == "45.00"
    opciones = body["items"][0]["options"]
    assert {o["option_name"]: o["price_delta"] for o in opciones} == {
        "Filete de pollo": "7.00",
        "sin palta": "0.00",
    }


@pytest.mark.anyio
async def test_precio_en_el_request_no_cambia_nada(
    client: AsyncClient, bot_headers, zona, energy_bowl
):
    """Mandar importes inventados no los hace entrar: no existe ese campo."""
    payload = _order_payload(energy_bowl.id, quantity=2)
    payload["items"][0]["unit_price"] = "1.00"
    payload["total"] = "1.00"
    payload["delivery_fee"] = "0.00"

    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["total"] == "71.00"


@pytest.mark.anyio
async def test_producto_sin_precio_se_rechaza(
    client: AsyncClient, bot_headers, zona, db_session, owner_user
):
    sin_precio = _make_product(
        db_session, owner_user, f"BOWL SIN PRECIO {uuid.uuid4().hex[:4]}", None
    )
    resp = await client.post(
        ORDERS_URL, json=_order_payload(sin_precio.id), headers=bot_headers
    )
    assert resp.status_code == 400
    assert "sale price" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_distrito_sin_cobertura_se_rechaza(
    client: AsyncClient, bot_headers, zona, energy_bowl
):
    resp = await client.post(
        ORDERS_URL,
        json=_order_payload(energy_bowl.id, district="Los Olivos"),
        headers=bot_headers,
    )
    assert resp.status_code == 400
    assert "coverage" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tarifas
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cotiza_ignorando_tildes_y_mayusculas(
    client: AsyncClient, bot_headers, db_session, owner_user
):
    db_session.add(
        DeliveryZone(
            id=uuid.uuid4(),
            district="Jesús María",
            fee=Decimal("5.00"),
            is_active=True,
            created_by=owner_user.id,
        )
    )
    db_session.flush()
    resp = await client.get(
        f"{ZONES_URL}/quote", params={"district": "jesus maria"}, headers=bot_headers
    )
    assert resp.status_code == 200
    assert resp.json() == {"district": "Jesús María", "covered": True, "fee": "5.00"}


@pytest.mark.anyio
async def test_distrito_sin_cobertura_responde_200_no_404(
    client: AsyncClient, bot_headers, zona
):
    """"No repartimos ahi" es una respuesta de negocio, no una falla tecnica."""
    resp = await client.get(
        f"{ZONES_URL}/quote", params={"district": "Los Olivos"}, headers=bot_headers
    )
    assert resp.status_code == 200
    assert resp.json()["covered"] is False
    assert resp.json()["fee"] is None


# ---------------------------------------------------------------------------
# El limite: cobrar si, firmar no
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_pago_del_asistente_nace_pendiente(
    client: AsyncClient, bot_headers, zona, energy_bowl
):
    order = (
        await client.post(
            ORDERS_URL, json=_order_payload(energy_bowl.id), headers=bot_headers
        )
    ).json()
    resp = await client.post(
        f"{ORDERS_URL}/{order['id']}/payments",
        json={"method": "yape", "amount": "71.00", "proof_url": "/fotos/yape1.jpg"},
        headers=bot_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"
    assert resp.json()["verified_at"] is None


@pytest.mark.anyio
async def test_el_asistente_no_puede_firmar_un_pago(
    client: AsyncClient, bot_headers, zona, energy_bowl
):
    """EL TEST QUE IMPORTA. Un token del asistente no puede darse por pagado."""
    order = (
        await client.post(
            ORDERS_URL, json=_order_payload(energy_bowl.id), headers=bot_headers
        )
    ).json()
    payment = (
        await client.post(
            f"{ORDERS_URL}/{order['id']}/payments",
            json={"method": "yape", "amount": "71.00"},
            headers=bot_headers,
        )
    ).json()

    resp = await client.post(
        f"/api/v1/payments/{payment['id']}/verify", headers=bot_headers
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_el_asistente_tampoco_llega_actuando_como_owner(
    client: AsyncClient, db_session, owner_user
):
    """El atajo obvio tambien esta cerrado.

    Un service token que nombra a un owner en X-Act-As no obtiene sus permisos:
    ACT_AS_ALLOWED_ROLES no incluye owner, y ese camino devuelve 401 generico —
    no un 403, que le confirmaria al atacante que el correo existe y es de owner.
    """
    _, token = create_service_principal(db_session, name=f"wa-{uuid.uuid4().hex[:6]}")
    resp = await client.get(MENU_URL, headers=svc_headers(token, owner_user.email))
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_el_owner_si_firma(
    client: AsyncClient, bot_headers, owner_token, zona, energy_bowl, db_session
):
    order = (
        await client.post(
            ORDERS_URL, json=_order_payload(energy_bowl.id), headers=bot_headers
        )
    ).json()
    payment = (
        await client.post(
            f"{ORDERS_URL}/{order['id']}/payments",
            json={"method": "yape", "amount": "71.00"},
            headers=bot_headers,
        )
    ).json()

    resp = await client.post(
        f"/api/v1/payments/{payment['id']}/verify", headers=_auth(owner_token)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "verified"
    assert resp.json()["verified_at"] is not None

    row = db_session.get(Payment, uuid.UUID(payment["id"]))
    db_session.refresh(row)
    assert row.verified_by is not None


@pytest.mark.anyio
async def test_el_cocinero_no_toma_pedidos(
    client: AsyncClient, cocinero_token, zona, energy_bowl
):
    """Un cocinero captura lo que sale de la cocina; no vende."""
    resp = await client.post(
        ORDERS_URL, json=_order_payload(energy_bowl.id), headers=_auth(cocinero_token)
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Cliente y carta
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_telefono_es_la_cuenta(
    client: AsyncClient, bot_headers, zona, energy_bowl
):
    """Dos pedidos del mismo numero son el mismo cliente, no dos."""
    first = await client.post(
        ORDERS_URL, json=_order_payload(energy_bowl.id), headers=bot_headers
    )
    second = await client.post(
        ORDERS_URL, json=_order_payload(energy_bowl.id), headers=bot_headers
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["customer_phone"] == second.json()["customer_phone"] == "+51966497671"
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.anyio
async def test_el_telefono_se_normaliza_con_el_prefijo(
    client: AsyncClient, bot_headers, zona, energy_bowl
):
    """Meta rechaza con (#131009) todo destinatario sin +; se agrega al entrar."""
    payload = _order_payload(energy_bowl.id)
    payload["customer"]["phone"] = "51966497671"
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["customer_phone"] == "+51966497671"


@pytest.mark.anyio
async def test_la_carta_esconde_lo_que_no_puede_cotizar(
    client: AsyncClient, bot_headers, db_session, owner_user, energy_bowl
):
    _make_product(db_session, owner_user, f"BOWL MUDO {uuid.uuid4().hex[:4]}", None)
    resp = await client.get(MENU_URL, headers=bot_headers)
    assert resp.status_code == 200
    nombres = {item["name"] for item in resp.json()}
    assert energy_bowl.name in nombres
    assert not any(n.startswith("BOWL MUDO") for n in nombres)


@pytest.mark.anyio
async def test_la_carta_no_lista_modificadores_gratis(
    client: AsyncClient, bot_headers, db_session, owner_user, energy_bowl
):
    """Una salsa incluida vale 0 y NO es un plato.

    Lleva precio 0 (y no NULL) porque una opcion que nombra un producto exige
    que ese producto tenga precio. Pero en la carta seria "Vinagreta, S/ 0",
    que el asistente ofreceria como si fuera un plato gratis.
    """
    salsa = _make_product(db_session, owner_user, f"VINAGRETA {uuid.uuid4().hex[:4]}", "0.00")
    resp = await client.get(MENU_URL, headers=bot_headers)
    assert resp.status_code == 200
    nombres = {item["name"] for item in resp.json()}
    assert energy_bowl.name in nombres
    assert salsa.name not in nombres


@pytest.mark.anyio
async def test_la_salsa_gratis_igual_sirve_como_opcion(
    client: AsyncClient, bot_headers, zona, energy_bowl, db_session, owner_user
):
    """Fuera de la carta, pero utilizable como modificador y sumando 0."""
    salsa = _make_product(db_session, owner_user, f"SALSA PALTA {uuid.uuid4().hex[:4]}", "0.00")
    payload = _order_payload(
        energy_bowl.id,
        quantity=1,
        options=[
            {
                "option_group": "salsa",
                "option_name": "Salsa de palta proteica",
                "product_id": str(salsa.id),
            }
        ],
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["items_total"] == "33.00"
    assert resp.json()["items"][0]["options"][0]["price_delta"] == "0.00"
