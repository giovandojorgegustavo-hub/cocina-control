"""Endpoint de salud — contrato de fabrica (docs/salud-endpoint.md).

Devuelve `status` y `commit`. Sin `commit`, `scripts/deploy.sh` no puede
confirmar que el proceso vivo corre lo que se acaba de desplegar, y falla el
deploy. Ese campo cubre el caso "systemd reinicio pero el WorkingDirectory
apunta a otro checkout".

POR QUE NO SE USA `git rev-parse`
---------------------------------
El release rsyncea el arbol del tag EXCLUYENDO `.git/`, asi que el checkout de
`/opt/cocina-control` se queda en el commit del ultimo bootstrap y no avanza
con los despliegues. `git rev-parse HEAD` ahi devuelve un SHA real pero
equivocado — que es peor que no devolver ninguno: el deploy pasaria la
verificacion creyendo que corre codigo que no corre.

La fuente es un archivo de metadata que escribe el propio despliegue, con la
variable de entorno como alternativa para entornos que la inyecten.

SE RESUELVE UNA SOLA VEZ, al importar el modulo (arranque del proceso). Si se
resolviera por request, un archivo cambiado bajo los pies haria que el
endpoint reporte algo distinto de lo que el proceso realmente tiene cargado.
"""

import os
import re
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# Nombre del archivo que el paso de despliegue deja en el directorio de trabajo.
_COMMIT_FILE = "COMMIT"

# SHA completo: 40 hex. El contrato lo exige asi, y validarlo evita publicar
# como "commit" cualquier basura que quedara en el archivo.
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Valor cuando no se pudo resolver. Explicito a proposito: deploy.sh compara el
# commit desplegado contra este campo, y una cadena que nunca va a coincidir
# hace fallar el deploy en vez de darlo por bueno.
_UNKNOWN = "unknown"


def _resolve_commit() -> str:
    """Resuelve el SHA del codigo que corre. Solo se llama al importar."""
    from_env = os.environ.get("APP_COMMIT", "").strip()
    if _SHA_RE.match(from_env):
        return from_env

    try:
        from_file = Path(_COMMIT_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return _UNKNOWN

    return from_file if _SHA_RE.match(from_file) else _UNKNOWN


APP_COMMIT = _resolve_commit()


class HealthResponse(BaseModel):
    status: str
    commit: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok", commit=APP_COMMIT)
