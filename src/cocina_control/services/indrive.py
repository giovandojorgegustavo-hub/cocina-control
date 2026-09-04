"""Lectura de un link de rastreo de inDrive.

Un link `https://sharetrip.indrive.com/delivery/cust/{a}/{token}` se lee como
JSON insertando `/proxy/share/api/v2/share` antes del path. Sin token, sin
cookie, sin navegador: **el link ES la credencial**. La plantilla esta en el
bundle publico de sharetrip, asi que aplica a cualquier link de delivery.

QUE SE GUARDA Y QUE NO
----------------------
Del payload solo se toman el ESTADO y el COSTO. El resto trae datos personales
de quien reparte — nombre, telefono, foto y GPS en vivo — y almacenar eso es
tratamiento de datos personales de un tercero bajo la Ley 29733. Leerlo de paso
para el pedido propio es una cosa; guardarlo es otra.

EL ETA NO SIRVE
---------------
`arrival_time_to_active_point_m` SE CONGELA: al momento de la llegada seguia
diciendo 30 minutos. Cualquier logica de "ya llego" basada en el ETA es falsa.
La senal real es `status`.

LIMITES
-------
Es un endpoint interno de inDrive, no una API publica: no hay contrato de
estabilidad ni rate limit conocido. Por eso esta funcion NUNCA levanta: si algo
sale mal devuelve lo que pudo y el viaje se registra igual. Un reparto no se
bloquea porque un tercero cambio su JSON.
"""

import json
import logging
import re
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_HOST = "sharetrip.indrive.com"
_PREFIJO_PROXY = "/proxy/share/api/v2/share"
_TIMEOUT_S = 8.0

# Claves donde inDrive ha puesto el monto. Se prueban en orden y se toma la
# primera que rinda un numero. Es una lista y no una clave fija porque el
# payload es de un tercero: cuando cambie, se suma un nombre acá en vez de
# quedarse sin costo en silencio.
_CLAVES_COSTO = ("price", "total_price", "amount", "cost", "fare", "value")


class ViajeLeido:
    def __init__(self, status: str | None, cost: Decimal | None, ok: bool):
        self.status = status
        self.cost = cost
        self.ok = ok


def url_de_api(tracking_url: str) -> str | None:
    """Convierte el link que ve una persona en el que devuelve JSON."""
    p = urlparse(tracking_url)
    if p.scheme != "https" or p.netloc != _HOST or not p.path.startswith("/"):
        return None
    if p.path.startswith(_PREFIJO_PROXY):
        return tracking_url
    return f"https://{_HOST}{_PREFIJO_PROXY}{p.path}"


def _buscar_costo(nodo: Any, profundidad: int = 0) -> Decimal | None:
    """Busca el monto recorriendo el payload, sin asumir su forma exacta."""
    if profundidad > 6 or not isinstance(nodo, (dict, list)):
        return None
    if isinstance(nodo, list):
        for x in nodo:
            hallado = _buscar_costo(x, profundidad + 1)
            if hallado is not None:
                return hallado
        return None
    for clave in _CLAVES_COSTO:
        if clave in nodo:
            crudo = nodo[clave]
            if isinstance(crudo, dict):
                crudo = crudo.get("amount") or crudo.get("value")
            if isinstance(crudo, (int, float)):
                return Decimal(str(crudo))
            if isinstance(crudo, str):
                limpio = re.sub(r"[^\d.]", "", crudo)
                try:
                    if limpio:
                        return Decimal(limpio)
                except InvalidOperation:
                    pass
    for v in nodo.values():
        hallado = _buscar_costo(v, profundidad + 1)
        if hallado is not None:
            return hallado
    return None


def leer_viaje(tracking_url: str) -> ViajeLeido:
    """Lee estado y costo del viaje. Nunca levanta."""
    api = url_de_api(tracking_url)
    if api is None:
        logger.warning("indrive: el link no tiene la forma esperada")
        return ViajeLeido(None, None, False)
    # Se usa urllib de la biblioteca estandar a proposito: httpx vive en
    # optional-dependencies.dev, o sea que existe en los tests y NO en el venv
    # de produccion. Importarlo desde codigo de runtime tumbo el servicio
    # entero con ModuleNotFoundError. Una dependencia de test no puede estar en
    # el camino de arranque de la aplicacion.
    try:
        peticion = urllib.request.Request(api, headers={"Accept": "application/json"})
        with urllib.request.urlopen(peticion, timeout=_TIMEOUT_S) as respuesta:  # noqa: S310
            if respuesta.status != 200:
                logger.warning("indrive: respondio %s", respuesta.status)
                return ViajeLeido(None, None, False)
            data = json.loads(respuesta.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — un tercero caido no rompe el reparto
        logger.warning("indrive: no se pudo leer el link (%s)", type(exc).__name__)
        return ViajeLeido(None, None, False)

    entrega = data.get("delivery") if isinstance(data, dict) else None
    status = None
    if isinstance(entrega, dict):
        status = entrega.get("status")
    if status is None and isinstance(data, dict):
        status = data.get("status")

    costo = _buscar_costo(data)
    if costo is None:
        # Se deja rastro de las claves para poder sumar el nombre nuevo a
        # _CLAVES_COSTO en vez de descubrirlo por casualidad meses despues.
        claves = sorted(data.keys())[:12] if isinstance(data, dict) else []
        logger.warning("indrive: no encontre el costo. claves del payload: %s", claves)

    return ViajeLeido(str(status) if status is not None else None, costo, True)
