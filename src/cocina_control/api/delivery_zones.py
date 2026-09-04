"""Tarifas de reparto por distrito.

Routes
------
GET   /api/v1/delivery-zones            — zonas con cobertura; ?all=true incluye
                                          las apagadas (owner/admin)
GET   /api/v1/delivery-zones/quote      — cotiza un distrito por nombre
POST  /api/v1/delivery-zones            — alta de distrito (owner/admin)
PATCH /api/v1/delivery-zones/{id}       — nombre, tarifa, activa (owner/admin)

Invariants
----------
- Un distrito sin fila activa NO tiene cobertura. La ausencia es la respuesta.
- La busqueda ignora mayusculas y tildes: el cliente escribe "magdalena",
  "Magdalena" y "MAGDALENA DEL MAR", y las tres resuelven a la misma tarifa.
  La misma llave decide si un alta o un rename choca con una fila existente,
  activa o no: dos filas para el mismo distrito harian que el asistente cotice
  con la que encuentre primero.
- No hay DELETE. Un distrito que deja de tener cobertura se apaga
  (is_active = false): la fila sigue contando la historia de a cuanto se
  cobro el reparto cuando los pedidos de esa epoca se cerraron, y un distrito
  que vuelve a la lista recupera su tarifa con un clic en vez de que alguien
  la vuelva a adivinar.
"""

import unicodedata
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.api.deps import get_current_user, require_any_role
from cocina_control.db import get_session
from cocina_control.models.delivery_zone import DeliveryZone
from cocina_control.models.user import User
from cocina_control.schemas.delivery_zone import (
    DeliveryQuoteResponse,
    DeliveryZoneCreate,
    DeliveryZoneResponse,
    DeliveryZoneUpdate,
)

router = APIRouter(prefix="/delivery-zones", tags=["delivery-zones"])

# Misma frontera que /promotions: el asistente lee, el dueno edita.
_CAN_EDIT = require_any_role("owner", "admin")
_EDITOR_ROLES = frozenset({"owner", "admin"})
_CENTS = Decimal("0.01")


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
    zones = session.scalars(select(DeliveryZone).where(DeliveryZone.is_active.is_(True))).all()
    for zone in zones:
        if normalise_district(zone.district) == key:
            return zone
    return None


def _find_conflict(
    session: Session, district: str, *, exclude_id: uuid.UUID | None = None
) -> DeliveryZone | None:
    """La fila (activa o no) que ya ocupa este distrito, si la hay.

    A diferencia de find_zone, mira tambien las apagadas: dar de alta "Lince"
    cuando existe un "Lince" desactivado crearia el mellizo que el indice de
    lower(district) atajaria por caja pero no por tilde. Lo correcto es
    volver a encender la fila que ya esta, y el 409 es lo que lo dice.
    """
    key = normalise_district(district)
    for zone in session.scalars(select(DeliveryZone)).all():
        if zone.id == exclude_id:
            continue
        if normalise_district(zone.district) == key:
            return zone
    return None


def _conflict(zone: DeliveryZone) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Delivery zone for '{zone.district}' already exists",
    )


@router.get("", response_model=list[DeliveryZoneResponse])
def list_delivery_zones(
    all: bool = Query(
        default=False,
        description="Incluir zonas desactivadas (solo owner/admin)",
    ),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[DeliveryZone]:
    """Zonas con cobertura; con ?all=true tambien las apagadas.

    El chequeo de rol vive solo en la rama all=true y no en la dependencia: el
    asistente de WhatsApp usa esta misma lista para cotizar y no tiene rol de
    editor. Que vea las apagadas no le sirve — para el bot una zona apagada no
    existe — y cambiar la firma del endpoint lo dejaria afuera.
    """
    query = select(DeliveryZone)
    if all:
        if user.role not in _EDITOR_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    else:
        query = query.where(DeliveryZone.is_active.is_(True))
    return list(session.scalars(query.order_by(DeliveryZone.fee, DeliveryZone.district)).all())


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


@router.post("", response_model=DeliveryZoneResponse, status_code=status.HTTP_201_CREATED)
def create_delivery_zone(
    body: DeliveryZoneCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(_CAN_EDIT),
) -> DeliveryZone:
    existing = _find_conflict(session, body.district)
    if existing is not None:
        raise _conflict(existing)

    zone = DeliveryZone(
        id=uuid.uuid4(),
        district=body.district,
        # A centavos al escribir, para que la respuesta diga lo mismo que la columna.
        fee=body.fee.quantize(_CENTS),
        is_active=True,
        created_by=actor.id,
    )
    session.add(zone)
    session.flush()
    return zone


@router.patch("/{zone_id}", response_model=DeliveryZoneResponse)
def update_delivery_zone(
    zone_id: uuid.UUID,
    body: DeliveryZoneUpdate,
    session: Session = Depends(get_session),
    actor: User = Depends(_CAN_EDIT),
) -> DeliveryZone:
    zone = session.get(DeliveryZone, zone_id)
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery zone not found")

    if body.district is not None:
        existing = _find_conflict(session, body.district, exclude_id=zone.id)
        if existing is not None:
            raise _conflict(existing)
        zone.district = body.district
    if body.fee is not None:
        zone.fee = body.fee.quantize(_CENTS)
    if body.is_active is not None:
        zone.is_active = body.is_active

    zone.updated_at = datetime.now(UTC)
    zone.updated_by = actor.id
    session.flush()
    return zone
