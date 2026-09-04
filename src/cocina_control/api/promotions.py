"""Promociones: lo que el asistente puede ofrecer y lo que el dueno edita.

Routes
------
GET   /api/v1/catalog/promotions   — promos vigentes (asistente/owner/admin)
GET   /api/v1/promotions           — todas, incluso inactivas (owner/admin)
PATCH /api/v1/promotions/{code}    — editar porcentaje, vigencia (owner/admin)

Invariants
----------
- No hay POST ni DELETE. Las promociones nacen en migraciones porque el bot
  las conoce por codigo: una promo que aparece sin que el bot sepa ofrecerla
  no le sirve a nadie, y una que desaparece rompe el FK de los pedidos que
  la usaron. Apagarla es is_active = false.
- El importe del descuento nunca viaja: el pedido manda el codigo y el
  servidor aplica el porcentaje que este aca. Ver api/sales_orders.py.
"""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.api.deps import require_any_role
from cocina_control.db import get_session
from cocina_control.models.promotion import Promotion
from cocina_control.models.user import User
from cocina_control.schemas.promotion import (
    PromotionPublic,
    PromotionResponse,
    PromotionUpdate,
)

router = APIRouter(tags=["promotions"])

# Misma frontera que /catalog/menu: el asistente lee, no edita.
_CAN_READ_CATALOG = require_any_role("asistente_pedidos", "owner", "admin")
_CAN_EDIT = require_any_role("owner", "admin")
_CENTS = Decimal("0.01")


@router.get("/catalog/promotions", response_model=list[PromotionPublic])
def list_active_promotions(
    session: Session = Depends(get_session),
    _user: User = Depends(_CAN_READ_CATALOG),
) -> list[Promotion]:
    """Solo las vigentes: una promo apagada no existe para el asistente."""
    return list(
        session.scalars(
            select(Promotion)
            .where(Promotion.is_active.is_(True))
            .order_by(Promotion.code)
        ).all()
    )


@router.get("/promotions", response_model=list[PromotionResponse])
def list_promotions(
    session: Session = Depends(get_session),
    _user: User = Depends(_CAN_EDIT),
) -> list[Promotion]:
    return list(session.scalars(select(Promotion).order_by(Promotion.code)).all())


@router.patch("/promotions/{code}", response_model=PromotionResponse)
def update_promotion(
    code: str,
    body: PromotionUpdate,
    session: Session = Depends(get_session),
    actor: User = Depends(_CAN_EDIT),
) -> Promotion:
    promotion = session.get(Promotion, code)
    if promotion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Promotion not found"
        )

    if body.name is not None:
        promotion.name = body.name
    if body.percent is not None:
        # A centavos al escribir, para que la respuesta diga lo mismo que la columna.
        promotion.percent = body.percent.quantize(_CENTS)
    if body.first_order_only is not None:
        promotion.first_order_only = body.first_order_only
    if body.is_active is not None:
        promotion.is_active = body.is_active

    promotion.updated_at = datetime.now(UTC)
    promotion.updated_by = actor.id
    session.flush()
    return promotion
