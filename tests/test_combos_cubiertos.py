"""Integration tests de los combos elegibles y los cubiertos (migracion 0024).

La propiedad que se prueba aca: **un combo se arma eligiendo el bowl/wrap ya
hecho y la bebida, no escribiendolos como texto; y cualquier plato puede sumar
cubiertos opcionales a S/1 cada uno, hasta dos**.

La primera mitad mira la carta y un pedido con el `client` normal: los grupos
que 0024 sembro existen en la base de tests aunque los platos no, asi que se
crea un Combo Office a mano, se le asignan esos grupos y se comprueba lo que ve
el asistente. La segunda mitad corre un ciclo de Alembic con los productos
presentes — el estado de produccion — para probar la siembra de verdad: que los
cubiertos se apendean a cada plato y que "Elige tu bowl" enlaza los bowls por
nombre.
"""

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.delivery_zone import DeliveryZone
from cocina_control.models.product import Product

from .conftest import create_test_user
from .test_sales_orders import (
    MENU_URL,
    ORDERS_URL,
    _auth,
    _make_product,
    _order_payload,
)
from .test_service_principals import create_service_principal, svc_headers

GROUPS_URL = "/api/v1/option-groups"


def _product_groups_url(product_id) -> str:
    return f"/api/v1/products/{product_id}/option-groups"


# ---------------------------------------------------------------------------
# Fixtures — pytest no comparte fixtures entre modulos salvo por conftest.
# ---------------------------------------------------------------------------


@pytest.fixture
def asistente_user(db_session: Session):
    return create_test_user(db_session, "asistente_pedidos", f"bot-{uuid.uuid4().hex[:6]}@test.com")


@pytest.fixture
def bot_headers(db_session: Session, asistente_user) -> dict[str, str]:
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


def _combo(db_session: Session, owner, name: str, price: str) -> Product:
    """Un combo como en produccion: precio de lista de Rappi con el -30 %."""
    product = _make_product(db_session, owner, name, price)
    product.discount_percent = Decimal("30.00")
    db_session.flush()
    return product


async def _seeded_group_ids(client: AsyncClient, owner_token: str) -> dict[str, str]:
    resp = await client.get(GROUPS_URL, params={"all": "true"}, headers=_auth(owner_token))
    assert resp.status_code == 200, resp.text
    return {g["name"]: g["id"] for g in resp.json()}


# ---------------------------------------------------------------------------
# La carta: el combo ofrece elegir
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_combo_office_ofrece_bowl_bebida_y_cubiertos(
    client: AsyncClient, owner_token, bot_headers, db_session, owner_user
):
    combo = _combo(db_session, owner_user, f"COMBO OFFICE {uuid.uuid4().hex[:4]}", "54.00")
    by_name = await _seeded_group_ids(client, owner_token)
    wanted = ["Elige tu bowl", "Bebida", "Cubiertos"]

    resp = await client.put(
        _product_groups_url(combo.id),
        json={"group_ids": [by_name[n] for n in wanted]},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get(MENU_URL, headers=bot_headers)
    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json() if i["id"] == str(combo.id))
    # El -30 % ya aplicado: el precio del combo cubre el bowl y la bebida.
    assert item["final_price"] == "37.80"
    assert [g["name"] for g in item["option_groups"]] == wanted

    bowl = next(g for g in item["option_groups"] if g["name"] == "Elige tu bowl")
    assert bowl["required"] is True
    assert (bowl["selection"], bowl["min_choices"], bowl["max_choices"]) == ("single", 1, 1)
    # Los bowls ya armados, a 0.00: el combo ya los cubre.
    assert {o["name"]: o["price"] for o in bowl["options"]} == {
        "Focus Bowl": "0.00",
        "Energy Bowl": "0.00",
    }

    bebida = next(g for g in item["option_groups"] if g["name"] == "Bebida")
    assert bebida["required"] is True
    assert "Maracuyá refrescante 12 oz" in {o["name"] for o in bebida["options"]}

    cubiertos = next(g for g in item["option_groups"] if g["name"] == "Cubiertos")
    # La unica excepcion opcional: sin cubiertos no bloquea el pedido.
    assert cubiertos["required"] is False
    assert (cubiertos["min_choices"], cubiertos["max_choices"]) == (0, 1)
    assert {o["name"]: o["price"] for o in cubiertos["options"]} == {
        "Sin cubiertos": "0.00",
        "1 cubierto": "1.00",
        "2 cubiertos": "2.00",
    }


@pytest.mark.anyio
async def test_el_combo_double_ofrece_los_cuatro_picks(
    client: AsyncClient, owner_token, bot_headers, db_session, owner_user
):
    combo = _combo(db_session, owner_user, f"COMBO DOUBLE {uuid.uuid4().hex[:4]}", "110.00")
    by_name = await _seeded_group_ids(client, owner_token)
    wanted = ["Primer bowl", "Segundo bowl", "Primera bebida", "Segunda bebida", "Cubiertos"]

    resp = await client.put(
        _product_groups_url(combo.id),
        json={"group_ids": [by_name[n] for n in wanted]},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get(MENU_URL, headers=bot_headers)
    item = next(i for i in resp.json() if i["id"] == str(combo.id))
    assert [g["name"] for g in item["option_groups"]] == wanted
    # Cada pick es su propio grupo obligatorio de uno: dos bowls y dos bebidas.
    for name in wanted[:-1]:
        group = next(g for g in item["option_groups"] if g["name"] == name)
        assert (group["required"], group["min_choices"], group["max_choices"]) == (True, 1, 1)


# ---------------------------------------------------------------------------
# El pedido: los cubiertos suman, el bowl y la bebida no
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_pedido_de_combo_office_suma_los_cubiertos(
    client: AsyncClient, owner_token, bot_headers, zona, db_session, owner_user
):
    combo = _combo(db_session, owner_user, f"COMBO OFFICE {uuid.uuid4().hex[:4]}", "54.00")
    by_name = await _seeded_group_ids(client, owner_token)
    wanted = ["Elige tu bowl", "Bebida", "Cubiertos"]
    await client.put(
        _product_groups_url(combo.id),
        json={"group_ids": [by_name[n] for n in wanted]},
        headers=_auth(owner_token),
    )

    # Los ids de opcion se leen de la misma carta que ve el asistente.
    item = next(
        i
        for i in (await client.get(MENU_URL, headers=bot_headers)).json()
        if i["id"] == str(combo.id)
    )

    def option_id(group_name: str, option_name: str) -> str:
        group = next(g for g in item["option_groups"] if g["name"] == group_name)
        return next(o["id"] for o in group["options"] if o["name"] == option_name)

    payload = _order_payload(
        combo.id,
        quantity=1,
        options=[
            {"option_item_id": option_id("Elige tu bowl", "Focus Bowl")},
            {"option_item_id": option_id("Bebida", "Maracuyá refrescante 12 oz")},
            {"option_item_id": option_id("Cubiertos", "1 cubierto")},
        ],
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # 37.80 del combo (con su -30 %) + 1.00 del cubierto; bowl y bebida a 0.
    assert body["items_total"] == "38.80"
    deltas = {o["option_name"]: o["price_delta"] for o in body["items"][0]["options"]}
    assert deltas == {
        "Focus Bowl": "0.00",
        "Maracuyá refrescante 12 oz": "0.00",
        "1 cubierto": "1.00",
    }


@pytest.mark.anyio
async def test_los_cubiertos_no_son_obligatorios(
    client: AsyncClient, owner_token, bot_headers, zona, db_session, owner_user
):
    """El plato entra sin elegir cubiertos: el grupo no obliga."""
    combo = _combo(db_session, owner_user, f"COMBO OFFICE {uuid.uuid4().hex[:4]}", "54.00")
    by_name = await _seeded_group_ids(client, owner_token)
    await client.put(
        _product_groups_url(combo.id),
        json={"group_ids": [by_name[n] for n in ("Elige tu bowl", "Bebida", "Cubiertos")]},
        headers=_auth(owner_token),
    )
    item = next(
        i
        for i in (await client.get(MENU_URL, headers=bot_headers)).json()
        if i["id"] == str(combo.id)
    )

    def option_id(group_name: str, option_name: str) -> str:
        group = next(g for g in item["option_groups"] if g["name"] == group_name)
        return next(o["id"] for o in group["options"] if o["name"] == option_name)

    payload = _order_payload(
        combo.id,
        quantity=1,
        options=[
            {"option_item_id": option_id("Elige tu bowl", "Energy Bowl")},
            {"option_item_id": option_id("Bebida", "Maracuyá refrescante 12 oz")},
        ],
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["items_total"] == "37.80"


# ---------------------------------------------------------------------------
# La siembra de verdad: un ciclo de Alembic con los platos presentes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_la_migracion_asigna_cubiertos_y_enlaza_los_bowls(postgres_url: str, db_engine):
    """Ciclo propio de Alembic con los productos presentes — como produccion.

    En la base de tests recien creada no hay platos, asi que la siembra de 0024
    crea los grupos pero no asigna nada. Aca se baja a 0022, se insertan un
    owner y los bowls/bebida reales, y se sube a head: 0023 asigna sus grupos y
    crea los combos, y 0024 apendea los cubiertos y los picks. Se comprueba que
    los cubiertos quedan al FINAL del orden de cada plato y que "Elige tu bowl"
    enlaza los bowls por nombre.

    El ciclo corre sobre la base compartida y se limpia al final: los bowls
    quedan referenciados por option_items (product_id es RESTRICT), asi que
    primero se sueltan esos enlaces y despues se borran los productos, los
    combos y el owner, para que el resto de la suite no cuente de mas.
    """
    from alembic import command
    from alembic.config import Config

    from cocina_control.db import build_engine

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    engine = build_engine(postgres_url)

    owner_id = uuid.uuid4()
    focus_id = uuid.uuid4()
    energy_id = uuid.uuid4()
    bebida_id = uuid.uuid4()
    my_products = (focus_id, energy_id, bebida_id)
    combo_names = ("COMBO OFFICE", "COMBO WRAPPER", "COMBO DOUBLE")

    insert_product = sa.text(
        "INSERT INTO products (id, name, unit, is_active, is_purchase, is_sale, "
        "sale_price, created_by) "
        "VALUES (:id, :name, 'un', true, false, true, :price, :owner)"
    )

    def groups_of(conn, product_id):
        return [
            r.name
            for r in conn.execute(
                sa.text(
                    "SELECT og.name FROM product_option_groups pog "
                    "JOIN option_groups og ON og.id = pog.group_id "
                    "WHERE pog.product_id = :pid ORDER BY pog.sort_order"
                ),
                {"pid": product_id},
            ).all()
        ]

    try:
        command.downgrade(cfg, "0022_precios_descuentos")
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, name, email, password_hash, role) "
                    "VALUES (:id, 'Dueño', :email, 'x', 'owner')"
                ),
                {"id": owner_id, "email": f"owner-seed-{uuid.uuid4().hex[:6]}@test.com"},
            )
            conn.execute(
                insert_product,
                {"id": focus_id, "name": "Focus Bowl", "price": "30.00", "owner": owner_id},
            )
            conn.execute(
                insert_product,
                {"id": energy_id, "name": "Energy Bowl", "price": "32.00", "owner": owner_id},
            )
            conn.execute(
                insert_product,
                {
                    "id": bebida_id,
                    "name": "Maracuyá refrescante 12 oz",
                    "price": "8.00",
                    "owner": owner_id,
                },
            )
        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            # Los cubiertos se apendean al final de lo que 0023 ya asigno.
            focus_groups = groups_of(conn, focus_id)
            assert focus_groups == ["Proteína extra", "Salsa", "Adicionales", "Cubiertos"]
            assert groups_of(conn, energy_id)[-1] == "Cubiertos"

            # "Elige tu bowl" enlaza los bowls por nombre; "Bebida" la bebida.
            links = {
                r.name: r.product_id
                for r in conn.execute(
                    sa.text(
                        "SELECT oi.name, oi.product_id FROM option_items oi "
                        "JOIN option_groups og ON og.id = oi.group_id "
                        "WHERE og.name IN ('Elige tu bowl', 'Primer bowl', 'Bebida')"
                    )
                ).all()
                if r.name in ("Focus Bowl", "Energy Bowl", "Maracuyá refrescante 12 oz")
            }
            assert links["Focus Bowl"] == focus_id
            assert links["Energy Bowl"] == energy_id
            assert links["Maracuyá refrescante 12 oz"] == bebida_id

            # El Combo Office recibe sus picks despues de los grupos de 0023.
            combo_office_id = conn.execute(
                sa.text("SELECT id FROM products WHERE name = 'COMBO OFFICE'")
            ).scalar()
            assert groups_of(conn, combo_office_id) == [
                "Proteína extra",
                "Salsa",
                "Adicionales",
                "Elige tu bowl",
                "Bebida",
                "Cubiertos",
            ]
            combo_double_id = conn.execute(
                sa.text("SELECT id FROM products WHERE name = 'COMBO DOUBLE'")
            ).scalar()
            assert groups_of(conn, combo_double_id)[-5:] == [
                "Primer bowl",
                "Segundo bowl",
                "Primera bebida",
                "Segunda bebida",
                "Cubiertos",
            ]
    finally:
        with engine.begin() as conn:
            # option_items apunta a los bowls con RESTRICT: soltar antes de borrar.
            conn.execute(
                sa.text(
                    "UPDATE option_items SET product_id = NULL WHERE product_id IN :ids"
                ).bindparams(sa.bindparam("ids", expanding=True)),
                {"ids": list(my_products)},
            )
            conn.execute(
                sa.text("DELETE FROM products WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"ids": list(my_products)},
            )
            conn.execute(
                sa.text("DELETE FROM products WHERE name IN :names").bindparams(
                    sa.bindparam("names", expanding=True)
                ),
                {"names": list(combo_names)},
            )
            conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": owner_id})
        engine.dispose()
