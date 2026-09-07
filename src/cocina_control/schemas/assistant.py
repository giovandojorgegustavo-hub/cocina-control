"""Schemas del asistente del panel.

El request es una conversacion; la respuesta es UNA propuesta que el frontend
muestra para que un humano confirme. La respuesta nunca es una escritura: es la
descripcion de un cambio (que endpoint, que parametros, que resumen). Ver
api/assistant.py para la frontera de seguridad.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class AssistantMessage(BaseModel):
    """Un turno de la conversacion. role viene del cliente y se acota aca."""

    role: Literal["user", "assistant"]
    content: Annotated[str, Field(min_length=1, max_length=4000)]


class AssistantProposeRequest(BaseModel):
    # Un tope de mensajes: la conversacion del panel es corta y acotarla evita
    # que un cliente infle el prompt (y el costo) sin limite.
    messages: Annotated[list[AssistantMessage], Field(min_length=1, max_length=40)]


class AssistantProposeResponse(BaseModel):
    """Lo que ve el frontend: texto, una propuesta opcional y su resumen.

    proposal es un dict con `type` de la lista permitida y los parametros ya
    validados contra la base. null significa "no hay accion" (charla, no se
    puede, o el id no existe). El frontend nunca deriva poder de aca: usa el
    `type` para elegir el hook de negocio que ya existe y lo llama con el token
    del usuario, solo tras un Confirmar.
    """

    reply: str
    proposal: dict[str, Any] | None = None
    summary: str | None = None
