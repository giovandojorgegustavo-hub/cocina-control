"""Pydantic schemas del pedido de venta y sus pagos.

REGLA QUE ATRAVIESA TODO ESTE ARCHIVO: el cliente NUNCA manda precios.

Ni unit_price, ni line_total, ni delivery_fee, ni total. El servidor los busca
en products.sale_price y en delivery_zones y hace la cuenta. Si el importe
viajara en el request, quien tenga el token del asistente podria crear un pedido
de dos bowls por S/ 1 y la base lo aceptaria feliz: todos los CHECK cuadran,
porque 1 = 1 + 0. El unico modo de que el total sea confiable es que el cliente
no participe en calcularlo.

Un descuento tampoco viaja como importe. Lo que viaja es promo_code, un texto
que el servidor valida contra promotions y convierte en porcentaje. El bot dice
QUE el cliente pidio el descuento; cuanto vale lo decide la base.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SalesOrderChannel(StrEnum):
    whatsapp = "whatsapp"
    web = "web"
    rappi = "rappi"
    pedidosya = "pedidosya"
    phone = "phone"


class SalesOrderStatus(StrEnum):
    draft = "draft"
    confirmed = "confirmed"
    in_kitchen = "in_kitchen"
    dispatched = "dispatched"
    delivered = "delivered"
    cancelled = "cancelled"


class PaymentMethod(StrEnum):
    yape = "yape"
    plin = "plin"
    cash = "cash"
    bank_transfer = "bank_transfer"
    card = "card"


class PaymentStatus(StrEnum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class CustomerIn(BaseModel):
    phone: Annotated[str, Field(min_length=9, max_length=16)]
    name: Annotated[str | None, Field(default=None, max_length=120)]

    @field_validator("phone")
    @classmethod
    def _e164(cls, value: str) -> str:
        """Normalise to +51999999999 and reject anything else.

        Se acepta el numero sin el + y se lo agrega, porque personas.json y media
        operacion lo guardan asi. Lo que NO se acepta es guardarlo sin el: Meta
        rechaza esos envios con (#131009) y el cliente nunca recibe su
        confirmacion. Normalizar aca es mas barato que descubrirlo despues.
        """
        cleaned = "".join(ch for ch in value.strip() if not ch.isspace())
        cleaned = cleaned.replace("-", "").replace("(", "").replace(")", "")
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        digits = cleaned[1:]
        if not digits.isdigit() or not (8 <= len(digits) <= 15):
            raise ValueError("phone must be an international number, e.g. +51987654321")
        return cleaned


class AddressIn(BaseModel):
    district: Annotated[str, Field(min_length=2, max_length=120)]
    address_line: Annotated[str, Field(min_length=3, max_length=255)]
    reference: Annotated[str | None, Field(default=None, max_length=255)]


class SalesOrderItemOptionIn(BaseModel):
    """Modificador de una linea: crema, proteina extra, "sin palta".

    price_delta NO viaja: si la opcion nombra un producto del catalogo, su
    importe sale de products.sale_price; si no lo nombra, es una preferencia y
    no cuesta nada.
    """

    option_group: Annotated[str, Field(min_length=1, max_length=60)]
    option_name: Annotated[str, Field(min_length=1, max_length=120)]
    product_id: uuid.UUID | None = None


class SalesOrderItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: Annotated[int, Field(gt=0, le=99)]
    notes: Annotated[str | None, Field(default=None, max_length=255)]
    options: list[SalesOrderItemOptionIn] = Field(default_factory=list)


class SalesOrderCreate(BaseModel):
    customer: CustomerIn
    address: AddressIn
    items: Annotated[list[SalesOrderItemIn], Field(min_length=1)]
    channel: SalesOrderChannel = SalesOrderChannel.whatsapp
    notes: Annotated[str | None, Field(default=None, max_length=1000)]
    conversation_ref: Annotated[str | None, Field(default=None, max_length=120)]
    # Codigo de promotions, nunca un importe. Ver la regla al inicio del archivo.
    promo_code: Annotated[str | None, Field(default=None, min_length=1, max_length=40)]


class PaymentCreate(BaseModel):
    """Registro de un pago. Nace SIEMPRE pending.

    No hay campo status: el asistente no puede elegirlo. Verificar es otro acto,
    otro endpoint y otro rol.
    """

    method: PaymentMethod
    amount: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]
    proof_url: Annotated[str | None, Field(default=None, max_length=500)]


class PaymentReject(BaseModel):
    reason: Annotated[str, Field(min_length=3, max_length=255)]


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class MenuItemResponse(BaseModel):
    """Un plato de la carta con su precio de lista y el que se cobra.

    sale_price es el precio de lista; final_price ya tiene aplicado
    discount_percent. El asistente muestra los dos cuando hay descuento y
    cobra final_price — pero no lo manda: el servidor lo recalcula al crear
    el pedido.
    """

    id: uuid.UUID
    name: str
    sale_price: Decimal
    discount_percent: Decimal
    final_price: Decimal


class SalesOrderItemOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    option_group: str
    option_name: str
    price_delta: Decimal


class SalesOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    notes: str | None = None
    options: list[SalesOrderItemOptionResponse] = Field(default_factory=list)


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sales_order_id: uuid.UUID
    method: PaymentMethod
    amount: Decimal
    status: PaymentStatus
    proof_url: str | None = None
    verified_at: datetime | None = None
    rejected_reason: str | None = None
    created_at: datetime


class SalesOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: SalesOrderStatus
    channel: SalesOrderChannel
    customer_phone: str
    customer_name: str | None = None
    district: str
    address_line: str
    reference: str | None = None
    items_total: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    promo_code: str | None = None
    delivery_fee: Decimal
    total: Decimal
    notes: str | None = None
    conversation_ref: str | None = None
    created_at: datetime
    items: list[SalesOrderItemResponse] = Field(default_factory=list)
    payments: list[PaymentResponse] = Field(default_factory=list)
