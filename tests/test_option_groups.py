"""Integration tests de los extras y opciones de plato (migracion 0023).

La propiedad que se prueba aca: **la lista de opciones de cada plato, con sus
precios, la edita el dueno desde el panel y el asistente la lee de la carta**.
Un cocinero no toca grupos; una opcion repetida no se duplica; un pedido que
elige "Filete de pollo" paga el +8 que dice el grupo y no otro; y las reglas
del grupo (una sola, hasta N, obligatorio) las hace cumplir el servidor, no el
bot.

La segunda mitad prueba la siembra: los diez grupos de carta.json y los tres
combos aparecen despues de la migracion, con los precios que Rappi publica.
"""

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.delivery_zone import DeliveryZone
from cocina_control.models.option_group import OptionGroup, OptionItem, ProductOptionGroup
from cocina_control.models.product import Product

from .conftest import create_test_user
from .test_sales_orders import MENU_URL, ORDERS_URL, _auth, _make_product, _order_payload
from .test_service_principals import create_service_principal, svc_headers

GROUPS_URL = "/api/v1/option-groups"
ITEMS_URL = "/api/v1/option-items"

# Los diez `catalogos` de carta.json, en su orden, con el nombre que les da la
# migracion (los `corto`, desambiguados).
SEEDED_GROUP_NAMES = [
    "Base",
    "Bases (elige 2)",
    "Base wrap",
    "Toppings (hasta 5)",
    "Toppings (hasta 6)",
    "Semilla",
    "Proteína",
    "Salsa",
    "Adicionales",
    "Proteína extra",
]


def _product_groups_url(product_id) -> str:
    return f"/api/v1/products/{product_id}/option-groups"


# ---------------------------------------------------------------------------
# Fixtures — las mismas que test_sales_orders; pytest no comparte fixtures
# entre modulos salvo por conftest.
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


def _make_group(
    session: Session,
    owner,
    name: str,
    *,
    selection: str = "multiple",
    required: bool = False,
    min_choices: int = 0,
    max_choices: int | None = None,
    items: list[tuple[str, str]] = (),
) -> tuple[OptionGroup, dict[str, OptionItem]]:
    group = OptionGroup(
        id=uuid.uuid4(),
        name=name,
        selection=selection,
        required=required,
        min_choices=min_choices,
        max_choices=1 if selection == "single" else max_choices,
        sort_order=0,
        is_active=True,
        created_by=owner.id,
    )
    session.add(group)
    session.flush()
    created: dict[str, OptionItem] = {}
    for position, (item_name, price) in enumerate(items):
        item = OptionItem(
            id=uuid.uuid4(),
            group_id=group.id,
            name=item_name,
            price=Decimal(price),
            sort_order=position,
            is_active=True,
        )
        session.add(item)
        created[item_name] = item
    session.flush()
    return group, created


def _assign(session: Session, product: Product, *groups: OptionGroup) -> None:
    for position, group in enumerate(groups):
        session.add(
            ProductOptionGroup(product_id=product.id, group_id=group.id, sort_order=position)
        )
    session.flush()


@pytest.fixture
def proteina_extra(db_session: Session, owner_user):
    """El grupo real de la carta: obligatorio, hasta 2, con "sin" a costo 0."""
    return _make_group(
        db_session,
        owner_user,
        f"Proteína extra {uuid.uuid4().hex[:4]}",
        selection="multiple",
        required=True,
        min_choices=1,
        max_choices=2,
        items=[("Sin proteína extra", "0"), ("Filete de pollo", "8.00"), ("Milanesa", "7.00")],
    )


@pytest.fixture
def base(db_session: Session, owner_user):
    return _make_group(
        db_session,
        owner_user,
        f"Base {uuid.uuid4().hex[:4]}",
        selection="single",
        required=True,
        min_choices=1,
        items=[("Camote", "0"), ("Quinua", "0")],
    )


def _structured(*items: OptionItem) -> list[dict]:
    return [{"option_item_id": str(item.id)} for item in items]


# ---------------------------------------------------------------------------
# La siembra: diez grupos, con sus reglas y precios
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_la_migracion_siembra_los_diez_grupos(client: AsyncClient, owner_token):
    resp = await client.get(GROUPS_URL, params={"all": "true"}, headers=_auth(owner_token))
    assert resp.status_code == 200, resp.text
    seeded = [g for g in resp.json() if g["name"] in SEEDED_GROUP_NAMES]
    assert [g["name"] for g in seeded] == SEEDED_GROUP_NAMES

    by_name = {g["name"]: g for g in seeded}
    base = by_name["Base"]
    assert (base["selection"], base["required"], base["min_choices"], base["max_choices"]) == (
        "single", True, 1, 1
    )
    bases = by_name["Bases (elige 2)"]
    assert (bases["selection"], bases["min_choices"], bases["max_choices"]) == ("multiple", 2, 2)
    adicionales = by_name["Adicionales"]
    assert (
        adicionales["required"],
        adicionales["min_choices"],
        adicionales["max_choices"],
    ) == (False, 0, 6)
    assert {i["name"]: i["price"] for i in adicionales["items"]} == {
        "Maracuyá refrescante 12 oz": "8.00",
        "Chucrut púrpura 4 oz": "8.00",
        "Mini Camote Burger": "15.00",
    }
    extra = by_name["Proteína extra"]
    assert (extra["selection"], extra["required"], extra["max_choices"]) == (
        "multiple", True, 2
    )
    assert [(i["name"], i["price"]) for i in extra["items"]] == [
        ("Sin proteína extra", "0.00"),
        ("200 gr Tilapia a la plancha", "8.00"),
        ("Milanesa", "7.00"),
        ("Filete de pollo", "7.00"),
        ("Filete de pollo en salsa BBQ ahumada", "8.00"),
    ]
    assert len(by_name["Toppings (hasta 5)"]["items"]) == 11
    assert by_name["Toppings (hasta 6)"]["max_choices"] == 6


@pytest.mark.anyio
async def test_arma_tu_bowl_lleva_sus_grupos_en_la_carta(
    client: AsyncClient, owner_token, bot_headers, db_session, owner_user
):
    """Los platos no existen en la base de tests: se crea Arma tu Bowl y se le
    asignan los grupos que carta.json le da, en su orden. La carta los expone."""
    bowl = _make_product(db_session, owner_user, f"ARMA TU BOWL {uuid.uuid4().hex[:4]}", "24.90")
    groups = (await client.get(GROUPS_URL, headers=_auth(owner_token))).json()
    by_name = {g["name"]: g for g in groups}
    wanted = ["Base", "Toppings (hasta 5)", "Proteína", "Proteína extra", "Salsa", "Adicionales"]

    resp = await client.put(
        _product_groups_url(bowl.id),
        json={"group_ids": [by_name[n]["id"] for n in wanted]},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200, resp.text
    assert [g["name"] for g in resp.json()] == wanted
    assert [g["sort_order"] for g in resp.json()] == list(range(len(wanted)))

    resp = await client.get(MENU_URL, headers=bot_headers)
    assert resp.status_code == 200
    item = next(i for i in resp.json() if i["id"] == str(bowl.id))
    assert [g["name"] for g in item["option_groups"]] == wanted
    proteina = next(g for g in item["option_groups"] if g["name"] == "Proteína")
    assert proteina["required"] is True and proteina["max_choices"] == 2
    assert {o["name"]: o["price"] for o in proteina["options"]}["Filete de pollo"] == "8.00"
    # Sin campos de administracion: el bot no necesita saber que esta apagado.
    assert set(proteina["options"][0]) == {"id", "name", "price"}


@pytest.mark.anyio
async def test_los_combos_se_crean_con_su_descuento(
    client: AsyncClient, db_session: Session, postgres_url: str
):
    """Ciclo propio de Alembic con un owner presente.

    products.created_by es NOT NULL, asi que la migracion solo crea los combos
    cuando hay a quien atribuirlos; en la subida inicial de conftest (base
    vacia) no los crea. Aca se baja a 0022, se inserta un owner y se vuelve a
    subir: es exactamente el estado de produccion. Se repite el ciclo para
    probar que no duplica y que completa el descuento cuando falta.

    El ciclo corre ANTES de tocar db_session: si la sesion de test ya hubiera
    insertado un usuario, el DROP de las FKs hacia users se quedaria esperando
    su transaccion. Los combos y el owner sembrado se borran al final porque
    quedan commiteados fuera del savepoint y el resto de la suite cuenta
    productos.
    """
    from alembic import command
    from alembic.config import Config

    from cocina_control.db import build_engine

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    engine = build_engine(postgres_url)
    seed_owner_id = uuid.uuid4()
    combo_names = ("COMBO OFFICE", "COMBO WRAPPER", "COMBO DOUBLE")

    def combos(conn):
        return conn.execute(
            sa.text(
                "SELECT name, sale_price, discount_percent, is_sale, is_purchase, unit "
                "FROM products WHERE name IN :names ORDER BY name"
            ).bindparams(sa.bindparam("names", expanding=True)),
            {"names": list(combo_names)},
        ).all()

    try:
        command.downgrade(cfg, "0022_precios_descuentos")
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, name, email, password_hash, role) "
                    "VALUES (:id, 'Dueño', :email, 'x', 'owner')"
                ),
                {"id": seed_owner_id, "email": f"owner-seed-{uuid.uuid4().hex[:6]}@test.com"},
            )
        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            rows = combos(conn)
            assert [(r.name, str(r.sale_price), str(r.discount_percent)) for r in rows] == [
                ("COMBO DOUBLE", "110.00", "30.00"),
                ("COMBO OFFICE", "54.00", "30.00"),
                ("COMBO WRAPPER", "51.00", "30.00"),
            ]
            assert all((r.is_sale, r.is_purchase, r.unit) == (True, False, "un") for r in rows)
            author = conn.execute(
                sa.text("SELECT DISTINCT created_by FROM products WHERE name IN :names")
                .bindparams(sa.bindparam("names", expanding=True)),
                {"names": list(combo_names)},
            ).scalars().all()
            assert author == [seed_owner_id]

        # Segundo ciclo: el downgrade deja los combos (son datos); la subida no
        # los duplica, y les repone el 30 % si alguien lo borro.
        command.downgrade(cfg, "0022_precios_descuentos")
        with engine.begin() as conn:
            assert len(combos(conn)) == 3
            conn.execute(
                sa.text("UPDATE products SET discount_percent = NULL WHERE name = 'COMBO OFFICE'")
            )
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            rows = combos(conn)
            assert len(rows) == 3
            assert {r.name: str(r.discount_percent) for r in rows}["COMBO OFFICE"] == "30.00"

        # Lo que ve el asistente: precio final con el -30 % y los grupos que
        # carta.json le da al Combo Office, en su orden.
        bot = create_test_user(
            db_session, "asistente_pedidos", f"bot-{uuid.uuid4().hex[:6]}@test.com"
        )
        _, token = create_service_principal(db_session, name=f"wa-{uuid.uuid4().hex[:6]}")
        resp = await client.get(MENU_URL, headers=svc_headers(token, bot.email))
        assert resp.status_code == 200, resp.text
        by_name = {i["name"]: i for i in resp.json()}
        assert by_name["COMBO OFFICE"]["final_price"] == "37.80"
        assert by_name["COMBO WRAPPER"]["final_price"] == "35.70"
        assert by_name["COMBO DOUBLE"]["final_price"] == "77.00"
        assert by_name["COMBO OFFICE"]["discount_percent"] == "30.00"
        assert [g["name"] for g in by_name["COMBO OFFICE"]["option_groups"]] == [
            "Proteína extra",
            "Salsa",
            "Adicionales",
        ]
    finally:
        with engine.begin() as conn:
            conn.execute(
                sa.text("DELETE FROM products WHERE name IN :names").bindparams(
                    sa.bindparam("names", expanding=True)
                ),
                {"names": list(combo_names)},
            )
            conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": seed_owner_id})
        engine.dispose()


# ---------------------------------------------------------------------------
# Grupos: alta, edicion, permisos
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_admin_crea_un_grupo(client: AsyncClient, admin_token):
    resp = await client.post(
        GROUPS_URL,
        json={"name": "  Salsa  ", "selection": "single", "required": True},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Salsa"
    # single => max 1; obligatorio sin minimo => min 1.
    assert (body["selection"], body["min_choices"], body["max_choices"]) == ("single", 1, 1)
    assert body["is_active"] is True and body["items"] == []
    uuid.UUID(body["id"])


@pytest.mark.anyio
async def test_el_cocinero_no_crea_grupos(client: AsyncClient, cocinero_token):
    resp = await client.post(
        GROUPS_URL, json={"name": "Salsa", "selection": "single"}, headers=_auth(cocinero_token)
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_el_asistente_no_lee_ni_edita_grupos(client: AsyncClient, bot_headers):
    """El bot lee la carta; el panel de opciones es del dueno."""
    assert (await client.get(GROUPS_URL, headers=bot_headers)).status_code == 403
    resp = await client.post(
        GROUPS_URL, json={"name": "Salsa", "selection": "single"}, headers=bot_headers
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_single_con_maximo_cinco_es_422(client: AsyncClient, owner_token):
    resp = await client.post(
        GROUPS_URL,
        json={"name": "Base", "selection": "single", "max_choices": 5},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_minimo_mayor_que_maximo_es_422(client: AsyncClient, owner_token):
    resp = await client.post(
        GROUPS_URL,
        json={"name": "Toppings", "selection": "multiple", "min_choices": 3, "max_choices": 2},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_el_owner_edita_un_grupo(
    client: AsyncClient, owner_token, owner_user, proteina_extra
):
    group, _ = proteina_extra
    resp = await client.patch(
        f"{GROUPS_URL}/{group.id}",
        json={"name": "Proteína extra", "max_choices": 3, "is_active": False},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Proteína extra"
    assert body["max_choices"] == 3
    assert body["is_active"] is False
    assert body["updated_at"] is not None
    assert [i["name"] for i in body["items"]] == [
        "Sin proteína extra",
        "Filete de pollo",
        "Milanesa",
    ]
    assert group.updated_by == owner_user.id


@pytest.mark.anyio
async def test_pasar_a_single_con_maximo_guardado_es_422(
    client: AsyncClient, owner_token, proteina_extra
):
    """La regla se evalua sobre el grupo mezclado, no sobre el body."""
    group, _ = proteina_extra
    resp = await client.patch(
        f"{GROUPS_URL}/{group.id}",
        json={"selection": "single", "max_choices": 2},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 422
    # Sin max explicito, pasar a single simplemente lo deja en 1.
    resp = await client.patch(
        f"{GROUPS_URL}/{group.id}", json={"selection": "single"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["max_choices"] == 1


@pytest.mark.anyio
async def test_un_grupo_inexistente_es_404(client: AsyncClient, owner_token):
    resp = await client.patch(
        f"{GROUPS_URL}/{uuid.uuid4()}", json={"name": "X"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_el_patch_vacio_es_422(client: AsyncClient, owner_token, proteina_extra):
    group, items = proteina_extra
    resp = await client.patch(f"{GROUPS_URL}/{group.id}", json={}, headers=_auth(owner_token))
    assert resp.status_code == 422
    resp = await client.patch(
        f"{ITEMS_URL}/{items['Milanesa'].id}", json={}, headers=_auth(owner_token)
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_sin_all_solo_se_ve_lo_activo(
    client: AsyncClient, owner_token, db_session, proteina_extra
):
    group, items = proteina_extra
    items["Milanesa"].is_active = False
    db_session.flush()

    resp = await client.get(GROUPS_URL, headers=_auth(owner_token))
    mine = next(g for g in resp.json() if g["id"] == str(group.id))
    assert [i["name"] for i in mine["items"]] == ["Sin proteína extra", "Filete de pollo"]

    resp = await client.get(GROUPS_URL, params={"all": "true"}, headers=_auth(owner_token))
    mine = next(g for g in resp.json() if g["id"] == str(group.id))
    assert {i["name"]: i["is_active"] for i in mine["items"]}["Milanesa"] is False

    group.is_active = False
    db_session.flush()
    resp = await client.get(GROUPS_URL, headers=_auth(owner_token))
    assert str(group.id) not in {g["id"] for g in resp.json()}


# ---------------------------------------------------------------------------
# Opciones: alta, duplicados, precio
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_el_admin_agrega_una_opcion_con_precio(
    client: AsyncClient, admin_token, proteina_extra
):
    group, _ = proteina_extra
    resp = await client.post(
        f"{GROUPS_URL}/{group.id}/items",
        json={"name": "Tilapia", "price": "8"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Tilapia"
    assert body["price"] == "8.00"
    assert body["product_id"] is None
    assert body["is_active"] is True


@pytest.mark.anyio
async def test_la_opcion_repetida_es_409(client: AsyncClient, owner_token, proteina_extra):
    group, items = proteina_extra
    resp = await client.post(
        f"{GROUPS_URL}/{group.id}/items",
        json={"name": "milanesa", "price": "7"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 409
    # Renombrar una opcion a otra que ya existe tampoco.
    resp = await client.patch(
        f"{ITEMS_URL}/{items['Filete de pollo'].id}",
        json={"name": "MILANESA"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 409
    # Renombrarse a si misma con otra caja no choca con su propia fila.
    resp = await client.patch(
        f"{ITEMS_URL}/{items['Milanesa'].id}",
        json={"name": "MILANESA"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.anyio
async def test_un_insumo_no_puede_ser_opcion(
    client: AsyncClient, owner_token, db_session, owner_user, proteina_extra
):
    group, _ = proteina_extra
    insumo = Product(
        id=uuid.uuid4(),
        name=f"POLLO CRUDO {uuid.uuid4().hex[:4]}",
        unit="kg",
        is_active=True,
        is_purchase=True,
        is_sale=False,
        created_by=owner_user.id,
    )
    db_session.add(insumo)
    db_session.flush()
    resp = await client.post(
        f"{GROUPS_URL}/{group.id}/items",
        json={"name": "Pollo", "price": "8", "product_id": str(insumo.id)},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_el_owner_cambia_el_precio_de_una_opcion(
    client: AsyncClient, owner_token, proteina_extra
):
    _, items = proteina_extra
    resp = await client.patch(
        f"{ITEMS_URL}/{items['Filete de pollo'].id}",
        json={"price": "9.5", "is_active": False},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price"] == "9.50"
    assert resp.json()["is_active"] is False


@pytest.mark.anyio
async def test_una_opcion_inexistente_es_404(client: AsyncClient, owner_token):
    resp = await client.patch(
        f"{ITEMS_URL}/{uuid.uuid4()}", json={"price": "1"}, headers=_auth(owner_token)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Asignacion plato -> grupos
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_la_asignacion_se_reemplaza_en_orden(
    client: AsyncClient, owner_token, energy_bowl, proteina_extra, base
):
    extra, _ = proteina_extra
    base_group, _ = base
    resp = await client.put(
        _product_groups_url(energy_bowl.id),
        json={"group_ids": [str(extra.id), str(base_group.id)]},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200, resp.text
    assert [g["group_id"] for g in resp.json()] == [str(extra.id), str(base_group.id)]

    resp = await client.put(
        _product_groups_url(energy_bowl.id),
        json={"group_ids": [str(base_group.id)]},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(_product_groups_url(energy_bowl.id), headers=_auth(owner_token))
    assert [(g["group_id"], g["sort_order"]) for g in resp.json()] == [(str(base_group.id), 0)]


@pytest.mark.anyio
async def test_un_grupo_desconocido_en_la_asignacion_es_400(
    client: AsyncClient, owner_token, energy_bowl
):
    resp = await client.put(
        _product_groups_url(energy_bowl.id),
        json={"group_ids": [str(uuid.uuid4())]},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_un_insumo_no_lleva_opciones(
    client: AsyncClient, owner_token, db_session, owner_user, base
):
    group, _ = base
    insumo = Product(
        id=uuid.uuid4(),
        name=f"LECHUGA {uuid.uuid4().hex[:4]}",
        unit="kg",
        is_active=True,
        is_purchase=True,
        is_sale=False,
        created_by=owner_user.id,
    )
    db_session.add(insumo)
    db_session.flush()
    resp = await client.put(
        _product_groups_url(insumo.id),
        json={"group_ids": [str(group.id)]},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_el_cocinero_no_asigna_grupos(
    client: AsyncClient, cocinero_token, energy_bowl, base
):
    group, _ = base
    resp = await client.put(
        _product_groups_url(energy_bowl.id),
        json={"group_ids": [str(group.id)]},
        headers=_auth(cocinero_token),
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_un_grupo_apagado_no_sale_en_la_carta(
    client: AsyncClient, bot_headers, db_session, energy_bowl, proteina_extra, base
):
    extra, _ = proteina_extra
    base_group, _ = base
    _assign(db_session, energy_bowl, extra, base_group)
    base_group.is_active = False
    db_session.flush()

    resp = await client.get(MENU_URL, headers=bot_headers)
    item = next(i for i in resp.json() if i["id"] == str(energy_bowl.id))
    assert [g["id"] for g in item["option_groups"]] == [str(extra.id)]


# ---------------------------------------------------------------------------
# El pedido: la opcion suma lo que dice el grupo, y el grupo manda
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_la_opcion_estructurada_suma_su_precio(
    client: AsyncClient, bot_headers, zona, db_session, energy_bowl, proteina_extra
):
    group, items = proteina_extra
    _assign(db_session, energy_bowl, group)
    payload = _order_payload(
        energy_bowl.id, quantity=1, options=_structured(items["Filete de pollo"])
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["items_total"] == "41.00"  # 33 + 8
    assert body["total"] == "46.00"
    (option,) = body["items"][0]["options"]
    assert option == {
        "option_group": group.name,
        "option_name": "Filete de pollo",
        "price_delta": "8.00",
        "option_item_id": str(items["Filete de pollo"].id),
    }


@pytest.mark.anyio
async def test_la_opcion_enlazada_cobra_el_precio_de_la_opcion(
    client: AsyncClient, bot_headers, zona, db_session, owner_user, energy_bowl
):
    """No el del producto: lo que cuesta el adicional lo decide el grupo."""
    bebida = _make_product(db_session, owner_user, f"MARACUYA {uuid.uuid4().hex[:4]}", "10.00")
    group, items = _make_group(
        db_session,
        owner_user,
        f"Adicionales {uuid.uuid4().hex[:4]}",
        max_choices=6,
        items=[("Maracuyá 12 oz", "8.00")],
    )
    items["Maracuyá 12 oz"].product_id = bebida.id
    _assign(db_session, energy_bowl, group)

    payload = _order_payload(
        energy_bowl.id, quantity=1, options=_structured(items["Maracuyá 12 oz"])
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["items_total"] == "41.00"  # 33 + 8, no 33 + 10


@pytest.mark.anyio
async def test_dos_en_un_grupo_de_una_sola_es_400(
    client: AsyncClient, bot_headers, zona, db_session, energy_bowl, base
):
    group, items = base
    _assign(db_session, energy_bowl, group)
    payload = _order_payload(
        energy_bowl.id, quantity=1, options=_structured(items["Camote"], items["Quinua"])
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == f"Elige como máximo 1 en {group.name}."


@pytest.mark.anyio
async def test_mas_del_maximo_es_400(
    client: AsyncClient, bot_headers, zona, db_session, energy_bowl, proteina_extra
):
    group, items = proteina_extra
    _assign(db_session, energy_bowl, group)
    payload = _order_payload(
        energy_bowl.id,
        quantity=1,
        options=_structured(
            items["Filete de pollo"], items["Milanesa"], items["Sin proteína extra"]
        ),
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == f"Elige como máximo 2 en {group.name}."


@pytest.mark.anyio
async def test_el_grupo_obligatorio_que_falta_es_400(
    client: AsyncClient, bot_headers, zona, db_session, energy_bowl, proteina_extra, base
):
    extra, _ = proteina_extra
    base_group, base_items = base
    _assign(db_session, energy_bowl, base_group, extra)
    payload = _order_payload(energy_bowl.id, quantity=1, options=_structured(base_items["Camote"]))
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == f"Falta elegir en {extra.name}."


@pytest.mark.anyio
async def test_menos_del_minimo_es_400(
    client: AsyncClient, bot_headers, zona, db_session, owner_user, energy_bowl
):
    group, items = _make_group(
        db_session,
        owner_user,
        f"Bases (elige 2) {uuid.uuid4().hex[:4]}",
        required=True,
        min_choices=2,
        max_choices=2,
        items=[("Lechuga base", "0"), ("Quinua tricolor", "0")],
    )
    _assign(db_session, energy_bowl, group)
    payload = _order_payload(energy_bowl.id, quantity=1, options=_structured(items["Lechuga base"]))
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == f"Elige al menos 2 en {group.name}."

    payload = _order_payload(
        energy_bowl.id,
        quantity=1,
        options=_structured(items["Lechuga base"], items["Quinua tricolor"]),
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text


@pytest.mark.anyio
async def test_la_opcion_de_otro_plato_es_400(
    client: AsyncClient, bot_headers, zona, db_session, owner_user, energy_bowl, proteina_extra
):
    group, items = proteina_extra
    otro = _make_product(db_session, owner_user, f"WRAP FRESH {uuid.uuid4().hex[:4]}", "28.00")
    _assign(db_session, otro, group)  # asignado al wrap, no al bowl
    payload = _order_payload(energy_bowl.id, quantity=1, options=_structured(items["Milanesa"]))
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "La opción no corresponde a este plato."


@pytest.mark.anyio
async def test_la_opcion_apagada_o_desconocida_es_400(
    client: AsyncClient, bot_headers, zona, db_session, energy_bowl, proteina_extra
):
    group, items = proteina_extra
    _assign(db_session, energy_bowl, group)
    items["Milanesa"].is_active = False
    db_session.flush()

    payload = _order_payload(energy_bowl.id, quantity=1, options=_structured(items["Milanesa"]))
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "La opción no corresponde a este plato."

    payload = _order_payload(
        energy_bowl.id, quantity=1, options=[{"option_item_id": str(uuid.uuid4())}]
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_el_texto_libre_no_exige_grupos(
    client: AsyncClient, bot_headers, zona, db_session, energy_bowl, proteina_extra
):
    """Un pedido todo en texto libre es el bot viejo: sigue entrando igual."""
    group, _ = proteina_extra
    _assign(db_session, energy_bowl, group)
    payload = _order_payload(
        energy_bowl.id, quantity=1, options=[{"option_group": "nota", "option_name": "sin cebolla"}]
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    (option,) = resp.json()["items"][0]["options"]
    assert option["option_item_id"] is None
    assert option["price_delta"] == "0.00"


@pytest.mark.anyio
async def test_las_dos_formas_conviven_en_el_mismo_item(
    client: AsyncClient, bot_headers, zona, db_session, energy_bowl, proteina_extra
):
    group, items = proteina_extra
    _assign(db_session, energy_bowl, group)
    payload = _order_payload(
        energy_bowl.id,
        quantity=2,
        options=[
            {"option_item_id": str(items["Milanesa"].id)},
            {"option_group": "nota", "option_name": "sin cebolla"},
        ],
    )
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["items_total"] == "80.00"  # (33 + 7) x 2


@pytest.mark.anyio
async def test_una_opcion_sin_ninguna_forma_es_422(
    client: AsyncClient, bot_headers, zona, energy_bowl
):
    payload = _order_payload(energy_bowl.id, quantity=1, options=[{"option_group": "nota"}])
    resp = await client.post(ORDERS_URL, json=payload, headers=bot_headers)
    assert resp.status_code == 422
