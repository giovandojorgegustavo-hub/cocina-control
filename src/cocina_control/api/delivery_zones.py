"""Tarifas de reparto por distrito.

Routes
------
GET /api/v1/delivery-zones          — lista de zonas con cobertura
GET /api/v1/delivery-zones/quote    — cotiza un distrito por nombre

Invariants
----------
- Un distrito sin fila activa NO tiene cobertura. La ausencia es la respuesta.
- La busqueda ignora mayusculas y tildes: el cliente escribe "magdalena",
  "Magdalena" y "MAGDALENA DEL MAR", y las tres resuelven a la misma tarifa.
"""

import unicodedata

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.api.deps import get_current_user
from cocina_control.db import get_session
from cocina_control.models.delivery_zone import DeliveryZone
from cocina_control.models.user import User
from cocina_control.schemas.delivery_zone import (
    DeliveryQuoteResponse,
    DeliveryZoneResponse,
)

router = APIRouter(prefix="/delivery-zones", tags=["delivery-zones"])


def normalise_district(value: str) -> str:
    """Llave de comparacion: sin tildes, sin mayusculas, sin espacios de mas.

    El indice unico de la tabla es sobre lower(district) y NO ignora tildes, asi
    que "Jesus Maria" y "Jesús María" conviven como filas distintas si alguien
    las carga a mano. Comparar por esta llave es lo que evita que el asistente
    cotice con la que encuentre primero.
    """
    collapsed = " ".join(value.strip().split()).upper()
    decomposed = unicodedata.normalize("NFKD", collapsed)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def find_zone(session: Session, district: str) -> DeliveryZone | None:
    """Devuelve la zona activa cuyo distrito coincide, ignorando tildes y caja."""
    key = normalise_district(district)
    zones = session.scalars(
        select(DeliveryZone).where(DeliveryZone.is_active.is_(True))
    ).all()
    for zone in zones:
        if normalise_district(zone.district) == key:
            return zone
    return None


@router.get("", response_model=list[DeliveryZoneResponse])
def list_delivery_zones(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> list[DeliveryZone]:
    return list(
        session.scalars(
            select(DeliveryZone)
            .where(DeliveryZone.is_active.is_(True))
            .order_by(DeliveryZone.fee, DeliveryZone.district)
        ).all()
    )


@router.get("/quote", response_model=DeliveryQuoteResponse)
def quote_delivery(
    district: str = Query(..., min_length=2, max_length=120),
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> DeliveryQuoteResponse:
    """Cotiza el reparto a un distrito.

    Un distrito sin cobertura devuelve 200 con covered=false, no 404: "no
    repartimos ahi" es una respuesta de negocio perfectamente valida, y
    convertirla en error obligaria al asistente a tratarla como una falla.
    """
    zone = find_zone(session, district)
    if zone is None:
        return DeliveryQuoteResponse(district=district, covered=False, fee=None)
    return DeliveryQuoteResponse(district=zone.district, covered=True, fee=zone.fee)
