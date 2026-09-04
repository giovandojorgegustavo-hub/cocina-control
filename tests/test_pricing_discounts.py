"""Integration tests de precios, descuentos por plato y promociones.

La propiedad que se prueba aca es la continuacion de la de test_sales_orders:
**el cliente no manda importes, y un descuento tampoco lo es**. Lo unico que
viaja es un codigo; el servidor decide si aplica y cuanto vale. Un token del
asistente no puede inventarse un descuento, y un cliente que ya compro no puede
volver a cobrar el de primera compra cambiando de conversacion.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.delivery_zone import DeliveryZone
from cocina_control.models.product import Product
from cocina_control.models.promotion import Promotion

from .conftest import create_test_user
from .test_sales_orders import MENU_URL, ORDERS_URL, _auth, _make_product, _order_payload
from .test_service_principals import create_service_principal, svc_headers

PROMOS_URL = "/api/v1/promotions"
CATALOG_PROMOS_URL = "/api/v1/catalog/promotions"


def _pricing_url(product_id) -> str:
    return f"/api/v1/products/{product_id}/pricing"


# ---------------------------------------------------------------------------
# Fixtures — las mismas que test_sales_orders; pytest no comparte fixtures
# entre modulos salvo por conftest, y no vale la pena moverlas por dos tests.
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


@pytest.fixture
def energy_bowl(db_session: Session, owner_user) -> Product:
    return _make_product(db_session, owner_user, f"ENERGY BOWL {uuid.uuid4().hex[:4]}", "33.00")


@pytest.fixture
def pollo_extra(db_session: Session, owner_user) -> Product:
    return _make_product(db_session, owner_user, f"FILETE POLLO {uuid.uuid4().hex[:4]}", "7.00")


@pytest.fixture
def primera_compra(db_session: Session) -> Promotion:
    """La promo sembrada por la migracion 0022, en su estado de fabrica."""
    promo = db_session.get(Promotion, "primera_compra")
    assert promo is not None, "la migracion 0022 debe sembrar primera_compra"
    promo.percent = Decimal("15.00")
    promo.first_order_only = True
    promo.is_active = True
    db_session.flush()
    return promo


# ---------------------------------------------------------------------------
# Carta: precio de lista y precio final
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_la_carta_muestra_el_precio_final(
    client: AsyncClient, bot_headers, db_session, owner_user, energy_bowl
):
    energy_bowl.discount_percent = Decimal("10.00")
    db_session.flush()

    resp = await client.get(MENU_URL, headers=bot_headers)
    assert resp.status_code == 200
    item = next(i for i in resp.json() if i["id"] == str(energy_bowl.id))
    assert item["sale_price"] == "33.00"
    assert item["discount_percent"] == "10.00"
    assert item["final_price"] == "29.70"


@pytest.mark.anyio
async def test_sin_descuento_la_carta_dice_cero(
    client: AsyncClient, bot_headers, energy_bowl
):
    """NULL en la base sale como "0.00": el bot no tiene que tratar dos casos."""
    resp = await client.get(MENU_URL, headers=bot_headers)
    item = next(i for i in resp.json() if i["id"] == str(energy_bowl.id))
    assert item["discount_percent"] == "0.00"
    assert item["final_price"] == item["sale_price"] == "33.00"


# ---------------------------------------------------------------------------
# PATCH /products/{id}/pricing
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_admin_cambia_precio_y_descuento(
    client: AsyncClient, admin_token, energy_bowl
):
    resp = await client.patch(
        _pricing_url(energy_bowl.id),
        json={"sale_price": "35.00", "discount_percent": "20"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sale_price"] == "35.00"
    assert body["discount_percent"] == "20.00"


@pytest.mark.anyio
async def test_el_precio_nuevo_llega_a_la_lista_de_productos(
    client: AsyncClient, owner_token, energy_bowl
):
    await client.patch(
        _pricing_url(energy_bowl.id),
        json={"discount_percent": "5"},
        headers=_auth(owner_token),
    )
    resp = await client.get("/api/v1/products", params={"flow": "sale"}, headers=_auth(owner_token))
    assert resp.status_code == 200
    item = next(p for p in resp.json() if p["id"] == str(energy_bowl.id))
    assert item["sale_price"] == "33.00"
    assert item["discount_percent"] == "5.00"


@pytest.mark.anyio
async def test_el_cocinero_no_toca_precios(
    client: AsyncClient, cocinero_token, energy_bowl
):
    resp = await client.patch(
        _pricing_url(energy_bowl.id),
        json={"sale_price": "1.00"},
        headers=_auth(cocinero_token),
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_el_asistente_tampoco_toca_precios(
    client: AsyncClient, bot_headers, energy_bowl
):
    """Quien vende no fija el precio: un token filtrado no rebaja la carta."""
    resp = await client.patch(
        _pricing_url(energy_bowl.id),
        json={"sale_price": "1.00"},
        headers=bot_headers,
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_descuento_de_cien_se_rechaza(
    client: AsyncClient, admin_token, energy_bowl
):
    """100 % es un regalo, se carga como precio 0; no es un descuento."""
    resp = await client.patch(
        _pricing_url(energy_bowl.id),
        json={"discount_percent": "100"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_un_insumo_no_tiene_precio_de_venta(
    client: AsyncClient, admin_token, db_session, owner_user
):
    insumo = Product(
        id=uuid.uuid4(),
        name=f"HARINA {uuid.uuid4().hex[:4]}",
        unit="kg",
        is_active=True,
        is_purchase=True,
        is_sale=False,
        created_by=owner_user.id,
    )
    db_session.add(insumo)
    db_session.flush()
    resp = await client.patch(
        _pricing_url(insumo.id), json={"sale_price": "10.00"}, headers=_auth(admin_token)
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_body_vacio_se_rechaza(client: AsyncClient, admin_token, energy_bowl):
    resp = await client.patch(
        _pricing_url(energy_bowl.id), json={}, headers=_auth(admin_token)
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# El pedido cobra el precio final
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_pedido_usa_el_precio_con_descuento(
    client: AsyncClient, bot_headers, zona, db_session, energy_bowl
):
    energy_bowl.discount_percent = Decimal("10.00")
    db_session.flush()

    resp = await client.post(
        ORDERS_URL, json=_order_payload(energy_bowl.id, quantity=2), headers=bot_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # 33 - 10 % = 29.70; x2 = 59.40; + 5 de reparto.
    assert body["items"][0]["unit_price"] == "29.70"
    assert body["items_total"] == "59.40"
    assert body["discount_amount"] == "0.00"
    assert body["promo_code"] is None
    assert body["total"] == "64.40"


@pytest.mark.anyio
async def test_el_extra_tambien_lleva_su_descuento(
    client: AsyncClient, bot_headers, zona, db_session, energy_bowl, pollo_extra
):
    pollo_extra.discount_percent = Decimal("50.00")
    db_session.flush()
    payload = _order_payload(
        energy_bowl.id,
        quantity=1,
        options=[
            {
                "option_group": "proteina-extra",
                "option_name": "Filete de pollo",
                "product_id": str(pollo_extra.id),
            }
        ],
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["items"][0]["options"][0]["price_delta"] == "3.50"
    assert resp.json()["items_total"] == "36.50"


# ---------------------------------------------------------------------------
# Promo de primera compra
# ---------------------------------------------------------------------------


def _payload_con_promo(product_id, phone="+51966497671", **kwargs):
    payload = _order_payload(product_id, **kwargs)
    payload["customer"]["phone"] = phone
    payload["promo_code"] = "primera_compra"
    return payload


@pytest.mark.anyio
async def test_primera_compra_descuenta_el_quince(
    client: AsyncClient, bot_headers, zona, energy_bowl, primera_compra
):
    phone = f"+5199{uuid.uuid4().int % 10**7:07d}"
    resp = await client.post(
        ORDERS_URL, json=_payload_con_promo(energy_bowl.id, phone=phone), headers=bot_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # 2 x 33 = 66; 15 % = 9.90; 66 - 9.90 + 5 = 61.10.
    assert body["items_total"] == "66.00"
    assert body["discount_percent"] == "15.00"
    assert body["discount_amount"] == "9.90"
    assert body["promo_code"] == "primera_compra"
    assert body["delivery_fee"] == "5.00"
    assert body["total"] == "61.10"


@pytest.mark.anyio
async def test_la_segunda_compra_no_lleva_la_promo(
    client: AsyncClient, bot_headers, zona, energy_bowl, primera_compra
):
    phone = f"+5198{uuid.uuid4().int % 10**7:07d}"
    first = await client.post(
        ORDERS_URL, json=_payload_con_promo(energy_bowl.id, phone=phone), headers=bot_headers
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        ORDERS_URL, json=_payload_con_promo(energy_bowl.id, phone=phone), headers=bot_headers
    )
    assert second.status_code == 400
    assert (
        second.json()["detail"]
        == "El descuento de primera compra ya fue usado por este cliente."
    )


@pytest.mark.anyio
async def test_un_pedido_previo_sin_promo_tambien_cuenta(
    client: AsyncClient, bot_headers, zona, energy_bowl, primera_compra
):
    """Primera compra es la primera compra, no el primer uso del codigo."""
    phone = f"+5197{uuid.uuid4().int % 10**7:07d}"
    payload = _order_payload(energy_bowl.id)
    payload["customer"]["phone"] = phone
    first = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert first.status_code == 201, first.text

    second = await client.post(
        ORDERS_URL, json=_payload_con_promo(energy_bowl.id, phone=phone), headers=bot_headers
    )
    assert second.status_code == 400


@pytest.mark.anyio
async def test_promo_apagada_se_rechaza(
    client: AsyncClient, bot_headers, zona, energy_bowl, db_session, primera_compra
):
    primera_compra.is_active = False
    db_session.flush()
    resp = await client.post(
        ORDERS_URL, json=_payload_con_promo(energy_bowl.id), headers=bot_headers
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Promoción no vigente."


@pytest.mark.anyio
async def test_codigo_desconocido_se_rechaza(
    client: AsyncClient, bot_headers, zona, energy_bowl
):
    payload = _order_payload(energy_bowl.id)
    payload["promo_code"] = "no_existe"
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Promoción no encontrada."


@pytest.mark.anyio
async def test_el_importe_del_descuento_no_viaja(
    client: AsyncClient, bot_headers, zona, energy_bowl
):
    """Mandar discount_amount no lo hace entrar: no existe ese campo."""
    payload = _order_payload(energy_bowl.id)
    payload["discount_amount"] = "60.00"
    payload["discount_percent"] = "90"
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["discount_amount"] == "0.00"
    assert resp.json()["total"] == "71.00"


# ---------------------------------------------------------------------------
# Promociones: lo que ve el bot y lo que edita el dueno
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_catalogo_solo_lista_promos_vigentes(
    client: AsyncClient, bot_headers, db_session, owner_user, primera_compra
):
    apagada = Promotion(
        code=f"vieja_{uuid.uuid4().hex[:6]}",
        name="Promo vieja",
        percent=Decimal("10.00"),
        first_order_only=False,
        is_active=False,
    )
    db_session.add(apagada)
    db_session.flush()

    resp = await client.get(CATALOG_PROMOS_URL, headers=bot_headers)
    assert resp.status_code == 200
    codes = {p["code"] for p in resp.json()}
    assert "primera_compra" in codes
    assert apagada.code not in codes
    vigente = next(p for p in resp.json() if p["code"] == "primera_compra")
    assert vigente == {
        "code": "primera_compra",
        "name": "Descuento de primera compra",
        "percent": "15.00",
        "first_order_only": True,
    }


@pytest.mark.anyio
async def test_el_owner_edita_la_promo(
    client: AsyncClient, owner_token, primera_compra
):
    resp = await client.patch(
        f"{PROMOS_URL}/primera_compra",
        json={"percent": "20"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["percent"] == "20.00"
    assert body["is_active"] is True
    assert body["updated_at"] is not None

    listed = await client.get(PROMOS_URL, headers=_auth(owner_token))
    assert listed.status_code == 200
    assert any(p["code"] == "primera_compra" and p["percent"] == "20.00" for p in listed.json())


@pytest.mark.anyio
async def test_el_cocinero_no_edita_promos(
    client: AsyncClient, cocinero_token, primera_compra
):
    resp = await client.patch(
        f"{PROMOS_URL}/primera_compra",
        json={"percent": "99"},
        headers=_auth(cocinero_token),
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_el_asistente_lee_pero_no_edita_promos(
    client: AsyncClient, bot_headers, primera_compra
):
    assert (await client.get(PROMOS_URL, headers=bot_headers)).status_code == 403
    resp = await client.patch(
        f"{PROMOS_URL}/primera_compra", json={"percent": "99"}, headers=bot_headers
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_promo_desconocida_da_404(client: AsyncClient, owner_token):
    resp = await client.patch(
        f"{PROMOS_URL}/no_existe", json={"percent": "5"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 404
