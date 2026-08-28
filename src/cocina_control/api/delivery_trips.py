"""Viajes de reparto.

Routes
------
POST /api/v1/delivery-trips   — registra un viaje de inDrive con sus pedidos

Invariants
----------
- El costo NO lo manda quien despacha: se lee del propio link. Transcribirlo a
  mano abre la puerta a que no coincida con lo que inDrive cobro.
- Un pedido no puede estar en dos viajes. Si ya tiene viaje, se rechaza en vez
  de reasignarlo en silencio: reasignar borraria el rastro del primero.
- Si el link no se deja leer, el viaje se registra igual sin costo ni estado.
  Un reparto real no se bloquea porque un tercero cambio su JSON.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cocina_control.api.deps import require_any_role
from cocina_control.db import get_session
from cocina_control.models.customer import Customer, CustomerAddress
from cocina_control.models.delivery_trip import DeliveryTrip
from cocina_control.models.sales_order import SalesOrder
from cocina_control.models.user import User
from cocina_control.schemas.delivery_trip import (
    DeliveryTripCreate,
    DeliveryTripResponse,
    OrderInTrip,
)
from cocina_control.services.indrive import leer_viaje

router = APIRouter(prefix="/delivery-trips", tags=["delivery-trips"])

_PUEDE_DESPACHAR = require_any_role("asistente_pedidos", "owner", "admin")


@router.post("", response_model=DeliveryTripResponse, status_code=status.HTTP_201_CREATED)
def create_delivery_trip(
    payload: DeliveryTripCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(_PUEDE_DESPACHAR),
) -> DeliveryTripResponse:
    pedidos = list(
        session.scalars(
            select(SalesOrder).where(SalesOrder.id.in_(payload.sales_order_ids))
        ).all()
    )
    encontrados = {o.id for o in pedidos}
    faltan = [str(i) for i in payload.sales_order_ids if i not in encontrados]
    if faltan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estos pedidos no existen: {', '.join(faltan)}",
        )

    ya_en_viaje = [str(o.id) for o in pedidos if o.delivery_trip_id is not None]
    if ya_en_viaje:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Estos pedidos ya salieron en otro viaje: {', '.join(ya_en_viaje)}",
        )

    cancelados = [str(o.id) for o in pedidos if o.status == "cancelled"]
    if cancelados:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estos pedidos están cancelados: {', '.join(cancelados)}",
        )

    lectura = leer_viaje(payload.tracking_url)

    viaje = DeliveryTrip(
        id=uuid.uuid4(),
        tracking_url=payload.tracking_url,
        provider="indrive",
        trip_cost=lectura.cost,
        status=lectura.status,
        status_checked_at=datetime.now(UTC) if lectura.ok else None,
        created_by=actor.id,
    )
    session.add(viaje)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        # El índice único sobre tracking_url. Vale la pena decirlo claro: casi
        # siempre es que ya se registró y se está reintentando.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese link ya está registrado como viaje",
        ) from None

    for o in pedidos:
        o.delivery_trip_id = viaje.id
        o.status = "dispatched"
        o.updated_at = datetime.now(UTC)
        o.updated_by = actor.id

    session.commit()
    session.refresh(viaje)

    salida: list[OrderInTrip] = []
    for o in pedidos:
        cliente = session.get(Customer, o.customer_id)
        direccion = session.get(CustomerAddress, o.address_id) if o.address_id else None
        salida.append(
            OrderInTrip(
                id=o.id,
                customer_phone=cliente.phone if cliente else "",
                customer_name=cliente.name if cliente else None,
                district=direccion.district if direccion else "",
                total=o.total,
            )
        )

    return DeliveryTripResponse(
        id=viaje.id,
        tracking_url=viaje.tracking_url,
        provider=viaje.provider,
        trip_cost=viaje.trip_cost,
        status=viaje.status,
        created_at=viaje.created_at,
        orders=salida,
    )
