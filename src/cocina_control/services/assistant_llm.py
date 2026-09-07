"""Cliente del asistente del panel: traduce lenguaje natural a UNA propuesta.

Este modulo NO escribe nada. Su unico trabajo es preguntarle al modelo, con el
contexto del negocio ya cargado (carta, zonas, promociones, grupos de opciones),
que accion de una LISTA CERRADA describe lo que el dueno pidio en espanol. La
escritura la hace despues el frontend, con el token del usuario, contra el
endpoint de negocio que ya existe, y solo tras un "Confirmar" humano. Aca no
hay ninguna llamada de escritura, ni la puede haber: httpx solo habla con la
API de Anthropic.

POR QUE UNA LISTA CERRADA
-------------------------
El modelo elige entre acciones con nombre fijo (set_price, set_zone, ...). No
puede inventar una accion nueva ni una ruta nueva: si lo que se pide no encaja,
la respuesta es `none`, que es "hablemos" o "eso no lo puedo hacer". El endpoint
vuelve a validar los ids y los rangos sobre la base real, asi que aunque el
modelo alucine un id, la propuesta se cae antes de mostrarse.

CLAVE FALTANTE = INERTE
-----------------------
Sin COCINA_ASSISTANT_API_KEY la funcion no se llama: el endpoint corta antes
con 503. El asistente no existe hasta que alguien carga una clave, y la clave
nunca viaja al repo ni al log.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Modelo chico y barato: la tarea es clasificar una frase en una accion, no
# redactar. Se fija aca y no en settings porque cambiarlo es una decision de
# ingenieria (formato del tool use), no de operacion.
_MODEL = "claude-haiku-4-5-20251001"
_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_MAX_TOKENS = 1024
_TIMEOUT_S = 30.0

# La lista cerrada. El modelo DEBE elegir un `type` de aca; cualquier otro
# valor lo rechaza el endpoint. Mantener en sync con api/assistant.py.
ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "set_price",
        "set_zone",
        "new_zone",
        "set_promotion",
        "set_option_item",
        "new_option_item",
        "set_option_group",
        "assign_groups",
        "none",
    }
)


class AssistantLLMError(RuntimeError):
    """El modelo no devolvio una propuesta utilizable (red, formato, timeout)."""


@dataclass(frozen=True)
class LLMProposal:
    """Lo que el modelo propuso, sin validar todavia contra la base.

    - reply: texto en espanol que se le muestra al dueno.
    - action: dict con `type` en ALLOWED_ACTIONS y sus parametros, o None.
    - summary: una linea que describe el cambio, o None cuando no hay accion.
    """

    reply: str
    action: dict[str, Any] | None
    summary: str | None


# La herramienta que el modelo esta OBLIGADO a usar. El schema es intencionalmente
# laxo en los parametros (el endpoint valida ids y rangos contra la base): lo que
# se fuerza aca es la forma — un `type` de la lista, un `reply` y un `summary`.
_TOOL = {
    "name": "emitir_propuesta",
    "description": (
        "Emite UNA propuesta de cambio de configuracion del negocio, o `none` "
        "si no hay accion (charla, no se puede, o requiere revision de codigo). "
        "Nunca ejecutas el cambio: solo lo describes para que un humano confirme."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reply": {
                "type": "string",
                "description": "Respuesta en espanol neutro para el dueno.",
            },
            "summary": {
                "type": ["string", "null"],
                "description": "Una linea en espanol que resume el cambio; null si no hay accion.",
            },
            "action": {
                "type": ["object", "null"],
                "description": "La accion propuesta o null. Debe tener 'type' de la lista.",
                "properties": {
                    "type": {"type": "string", "enum": sorted(ALLOWED_ACTIONS)},
                    "product_id": {"type": ["string", "null"]},
                    "zone_id": {"type": ["string", "null"]},
                    "option_item_id": {"type": ["string", "null"]},
                    "group_id": {"type": ["string", "null"]},
                    "group_ids": {"type": ["array", "null"], "items": {"type": "string"}},
                    "code": {"type": ["string", "null"]},
                    "district": {"type": ["string", "null"]},
                    "name": {"type": ["string", "null"]},
                    "sale_price": {"type": ["string", "null"]},
                    "discount_percent": {"type": ["string", "null"]},
                    "fee": {"type": ["string", "null"]},
                    "price": {"type": ["string", "null"]},
                    "percent": {"type": ["string", "null"]},
                    "is_active": {"type": ["boolean", "null"]},
                    "first_order_only": {"type": ["boolean", "null"]},
                },
                "required": ["type"],
            },
        },
        "required": ["reply", "action"],
    },
}

_SYSTEM_PROMPT = """\
Eres el asistente de configuracion del panel interno de una dark kitchen en Lima.
El dueno o un admin te escribe en espanol para cambiar la configuracion del negocio.

REGLAS DURAS:
- NUNCA ejecutas un cambio. Solo describes UNA accion para que un humano la confirme.
- Elegis exactamente UNA accion de la lista permitida, o `none`.
- Solo podes tocar: precios y descuentos de platos, zonas de reparto, promociones,
  grupos de opciones y sus items, y la asignacion de grupos a un plato.
- Si te piden editar codigo, la web, el servidor, la base de datos directamente,
  borrar pedidos/datos, o cualquier cosa fuera de esa lista: responde con `none` y
  un reply que explique amablemente que eso no lo podes hacer, y que los cambios de
  codigo o de la web pasan por la revision de un desarrollador. No inventes que lo hiciste.
- Usa los ids EXACTOS del contexto. Si no encontras el plato/zona/promo/opcion que
  nombran, responde `none` y pedi que aclaren, nombrando lo que si existe.
- Los importes y porcentajes van como string con dos decimales (ej "35.00", "10.00").
- El reply y el summary van en espanol neutro, claro y breve.

Acciones permitidas y sus parametros:
- set_price {product_id, sale_price?, discount_percent?}: precio de lista y/o descuento de un plato.
- set_zone {zone_id, fee?, is_active?}: tarifa y/o encender/apagar una zona de reparto.
- new_zone {district, fee}: alta de un distrito de reparto.
- set_promotion {code, percent?, is_active?, first_order_only?}: editar una promocion existente.
- set_option_item {option_item_id, name?, price?, is_active?}: editar una opcion (extra).
- new_option_item {group_id, name, price}: alta de una opcion dentro de un grupo.
- set_option_group {group_id, name?, is_active?, ...}: editar un grupo de opciones.
- assign_groups {product_id, group_ids}: reemplazar los grupos asignados a un plato.
- none {reply}: charla, no se puede, o requiere revision de codigo.

Siempre respondes llamando a la herramienta emitir_propuesta.
"""


def _build_context_block(context: dict[str, Any]) -> str:
    """Serializa el contexto del negocio como JSON legible para el modelo."""
    return json.dumps(context, ensure_ascii=False, indent=2, default=str)


def generate_proposal(
    messages: list[dict[str, str]],
    context: dict[str, Any],
    *,
    api_key: str,
    client: httpx.Client | None = None,
) -> LLMProposal:
    """Pide al modelo UNA propuesta a partir de la conversacion y el contexto.

    No valida ids ni rangos: eso es del endpoint, contra la base real. Aca solo
    se arma el pedido, se llama a la API y se extrae el tool_use. Cualquier fallo
    (red, timeout, formato inesperado) sube como AssistantLLMError para que el
    endpoint lo traduzca a un 502/error claro en vez de un 500 pelado.
    """
    context_block = _build_context_block(context)
    convo: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                "CONTEXTO DEL NEGOCIO (solo lectura, ids reales):\n"
                f"{context_block}\n\n"
                "CONVERSACION con el dueno/admin (usa el ultimo mensaje como pedido):\n"
                + "\n".join(f"{m['role']}: {m['content']}" for m in messages)
            ),
        }
    ]

    payload = {
        "model": _MODEL,
        "max_tokens": _MAX_TOKENS,
        "system": _SYSTEM_PROMPT,
        "tools": [_TOOL],
        "tool_choice": {"type": "tool", "name": "emitir_propuesta"},
        "messages": convo,
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _API_VERSION,
        "content-type": "application/json",
    }

    owns_client = client is None
    client = client or httpx.Client(timeout=_TIMEOUT_S)
    try:
        response = client.post(_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        # No filtramos el detalle de la API hacia afuera: al log el porque,
        # al endpoint una senal generica.
        logger.warning("Fallo al llamar a la API del asistente: %s", exc)
        raise AssistantLLMError("El asistente no pudo responder.") from exc
    finally:
        if owns_client:
            client.close()

    return _parse_response(data)


def _parse_response(data: dict[str, Any]) -> LLMProposal:
    """Extrae el tool_use `emitir_propuesta` del cuerpo de la respuesta."""
    for block in data.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "emitir_propuesta":
            payload = block.get("input") or {}
            reply = payload.get("reply")
            if not isinstance(reply, str) or not reply.strip():
                raise AssistantLLMError("El asistente respondio sin texto.")
            action = payload.get("action")
            if action is not None and not isinstance(action, dict):
                raise AssistantLLMError("El asistente respondio una accion mal formada.")
            summary = payload.get("summary")
            if summary is not None and not isinstance(summary, str):
                summary = None
            return LLMProposal(reply=reply.strip(), action=action, summary=summary)
    raise AssistantLLMError("El asistente no devolvio una propuesta.")
