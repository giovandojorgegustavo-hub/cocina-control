"""Tests del asistente del panel: /api/v1/assistant/propose.

La propiedad central que se prueba aca es la frontera de seguridad: el endpoint
SOLO lee y devuelve una propuesta; nunca escribe. Por eso el modelo se mockea
por completo (monkeypatch) — nunca se llama a la API real — y lo que se verifica
es como el endpoint valida esa propuesta contra la base:

- una frase que sube un precio produce set_price con el product_id y el precio
  correctos, quantizados a dos decimales;
- un plato inexistente se degrada a `none` (no se muestra una propuesta que
  fallaria al confirmar);
- un pedido de borrar datos o editar codigo vuelve como `none` con un reply que
  declina, sin ejecutar ni fingir nada;
- sin clave configurada, 503;
- un cocinero no llega: 403.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.config import get_settings
from cocina_control.models.delivery_zone import DeliveryZone
from cocina_control.models.product import Product
from cocina_control.services import assistant_llm
from cocina_control.services.assistant_llm import LLMProposal

PROPOSE_URL = "/api/v1/assistant/propose"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def with_key(monkeypatch):
    """Configura una clave del asistente para la duracion del test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "assistant_api_key", "sk-test-not-real")
    return "sk-test-not-real"


@pytest.fixture
def no_key(monkeypatch):
    """Fuerza el estado de fabrica: sin clave, el asistente esta inerte."""
    settings = get_settings()
    monkeypatch.setattr(settings, "assistant_api_key", None)


def _fake_llm(monkeypatch, proposal: LLMProposal):
    """Reemplaza el cliente del modelo: los tests NUNCA llaman a la API real."""

    def _fake(messages, context, *, api_key, client=None):  # noqa: ANN001, ARG001
        return proposal

    monkeypatch.setattr(assistant_llm, "generate_proposal", _fake)


@pytest.fixture
def focus_bowl(db_session: Session, owner_user) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name="FOCUS BOWL",
        unit="un",
        is_active=True,
        is_purchase=False,
        is_sale=True,
        sale_price=Decimal("30.00"),
        created_by=owner_user.id,
    )
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def brena(db_session: Session, owner_user) -> DeliveryZone:
    zone = DeliveryZone(
        id=uuid.uuid4(),
        district="Breña",
        fee=Decimal("8.00"),
        is_active=True,
        created_by=owner_user.id,
    )
    db_session.add(zone)
    db_session.flush()
    return zone


# ---------------------------------------------------------------------------
# set_price: la frase feliz
# ---------------------------------------------------------------------------


async def test_set_price_yields_proposal(
    client: AsyncClient, owner_token, with_key, focus_bowl, monkeypatch
):
    _fake_llm(
        monkeypatch,
        LLMProposal(
            reply="Voy a subir el precio del Focus Bowl a S/ 35.00.",
            action={"type": "set_price", "product_id": str(focus_bowl.id), "sale_price": "35"},
            summary="Subir FOCUS BOWL a S/ 35.00",
        ),
    )

    response = await client.post(
        PROPOSE_URL,
        headers=_auth(owner_token),
        json={"messages": [{"role": "user", "content": "sube el Focus Bowl a 35"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"] is not None
    assert body["proposal"]["type"] == "set_price"
    assert body["proposal"]["product_id"] == str(focus_bowl.id)
    # Quantizado a dos decimales, como lo hara el endpoint de negocio.
    assert body["proposal"]["sale_price"] == "35.00"
    assert body["summary"]


async def test_set_zone_deactivate_yields_proposal(
    client: AsyncClient, admin_token, with_key, brena, monkeypatch
):
    _fake_llm(
        monkeypatch,
        LLMProposal(
            reply="Voy a desactivar el reparto a Breña.",
            action={"type": "set_zone", "zone_id": str(brena.id), "is_active": False},
            summary="Apagar Breña",
        ),
    )

    response = await client.post(
        PROPOSE_URL,
        headers=_auth(admin_token),
        json={"messages": [{"role": "user", "content": "desactiva Breña"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["type"] == "set_zone"
    assert body["proposal"]["zone_id"] == str(brena.id)
    assert body["proposal"]["is_active"] is False


# ---------------------------------------------------------------------------
# Validacion: un id inexistente se degrada a `none`
# ---------------------------------------------------------------------------


async def test_unknown_product_yields_none(
    client: AsyncClient, owner_token, with_key, monkeypatch
):
    _fake_llm(
        monkeypatch,
        LLMProposal(
            reply="Listo.",
            action={"type": "set_price", "product_id": str(uuid.uuid4()), "sale_price": "35"},
            summary="algo",
        ),
    )

    response = await client.post(
        PROPOSE_URL,
        headers=_auth(owner_token),
        json={"messages": [{"role": "user", "content": "sube el Plato Fantasma a 35"}]},
    )

    assert response.status_code == 200
    body = response.json()
    # Sin propuesta: el endpoint no muestra una accion que fallaria al confirmar.
    assert body["proposal"] is None
    assert body["reply"]


async def test_out_of_range_discount_yields_none(
    client: AsyncClient, owner_token, with_key, focus_bowl, monkeypatch
):
    _fake_llm(
        monkeypatch,
        LLMProposal(
            reply="Ok.",
            action={
                "type": "set_price",
                "product_id": str(focus_bowl.id),
                "discount_percent": "150",
            },
            summary="descuento imposible",
        ),
    )

    response = await client.post(
        PROPOSE_URL,
        headers=_auth(owner_token),
        json={"messages": [{"role": "user", "content": "pon 150% de descuento"}]},
    )

    assert response.status_code == 200
    assert response.json()["proposal"] is None


# ---------------------------------------------------------------------------
# El modelo declina lo que esta fuera de la lista cerrada
# ---------------------------------------------------------------------------


async def test_destructive_or_code_request_declined(
    client: AsyncClient, owner_token, with_key, monkeypatch
):
    _fake_llm(
        monkeypatch,
        LLMProposal(
            reply=(
                "Eso no lo puedo hacer. No puedo borrar pedidos ni editar el código; "
                "los cambios de código o de la web pasan por la revisión de un desarrollador."
            ),
            action={"type": "none"},
            summary=None,
        ),
    )

    for prompt in ("borra todos los pedidos", "edita el código de la web"):
        response = await client.post(
            PROPOSE_URL,
            headers=_auth(owner_token),
            json={"messages": [{"role": "user", "content": prompt}]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["proposal"] is None
        assert "no lo puedo hacer" in body["reply"].lower()


# ---------------------------------------------------------------------------
# Clave faltante y rol
# ---------------------------------------------------------------------------


async def test_missing_key_returns_503(client: AsyncClient, owner_token, no_key):
    response = await client.post(
        PROPOSE_URL,
        headers=_auth(owner_token),
        json={"messages": [{"role": "user", "content": "sube el Focus Bowl a 35"}]},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "El asistente no está configurado."


async def test_cocinero_forbidden(client: AsyncClient, cocinero_token, with_key):
    response = await client.post(
        PROPOSE_URL,
        headers=_auth(cocinero_token),
        json={"messages": [{"role": "user", "content": "sube el Focus Bowl a 35"}]},
    )
    assert response.status_code == 403
