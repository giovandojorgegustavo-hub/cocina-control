"""Endpoint tests for ingredient capture on complete/correct.

El operario y el asistente de WhatsApp recorren este mismo endpoint: el bot
presenta su service principal y nombra al cocinero en X-Act-As, pero el cuerpo
y las validaciones son identicos. Por eso no hay una bateria separada para el
bot — seria probar dos veces el mismo codigo y dar la falsa impresion de que
hay dos caminos.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.delivery_order import DeliveryOrder
from cocina_control.models.product import Product

_BASE = "/api/v1/delivery-orders"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_product(
    session: Session,
    owner_id: uuid.UUID,
    name: str,
    *,
    is_active: bool = True,
    is_purchase: bool = True,
    is_sale: bool = False,
) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name=f"{name}-{uuid.uuid4().hex[:6]}".upper(),
        unit="kg",
        is_active=is_active,
        is_purchase=is_purchase,
        is_sale=is_sale,
        created_by=owner_id,
    )
    session.add(product)
    session.flush()
    return product


def _make_pending_order(session: Session, created_by: uuid.UUID) -> DeliveryOrder:
    order = DeliveryOrder(
        id=uuid.uuid4(),
        status="pending",
        created_by=created_by,
        created_at=datetime.now(UTC),
    )
    session.add(order)
    session.flush()
    return order


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_persists_and_returns_ingredients(
    client: AsyncClient, db_session: Session, cocinero_user, cocinero_token
):
    plato = _make_product(db_session, cocinero_user.id, "ARMA TU BOWL", is_sale=True)
    lechuga = _make_product(db_session, cocinero_user.id, "LECHUGA CRESPA")
    quinua = _make_product(db_session, cocinero_user.id, "QUINUA")
    order = _make_pending_order(db_session, cocinero_user.id)

    response = await client.post(
        f"{_BASE}/{order.id}/complete",
        json={
            "items": [
                {
                    "product_id": str(plato.id),
                    "quantity": "1",
                    "ingredients": [
                        {"ingredient_id": str(lechuga.id)},
                        {"ingredient_id": str(quinua.id), "quantity": "0.08"},
                    ],
                }
            ]
        },
        headers=_auth(cocinero_token),
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1

    returned = {i["ingredient_id"]: i for i in items[0]["ingredients"]}
    assert set(returned) == {str(lechuga.id), str(quinua.id)}
    # Sin cantidad declarada, la fila queda igual de valida: el objetivo de la
    # primera version es capturar QUE lleva el plato, no cuanto.
    assert returned[str(lechuga.id)]["quantity"] is None
    assert returned[str(lechuga.id)]["status"] == "included"
    assert returned[str(quinua.id)]["quantity"] == "0.08"


@pytest.mark.asyncio
async def test_complete_without_ingredients_still_works(
    client: AsyncClient, db_session: Session, cocinero_user, cocinero_token
):
    """Un plato fijo sin modificadores no tiene nada que declarar."""
    plato = _make_product(db_session, cocinero_user.id, "FOCUS BOWL", is_sale=True)
    order = _make_pending_order(db_session, cocinero_user.id)

    response = await client.post(
        f"{_BASE}/{order.id}/complete",
        json={"items": [{"product_id": str(plato.id), "quantity": "1"}]},
        headers=_auth(cocinero_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["ingredients"] == []


@pytest.mark.asyncio
async def test_sale_only_product_is_accepted_as_ingredient(
    client: AsyncClient, db_session: Session, cocinero_user, cocinero_token
):
    """La salsa es is_sale y aun asi es modificador del bowl en el ticket."""
    plato = _make_product(db_session, cocinero_user.id, "BOWL CRISPY", is_sale=True)
    salsa = _make_product(
        db_session,
        cocinero_user.id,
        "SALSA DE PALTA PROTEICA",
        is_purchase=False,
        is_sale=True,
    )
    order = _make_pending_order(db_session, cocinero_user.id)

    response = await client.post(
        f"{_BASE}/{order.id}/complete",
        json={
            "items": [
                {
                    "product_id": str(plato.id),
                    "quantity": "1",
                    "ingredients": [{"ingredient_id": str(salsa.id)}],
                }
            ]
        },
        headers=_auth(cocinero_token),
    )

    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Quiebre de stock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_out_of_stock_ingredient_is_recorded(
    client: AsyncClient, db_session: Session, cocinero_user, cocinero_token
):
    plato = _make_product(db_session, cocinero_user.id, "ENERGY BOWL", is_sale=True)
    palta = _make_product(db_session, cocinero_user.id, "PALTA")
    order = _make_pending_order(db_session, cocinero_user.id)

    response = await client.post(
        f"{_BASE}/{order.id}/complete",
        json={
            "items": [
                {
                    "product_id": str(plato.id),
                    "quantity": "1",
                    "ingredients": [{"ingredient_id": str(palta.id), "status": "out_of_stock"}],
                }
            ]
        },
        headers=_auth(cocinero_token),
    )

    assert response.status_code == 200, response.text
    ingredient = response.json()["items"][0]["ingredients"][0]
    assert ingredient["status"] == "out_of_stock"
    assert ingredient["quantity"] is None


@pytest.mark.asyncio
async def test_out_of_stock_with_quantity_is_rejected(
    client: AsyncClient, db_session: Session, cocinero_user, cocinero_token
):
    """Lo que no salio no consumio nada: 422, no un 500 por IntegrityError."""
    plato = _make_product(db_session, cocinero_user.id, "WRAP FRESH", is_sale=True)
    palta = _make_product(db_session, cocinero_user.id, "PALTA")
    order = _make_pending_order(db_session, cocinero_user.id)

    response = await client.post(
        f"{_BASE}/{order.id}/complete",
        json={
            "items": [
                {
                    "product_id": str(plato.id),
                    "quantity": "1",
                    "ingredients": [
                        {
                            "ingredient_id": str(palta.id),
                            "quantity": "0.05",
                            "status": "out_of_stock",
                        }
                    ],
                }
            ]
        },
        headers=_auth(cocinero_token),
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Rechazos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_ingredient_in_same_item_is_rejected(
    client: AsyncClient, db_session: Session, cocinero_user, cocinero_token
):
    plato = _make_product(db_session, cocinero_user.id, "ARMA TU WRAP", is_sale=True)
    tomate = _make_product(db_session, cocinero_user.id, "TOMATE")
    order = _make_pending_order(db_session, cocinero_user.id)

    response = await client.post(
        f"{_BASE}/{order.id}/complete",
        json={
            "items": [
                {
                    "product_id": str(plato.id),
                    "quantity": "1",
                    "ingredients": [
                        {"ingredient_id": str(tomate.id)},
                        {"ingredient_id": str(tomate.id)},
                    ],
                }
            ]
        },
        headers=_auth(cocinero_token),
    )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_inactive_ingredient_is_rejected(
    client: AsyncClient, db_session: Session, cocinero_user, cocinero_token
):
    plato = _make_product(db_session, cocinero_user.id, "ARMA TU SALAD", is_sale=True)
    retirado = _make_product(db_session, cocinero_user.id, "CHUCRUT VIEJO", is_active=False)
    order = _make_pending_order(db_session, cocinero_user.id)

    response = await client.post(
        f"{_BASE}/{order.id}/complete",
        json={
            "items": [
                {
                    "product_id": str(plato.id),
                    "quantity": "1",
                    "ingredients": [{"ingredient_id": str(retirado.id)}],
                }
            ]
        },
        headers=_auth(cocinero_token),
    )

    assert response.status_code == 400, response.text
    assert str(retirado.id) in response.json()["detail"]["invalid_ids"]


@pytest.mark.asyncio
async def test_unknown_ingredient_is_rejected(
    client: AsyncClient, db_session: Session, cocinero_user, cocinero_token
):
    plato = _make_product(db_session, cocinero_user.id, "BONA WRAP", is_sale=True)
    order = _make_pending_order(db_session, cocinero_user.id)
    ghost = uuid.uuid4()

    response = await client.post(
        f"{_BASE}/{order.id}/complete",
        json={
            "items": [
                {
                    "product_id": str(plato.id),
                    "quantity": "1",
                    "ingredients": [{"ingredient_id": str(ghost)}],
                }
            ]
        },
        headers=_auth(cocinero_token),
    )

    assert response.status_code == 400, response.text
    assert str(ghost) in response.json()["detail"]["invalid_ids"]


# ---------------------------------------------------------------------------
# Correccion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_correct_carries_ingredients_to_the_new_order(
    client: AsyncClient, db_session: Session, cocinero_user, cocinero_token
):
    """Corregir es el mismo acto de registro; comparte _persist_items."""
    plato = _make_product(db_session, cocinero_user.id, "BOWL CRISPY", is_sale=True)
    choclo = _make_product(db_session, cocinero_user.id, "CHOCLO AMERICANO")
    order = _make_pending_order(db_session, cocinero_user.id)

    completed = await client.post(
        f"{_BASE}/{order.id}/complete",
        json={"items": [{"product_id": str(plato.id), "quantity": "1"}]},
        headers=_auth(cocinero_token),
    )
    assert completed.status_code == 200, completed.text

    corrected = await client.post(
        f"{_BASE}/{order.id}/correct",
        json={
            "items": [
                {
                    "product_id": str(plato.id),
                    "quantity": "1",
                    "ingredients": [{"ingredient_id": str(choclo.id)}],
                }
            ],
            "reason": "faltaba el choclo",
        },
        headers=_auth(cocinero_token),
    )

    assert corrected.status_code == 201, corrected.text
    new_id = corrected.json()["id"]

    detail = await client.get(f"{_BASE}/{new_id}", headers=_auth(cocinero_token))
    assert detail.status_code == 200, detail.text
    ingredients = detail.json()["items"][0]["ingredients"]
    assert [i["ingredient_id"] for i in ingredients] == [str(choclo.id)]
