"""Asistente del panel: lee el negocio, propone UN cambio, nunca escribe.

Frontera de seguridad (el corazon de esta funcion)
--------------------------------------------------
Este endpoint SOLO lee y devuelve una propuesta estructurada: que accion de una
lista cerrada, con que parametros ya validados contra la base, y un resumen en
espanol. NO ejecuta ninguna escritura. La escritura la hace el frontend, con el
token del usuario, contra el endpoint de negocio que YA existe (PATCH
/products/{id}/pricing, etc.), y solo despues de que un humano toca "Confirmar".

Por eso el asistente no agrega poder: es una interfaz en lenguaje natural sobre
acciones que el mismo usuario ya puede hacer con clics, con el mismo rol
(owner/admin) y un confirm humano de por medio. Un id alucinado por el modelo se
cae aca, en la validacion contra la base, antes de mostrarse. Una accion fuera
de la lista no existe: el modelo elige `none`.

Clave faltante = 503
--------------------
Sin COCINA_ASSISTANT_API_KEY el endpoint corta con 503 y un mensaje claro. La
funcion queda inerte hasta que alguien carga una clave: es el default seguro.
"""

import logging
import uuid
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.api.deps import require_any_role
from cocina_control.api.option_groups import load_assigned_groups
from cocina_control.config import get_settings
from cocina_control.db import get_session
from cocina_control.models.delivery_zone import DeliveryZone
from cocina_control.models.option_group import OptionGroup, OptionItem
from cocina_control.models.product import Product
from cocina_control.models.promotion import Promotion
from cocina_control.models.user import User
from cocina_control.schemas.assistant import (
    AssistantProposeRequest,
    AssistantProposeResponse,
)
from cocina_control.services import assistant_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Misma frontera que las pantallas de la carta: quien edita precios, zonas,
# promos y opciones es owner/admin. El asistente no ensancha eso.
_CAN_USE = require_any_role("owner", "admin")

_CENTS = Decimal("0.01")
# Numeric(10, 2): el maximo que aceptan las columnas de importes.
_MAX_MONEY = Decimal("99999999.99")


# ---------------------------------------------------------------------------
# Contexto de negocio (solo lectura) que se le pasa al modelo
# ---------------------------------------------------------------------------


def _build_context(session: Session) -> dict[str, Any]:
    """Arma el contexto con ids reales: carta, zonas, promos y opciones.

    Reusa la misma logica de consulta que los endpoints (no se auto-llama por
    HTTP). Incluye lo activo y lo apagado de zonas/promos/grupos para que el
    modelo pueda proponer "volver a encender" algo.
    """
    products = list(
        session.scalars(
            select(Product)
            .where(Product.is_active.is_(True), Product.is_sale.is_(True))
            .order_by(Product.name)
        ).all()
    )
    assigned = load_assigned_groups(session, [p.id for p in products])

    zones = list(
        session.scalars(select(DeliveryZone).order_by(DeliveryZone.district)).all()
    )
    promotions = list(session.scalars(select(Promotion).order_by(Promotion.code)).all())
    groups = list(
        session.scalars(
            select(OptionGroup).order_by(OptionGroup.sort_order, OptionGroup.name)
        ).all()
    )
    items = list(session.scalars(select(OptionItem).order_by(OptionItem.name)).all())
    items_by_group: dict[uuid.UUID, list[OptionItem]] = {}
    for item in items:
        items_by_group.setdefault(item.group_id, []).append(item)

    return {
        "products": [
            {
                "id": str(p.id),
                "name": p.name,
                "sale_price": str(p.sale_price) if p.sale_price is not None else None,
                "discount_percent": (
                    str(p.discount_percent) if p.discount_percent is not None else None
                ),
                "assigned_group_ids": [str(g.id) for g in assigned.get(p.id, [])],
            }
            for p in products
        ],
        "delivery_zones": [
            {
                "id": str(z.id),
                "district": z.district,
                "fee": str(z.fee),
                "is_active": z.is_active,
            }
            for z in zones
        ],
        "promotions": [
            {
                "code": pr.code,
                "name": pr.name,
                "percent": str(pr.percent),
                "is_active": pr.is_active,
                "first_order_only": pr.first_order_only,
            }
            for pr in promotions
        ],
        "option_groups": [
            {
                "id": str(g.id),
                "name": g.name,
                "selection": g.selection,
                "is_active": g.is_active,
                "items": [
                    {
                        "id": str(it.id),
                        "name": it.name,
                        "price": str(it.price),
                        "is_active": it.is_active,
                    }
                    for it in items_by_group.get(g.id, [])
                ],
            }
            for g in groups
        ],
    }


# ---------------------------------------------------------------------------
# Validacion de la propuesta contra la base real
# ---------------------------------------------------------------------------


class _Invalid(Exception):
    """La propuesta no resiste la validacion; se degrada a `none`."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _as_uuid(value: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise _Invalid("El identificador no es válido.") from exc


def _money(value: Any, *, field: str, lo: Decimal, hi: Decimal, inclusive_hi: bool) -> str:
    """Parsea un importe/porcentaje a string con dos decimales o rechaza.

    Espeja los rangos de los schemas de negocio: mandar algo fuera de rango solo
    provocaria un 422 al confirmar, asi que se corta antes y se degrada a `none`.
    """
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise _Invalid(f"El valor de {field} no es un número.") from exc
    if parsed < lo:
        raise _Invalid(f"El valor de {field} no puede ser menor que {lo}.")
    if inclusive_hi:
        if parsed > hi:
            raise _Invalid(f"El valor de {field} no puede ser mayor que {hi}.")
    elif parsed >= hi:
        raise _Invalid(f"El valor de {field} debe ser menor que {hi}.")
    return str(parsed.quantize(_CENTS))


def _price(value: Any, field: str) -> str:
    """Caso comun de _money: un importe entre 0 y el maximo de la columna."""
    return _money(value, field=field, lo=Decimal("0"), hi=_MAX_MONEY, inclusive_hi=True)


def _get_active_sale_product(session: Session, action: dict[str, Any]) -> Product:
    product = session.get(Product, _as_uuid(action.get("product_id")))
    if product is None or not product.is_active:
        raise _Invalid("No encontré ese plato en la carta.")
    if not product.is_sale:
        raise _Invalid(f"'{product.name}' no es un plato de venta.")
    return product


def _validate_set_price(session: Session, action: dict[str, Any]) -> dict[str, Any]:
    product = _get_active_sale_product(session, action)
    out: dict[str, Any] = {
        "type": "set_price",
        "product_id": str(product.id),
        "product_name": product.name,
    }
    touched = False
    if action.get("sale_price") is not None:
        out["sale_price"] = _price(action["sale_price"], "precio")
        touched = True
    if action.get("discount_percent") is not None:
        out["discount_percent"] = _money(
            action["discount_percent"],
            field="descuento",
            lo=Decimal("0"),
            hi=Decimal("100"),
            inclusive_hi=False,
        )
        touched = True
    if not touched:
        raise _Invalid("No dijiste qué precio o descuento poner.")
    return out


def _validate_set_zone(session: Session, action: dict[str, Any]) -> dict[str, Any]:
    zone = session.get(DeliveryZone, _as_uuid(action.get("zone_id")))
    if zone is None:
        raise _Invalid("No encontré ese distrito de reparto.")
    out: dict[str, Any] = {"type": "set_zone", "zone_id": str(zone.id), "district": zone.district}
    touched = False
    if action.get("fee") is not None:
        out["fee"] = _price(action["fee"], "tarifa")
        touched = True
    if action.get("is_active") is not None:
        out["is_active"] = bool(action["is_active"])
        touched = True
    if not touched:
        raise _Invalid("No dijiste qué cambiar del distrito.")
    return out


def _validate_new_zone(session: Session, action: dict[str, Any]) -> dict[str, Any]:
    district = (action.get("district") or "").strip()
    if not district or len(district) > 80:
        raise _Invalid("El nombre del distrito no es válido.")
    if action.get("fee") is None:
        raise _Invalid("Falta la tarifa del distrito.")
    fee = _price(action["fee"], "tarifa")
    return {"type": "new_zone", "district": district, "fee": fee}


def _validate_set_promotion(session: Session, action: dict[str, Any]) -> dict[str, Any]:
    code = (action.get("code") or "").strip()
    promo = session.get(Promotion, code) if code else None
    if promo is None:
        raise _Invalid("No encontré esa promoción.")
    out: dict[str, Any] = {"type": "set_promotion", "code": promo.code, "name": promo.name}
    touched = False
    if action.get("percent") is not None:
        # Las promos van >0 y <100 (ck_promotions_percent_range).
        try:
            parsed = Decimal(str(action["percent"]))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise _Invalid("El porcentaje no es un número.") from exc
        if parsed <= 0 or parsed >= 100:
            raise _Invalid("El porcentaje de la promoción debe estar entre 0 y 100.")
        out["percent"] = str(parsed.quantize(_CENTS))
        touched = True
    if action.get("is_active") is not None:
        out["is_active"] = bool(action["is_active"])
        touched = True
    if action.get("first_order_only") is not None:
        out["first_order_only"] = bool(action["first_order_only"])
        touched = True
    if not touched:
        raise _Invalid("No dijiste qué cambiar de la promoción.")
    return out


def _validate_set_option_item(session: Session, action: dict[str, Any]) -> dict[str, Any]:
    item = session.get(OptionItem, _as_uuid(action.get("option_item_id")))
    if item is None:
        raise _Invalid("No encontré esa opción.")
    out: dict[str, Any] = {"type": "set_option_item", "option_item_id": str(item.id)}
    touched = False
    if action.get("name") is not None:
        name = str(action["name"]).strip()
        if not name or len(name) > 120:
            raise _Invalid("El nombre de la opción no es válido.")
        out["name"] = name
        touched = True
    if action.get("price") is not None:
        out["price"] = _price(action["price"], "precio")
        touched = True
    if action.get("is_active") is not None:
        out["is_active"] = bool(action["is_active"])
        touched = True
    if not touched:
        raise _Invalid("No dijiste qué cambiar de la opción.")
    return out


def _validate_new_option_item(session: Session, action: dict[str, Any]) -> dict[str, Any]:
    group = session.get(OptionGroup, _as_uuid(action.get("group_id")))
    if group is None:
        raise _Invalid("No encontré ese grupo de opciones.")
    name = str(action.get("name") or "").strip()
    if not name or len(name) > 120:
        raise _Invalid("El nombre de la opción no es válido.")
    if action.get("price") is None:
        raise _Invalid("Falta el precio de la opción.")
    price = _price(action["price"], "precio")
    return {
        "type": "new_option_item",
        "group_id": str(group.id),
        "group_name": group.name,
        "name": name,
        "price": price,
    }


def _validate_set_option_group(session: Session, action: dict[str, Any]) -> dict[str, Any]:
    group = session.get(OptionGroup, _as_uuid(action.get("group_id")))
    if group is None:
        raise _Invalid("No encontré ese grupo de opciones.")
    out: dict[str, Any] = {"type": "set_option_group", "group_id": str(group.id)}
    touched = False
    if action.get("name") is not None:
        name = str(action["name"]).strip()
        if not name or len(name) > 80:
            raise _Invalid("El nombre del grupo no es válido.")
        out["name"] = name
        touched = True
    if action.get("is_active") is not None:
        out["is_active"] = bool(action["is_active"])
        touched = True
    if not touched:
        raise _Invalid("No dijiste qué cambiar del grupo.")
    return out


def _validate_assign_groups(session: Session, action: dict[str, Any]) -> dict[str, Any]:
    product = _get_active_sale_product(session, action)
    raw_ids = action.get("group_ids")
    if not isinstance(raw_ids, list):
        raise _Invalid("No entendí qué grupos asignar.")
    group_ids: list[str] = []
    seen: set[uuid.UUID] = set()
    for raw in raw_ids:
        gid = _as_uuid(raw)
        if gid in seen:
            raise _Invalid("Un grupo aparece repetido.")
        seen.add(gid)
        if session.get(OptionGroup, gid) is None:
            raise _Invalid("Uno de los grupos no existe.")
        group_ids.append(str(gid))
    return {
        "type": "assign_groups",
        "product_id": str(product.id),
        "product_name": product.name,
        "group_ids": group_ids,
    }


_VALIDATORS = {
    "set_price": _validate_set_price,
    "set_zone": _validate_set_zone,
    "new_zone": _validate_new_zone,
    "set_promotion": _validate_set_promotion,
    "set_option_item": _validate_set_option_item,
    "new_option_item": _validate_new_option_item,
    "set_option_group": _validate_set_option_group,
    "assign_groups": _validate_assign_groups,
}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/propose", response_model=AssistantProposeResponse)
def propose(
    body: AssistantProposeRequest,
    session: Annotated[Session, Depends(get_session)],
    _actor: Annotated[User, Depends(_CAN_USE)],
) -> AssistantProposeResponse:
    """Devuelve UNA propuesta a partir de la conversacion. Nunca escribe.

    - Sin clave configurada: 503, y la funcion queda inerte.
    - Con clave: arma el contexto, le pide al modelo una accion de la lista
      cerrada, valida ids y rangos contra la base, y devuelve la propuesta (o
      `none`). La escritura la hace el frontend tras un Confirmar humano.
    """
    settings = get_settings()
    if not settings.assistant_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El asistente no está configurado.",
        )

    context = _build_context(session)
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        result = assistant_llm.generate_proposal(
            messages, context, api_key=settings.assistant_api_key
        )
    except assistant_llm.AssistantLLMError as exc:
        # Un fallo del modelo/red no es un 500 nuestro: es un 502 con mensaje claro.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El asistente no pudo responder. Intentá de nuevo.",
        ) from exc

    action = result.action
    # Sin accion, o `none`: charla / no se puede / requiere revision de codigo.
    if not action or action.get("type") in (None, "none"):
        return AssistantProposeResponse(reply=result.reply, proposal=None, summary=None)

    action_type = action.get("type")
    validator = _VALIDATORS.get(action_type)
    if validator is None:
        # El modelo nombro una accion fuera de la lista: se ignora y se degrada.
        logger.warning("Asistente propuso una acción no permitida: %r", action_type)
        return AssistantProposeResponse(reply=result.reply, proposal=None, summary=None)

    try:
        validated = validator(session, action)
    except _Invalid as exc:
        # Id inexistente o parametro fuera de rango: se degrada a `none` con el
        # motivo, en vez de mostrar una propuesta que fallaria al confirmar.
        return AssistantProposeResponse(reply=exc.reason, proposal=None, summary=None)

    return AssistantProposeResponse(
        reply=result.reply, proposal=validated, summary=result.summary
    )
