"""Pedidos de venta, su carta y sus pagos.

Routes
------
GET  /api/v1/catalog/menu                  — carta con precios (lista y final)
POST /api/v1/sales-orders                  — crear pedido (asistente/owner/admin)
GET  /api/v1/sales-orders                  — bandeja, filtrable por estado
GET  /api/v1/sales-orders/{id}             — detalle
POST /api/v1/sales-orders/{id}/payments    — registrar pago (queda pending)
POST /api/v1/payments/{id}/verify          — FIRMAR el pago (owner/admin)
POST /api/v1/payments/{id}/reject          — rechazar el pago (owner/admin)

Invariants
----------
- El cliente NUNCA manda importes. Todo precio sale de products.sale_price y de
  delivery_zones, y la cuenta la hace el servidor. Ver schemas/sales_order.py.
- Un descuento tampoco es un importe que viaje: es un codigo (promo_code) que
  el servidor valida contra promotions, o un discount_percent que vive en el
  producto. El bot solo dice que el cliente lo pidio.
- Una opcion con precio tampoco: viaja option_item_id y el servidor copia el
  nombre y el precio desde option_items (migracion 0023), verificando que el
  grupo este asignado al plato y que se respeten sus reglas. El texto libre
  ({option_group, option_name}) sigue entrando para preferencias sin costo.
- Un pago nace pending y solo un humano con rol owner/admin puede verificarlo.
  La regla la sostiene ck_payments_verified_needs_human en la base, no este
  archivo.
- El telefono es la identidad del cliente: un pedido de un numero ya conocido
  reusa su fila en vez de duplicarla.
- El envio NO lo cobramos nosotros. El cliente yapea amount_due (productos
  menos descuento); delivery_fee es un estimado por zona que le decimos y que
  el motorizado cobra en mano al llegar. total sigue incluyendo el envio
  porque es el valor del pedido para margen y reportes. Las zonas activas
  siguen mandando: fuera de cobertura no hay pedido.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cocina_control.api.delivery_zones import find_zone
from cocina_control.api.deps import require_any_role
from cocina_control.api.option_groups import load_assigned_groups, menu_option_groups
from cocina_control.db import get_session
from cocina_control.models.customer import Customer, CustomerAddress
from cocina_control.models.option_group import SELECTION_SINGLE, OptionItem
from cocina_control.models.payment import Payment
from cocina_control.models.product import Product
from cocina_control.models.promotion import Promotion
from cocina_control.models.sales_order import (
    SalesOrder,
    SalesOrderItem,
    SalesOrderItemOption,
)
from cocina_control.models.user import User
from cocina_control.schemas.sales_order import (
    MenuItemResponse,
    PaymentCreate,
    PaymentReject,
    PaymentResponse,
    SalesOrderCreate,
    SalesOrderItemOptionIn,
    SalesOrderItemOptionResponse,
    SalesOrderItemResponse,
    SalesOrderResponse,
)

router = APIRouter(tags=["sales-orders"])

_CENTS = Decimal("0.01")

# Quien puede tomar un pedido. cocinero NO esta: un cocinero captura lo que sale
# de la cocina, no vende. Darle este permiso porque "total ya esta logueado"
# seria exactamente el error que el rol asistente_pedidos existe para evitar.
_CAN_TAKE_ORDERS = require_any_role("asistente_pedidos", "owner", "admin")
# Firmar un pago es del dueno. Nunca de un service token.
_CAN_SIGN_PAYMENTS = require_any_role("owner", "admin")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS)


def _discount_percent(product: Product) -> Decimal:
    """NULL y 0 significan lo mismo: sin descuento."""
    return _money(Decimal(product.discount_percent or 0))


def _final_price(product: Product) -> Decimal:
    """Precio que se cobra: lista menos el descuento del plato, a centavos.

    Se calcula y no se guarda: cambiar el descuento no obliga a recalcular
    nada, y lo cobrado en cada pedido ya queda congelado en unit_price.
    """
    list_price = _money(Decimal(product.sale_price))
    percent = _discount_percent(product)
    if percent <= 0:
        return list_price
    return _money(list_price * (1 - percent / 100))


# ---------------------------------------------------------------------------
# Carta
# ---------------------------------------------------------------------------


@router.get("/catalog/menu", response_model=list[MenuItemResponse])
def get_menu(
    session: Session = Depends(get_session),
    _user: User = Depends(_CAN_TAKE_ORDERS),
) -> list[MenuItemResponse]:
    """Platos vendibles con precio cargado.

    Quedan fuera dos grupos, por motivos distintos:

    - Sin sale_price: ofrecer algo que despues no se puede cotizar le pasa el
      problema al cliente cuando ya eligio.
    - Con sale_price = 0: son modificadores, no platos. Las salsas van incluidas
      ("1 salsa a eleccion") y llevan precio 0 porque una opcion que nombra un
      producto exige que ese producto tenga precio; dejarlas en NULL las haria
      irrepresentables como opcion. Pero listarlas en la carta le haria creer al
      asistente que puede ofrecer "Vinagreta, S/ 0" como si fuera un plato.

    Esto es un parche honesto sobre un hueco del modelo: products no distingue
    plato de modificador, y "precio cero" es la unica senal disponible hoy. La
    solucion de verdad es una marca explicita, y esta anotada como pendiente
    junto con la de plato fijo vs armable.
    """
    products = session.scalars(
        select(Product)
        .where(
            Product.is_active.is_(True),
            Product.is_sale.is_(True),
            Product.sale_price.is_not(None),
            Product.sale_price > 0,
        )
        .order_by(Product.name)
    ).all()
    # Una sola pasada por las tres tablas de opciones para toda la carta: el
    # asistente pide el menu en cada conversacion.
    option_groups = menu_option_groups(session, [p.id for p in products])
    return [
        MenuItemResponse(
            id=p.id,
            name=p.name,
            sale_price=_money(Decimal(p.sale_price)),
            discount_percent=_discount_percent(p),
            final_price=_final_price(p),
            option_groups=option_groups.get(p.id, []),
        )
        for p in products
    ]


# ---------------------------------------------------------------------------
# Helpers de armado
# ---------------------------------------------------------------------------


def _upsert_customer(session: Session, data, actor: User) -> Customer:
    """Reusa el cliente si el telefono ya existe. El numero es la cuenta."""
    customer = session.scalar(
        select(Customer).where(Customer.phone == data.phone)
    )
    if customer is None:
        customer = Customer(
            id=uuid.uuid4(),
            phone=data.phone,
            name=data.name,
            created_by=actor.id,
        )
        session.add(customer)
        session.flush()
    elif data.name and not customer.name:
        # Solo se completa lo que faltaba. Pisar un nombre ya cargado con el
        # perfil de WhatsApp del momento borraria una correccion humana.
        customer.name = data.name
        customer.updated_at = datetime.now(UTC)
        customer.updated_by = actor.id
    return customer


def _resolve_address(
    session: Session, customer: Customer, data, actor: User
) -> CustomerAddress:
    """Reusa la direccion si el cliente ya pidio ahi."""
    existing = session.scalars(
        select(CustomerAddress).where(CustomerAddress.customer_id == customer.id)
    ).all()
    for address in existing:
        same_district = address.district.strip().lower() == data.district.strip().lower()
        same_line = (
            address.address_line.strip().lower() == data.address_line.strip().lower()
        )
        if same_district and same_line:
            return address

    address = CustomerAddress(
        id=uuid.uuid4(),
        customer_id=customer.id,
        district=data.district.strip(),
        address_line=data.address_line.strip(),
        reference=data.reference,
        is_default=not existing,
        created_by=actor.id,
    )
    session.add(address)
    session.flush()
    return address


def _load_sale_product(session: Session, product_id: uuid.UUID) -> Product:
    product = session.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product {product_id} does not exist or is inactive",
        )
    if not product.is_sale:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product '{product.name}' is not a sale product",
        )
    if product.sale_price is None:
        # Un pedido con total incompleto es peor que un pedido que no se pudo
        # crear: el segundo se ve al instante, el primero recien al cobrar.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product '{product.name}' has no sale price loaded",
        )
    return product


def _resolve_promotion(
    session: Session, code: str | None, customer: Customer
) -> Promotion | None:
    """Valida el codigo que mando el bot. Los textos de error son contrato:
    el asistente los reconoce para explicarle al cliente que paso."""
    if code is None:
        return None
    promotion = session.get(Promotion, code)
    if promotion is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Promoción no encontrada.",
        )
    if not promotion.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Promoción no vigente.",
        )
    if promotion.first_order_only:
        # El cliente ya esta upserteado y el pedido nuevo todavia no: la
        # cuenta es exactamente "los pedidos anteriores de este telefono".
        # Un pedido cancelado no cuenta como compra.
        previous = session.scalar(
            select(func.count())
            .select_from(SalesOrder)
            .where(
                SalesOrder.customer_id == customer.id,
                SalesOrder.status != "cancelled",
            )
        )
        if previous:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El descuento de primera compra ya fue usado por este cliente.",
            )
    return promotion


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _build_options(
    session: Session, product: Product, options_in: list[SalesOrderItemOptionIn]
) -> tuple[list[SalesOrderItemOption], Decimal]:
    """Convierte las opciones del request en filas congeladas y suma sus extras.

    Dos caminos por opcion, y pueden convivir en el mismo item:

    - option_item_id (estructurado): la opcion tiene que estar activa y su
      grupo asignado al plato; el nombre del grupo, el de la opcion y el precio
      se copian desde el catalogo de opciones. El precio es el de la opcion
      aunque enlace un producto: lo que cuesta un adicional dentro de un bowl
      lo decide el grupo.
    - option_group + option_name (libre): preferencia sin costo, o un producto
      del catalogo con su precio. Es el camino anterior a 0023 y sigue entero.

    Las reglas de grupo (una sola, hasta N) se cuentan sobre las opciones
    estructuradas del item. Los grupos obligatorios se exigen SOLO cuando el
    item trae al menos un option_item_id: un pedido que llega todo en texto
    libre es el bot viejo, y no se le puede pedir que conozca grupos que no
    sabe nombrar. Los mensajes son contrato con el asistente, que los repite al
    cliente tal cual.
    """
    structured = [o for o in options_in if o.option_item_id is not None]
    assigned = load_assigned_groups(session, [product.id]).get(product.id, []) if structured else []
    groups_by_id = {group.id: group for group in assigned}
    chosen: dict[uuid.UUID, int] = defaultdict(int)

    options: list[SalesOrderItemOption] = []
    extras = Decimal("0.00")
    for option_in in options_in:
        if option_in.option_item_id is not None:
            item = session.get(OptionItem, option_in.option_item_id)
            if item is None or not item.is_active or item.group_id not in groups_by_id:
                raise _bad_request("La opción no corresponde a este plato.")
            group = groups_by_id[item.group_id]
            chosen[group.id] += 1
            limit = 1 if group.selection == SELECTION_SINGLE else group.max_choices
            if limit is not None and chosen[group.id] > limit:
                raise _bad_request(f"Elige como máximo {limit} en {group.name}.")
            delta = _money(Decimal(item.price))
            options.append(
                SalesOrderItemOption(
                    id=uuid.uuid4(),
                    order_item_id=None,  # se asigna tras el flush del item
                    product_id=item.product_id,
                    option_group=group.name,
                    option_name=item.name,
                    price_delta=delta,
                    option_item_id=item.id,
                )
            )
        else:
            if option_in.product_id is None:
                # Preferencia sin costo ("sin palta", "poco picante").
                delta = Decimal("0.00")
            else:
                option_product = _load_sale_product(session, option_in.product_id)
                delta = _final_price(option_product)
            options.append(
                SalesOrderItemOption(
                    id=uuid.uuid4(),
                    order_item_id=None,
                    product_id=option_in.product_id,
                    option_group=option_in.option_group,
                    option_name=option_in.option_name,
                    price_delta=delta,
                    option_item_id=None,
                )
            )
        extras += delta

    if structured:
        for group in assigned:
            if not group.required:
                continue
            minimum = max(group.min_choices, 1)
            count = chosen.get(group.id, 0)
            if count == 0:
                raise _bad_request(f"Falta elegir en {group.name}.")
            if count < minimum:
                raise _bad_request(f"Elige al menos {minimum} en {group.name}.")

    return options, extras


# ---------------------------------------------------------------------------
# Pedido
# ---------------------------------------------------------------------------


@router.post(
    "/sales-orders",
    response_model=SalesOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_sales_order(
    payload: SalesOrderCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(_CAN_TAKE_ORDERS),
) -> SalesOrderResponse:
    zone = find_zone(session, payload.address.district)
    if zone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No delivery coverage for district '{payload.address.district}'",
        )

    customer = _upsert_customer(session, payload.customer, actor)
    address = _resolve_address(session, customer, payload.address, actor)
    # Antes de session.add(order): la promo de primera compra cuenta los
    # pedidos previos del cliente, y este todavia no tiene que estar.
    promotion = _resolve_promotion(session, payload.promo_code, customer)

    order = SalesOrder(
        id=uuid.uuid4(),
        customer_id=customer.id,
        address_id=address.id,
        channel=payload.channel.value,
        status="confirmed",
        items_total=Decimal("0.00"),
        discount_percent=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        promo_code=promotion.code if promotion else None,
        delivery_fee=_money(zone.fee),
        total=_money(zone.fee),
        notes=payload.notes,
        conversation_ref=payload.conversation_ref,
        created_by=actor.id,
    )
    session.add(order)
    session.flush()

    items_total = Decimal("0.00")
    built: list[tuple[SalesOrderItem, Product, list[SalesOrderItemOption]]] = []

    for item_in in payload.items:
        product = _load_sale_product(session, item_in.product_id)
        unit_price = _final_price(product)

        options, extras = _build_options(session, product, item_in.options)

        line_total = _money((unit_price + extras) * item_in.quantity)
        items_total += line_total

        item = SalesOrderItem(
            id=uuid.uuid4(),
            sales_order_id=order.id,
            product_id=product.id,
            quantity=item_in.quantity,
            unit_price=unit_price,
            line_total=line_total,
            notes=item_in.notes,
        )
        session.add(item)
        built.append((item, product, options))

    session.flush()
    for item, _product, options in built:
        for option in options:
            option.order_item_id = item.id
            session.add(option)

    order.items_total = _money(items_total)
    if promotion is not None:
        order.discount_percent = _money(Decimal(promotion.percent))
        order.discount_amount = _money(order.items_total * order.discount_percent / 100)
    order.total = _money(order.items_total - order.discount_amount + order.delivery_fee)
    session.commit()
    session.refresh(order)

    return _order_response(session, order)


def _order_response(session: Session, order: SalesOrder) -> SalesOrderResponse:
    customer = session.get(Customer, order.customer_id)
    address = session.get(CustomerAddress, order.address_id) if order.address_id else None

    items = session.scalars(
        select(SalesOrderItem).where(SalesOrderItem.sales_order_id == order.id)
    ).all()
    payments = session.scalars(
        select(Payment)
        .where(Payment.sales_order_id == order.id)
        .order_by(Payment.created_at)
    ).all()

    item_responses: list[SalesOrderItemResponse] = []
    for item in items:
        product = session.get(Product, item.product_id)
        options = session.scalars(
            select(SalesOrderItemOption).where(
                SalesOrderItemOption.order_item_id == item.id
            )
        ).all()
        item_responses.append(
            SalesOrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=product.name if product else "(producto eliminado)",
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
                notes=item.notes,
                options=[
                    SalesOrderItemOptionResponse(
                        option_group=o.option_group,
                        option_name=o.option_name,
                        price_delta=o.price_delta,
                        option_item_id=o.option_item_id,
                    )
                    for o in options
                ],
            )
        )

    return SalesOrderResponse(
        id=order.id,
        status=order.status,
        channel=order.channel,
        customer_phone=customer.phone if customer else "",
        customer_name=customer.name if customer else None,
        district=address.district if address else "",
        address_line=address.address_line if address else "",
        reference=address.reference if address else None,
        items_total=order.items_total,
        discount_percent=order.discount_percent,
        discount_amount=order.discount_amount,
        promo_code=order.promo_code,
        delivery_fee=order.delivery_fee,
        total=order.total,
        # Se recalcula aca y no se persiste: es una vista de dos columnas que ya
        # estan en la fila, y asi ningun pedido viejo queda sin el dato.
        amount_due=_money(Decimal(order.items_total) - Decimal(order.discount_amount)),
        delivery_fee_payment="on_arrival",
        notes=order.notes,
        conversation_ref=order.conversation_ref,
        created_at=order.created_at,
        items=item_responses,
        payments=[PaymentResponse.model_validate(p) for p in payments],
    )


@router.get("/sales-orders", response_model=list[SalesOrderResponse])
def list_sales_orders(
    session: Session = Depends(get_session),
    _actor: User = Depends(_CAN_TAKE_ORDERS),
    order_status: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[SalesOrderResponse]:
    query = select(SalesOrder).order_by(SalesOrder.created_at.desc()).limit(limit)
    if order_status:
        query = query.where(SalesOrder.status == order_status)
    return [_order_response(session, o) for o in session.scalars(query).all()]


@router.get("/sales-orders/{order_id}", response_model=SalesOrderResponse)
def get_sales_order(
    order_id: uuid.UUID,
    session: Session = Depends(get_session),
    _actor: User = Depends(_CAN_TAKE_ORDERS),
) -> SalesOrderResponse:
    order = session.get(SalesOrder, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sales order not found"
        )
    return _order_response(session, order)


# ---------------------------------------------------------------------------
# Pagos
# ---------------------------------------------------------------------------


@router.post(
    "/sales-orders/{order_id}/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_payment(
    order_id: uuid.UUID,
    payload: PaymentCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(_CAN_TAKE_ORDERS),
) -> Payment:
    """Registra un pago. Nace pending, siempre.

    El asistente puede llegar hasta aca y ni un paso mas. No hay parametro que
    le permita marcarlo verificado.
    """
    order = session.get(SalesOrder, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sales order not found"
        )

    payment = Payment(
        id=uuid.uuid4(),
        sales_order_id=order.id,
        method=payload.method.value,
        amount=_money(payload.amount),
        status="pending",
        proof_url=payload.proof_url,
        proof_at=datetime.now(UTC) if payload.proof_url else None,
        created_by=actor.id,
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment


@router.post("/payments/{payment_id}/verify", response_model=PaymentResponse)
def verify_payment(
    payment_id: uuid.UUID,
    session: Session = Depends(get_session),
    actor: User = Depends(_CAN_SIGN_PAYMENTS),
) -> Payment:
    """Firma un pago: la plata llego.

    Exige owner o admin. Un service token nunca llega hasta aca — ni siquiera si
    manda X-Act-As apuntando a un owner, porque ACT_AS_ALLOWED_ROLES no incluye
    owner y ese camino devuelve 401.
    """
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        )
    if payment.status == "verified":
        return payment
    if payment.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A rejected payment cannot be verified; register a new one",
        )

    payment.status = "verified"
    payment.verified_at = datetime.now(UTC)
    payment.verified_by = actor.id
    session.commit()
    session.refresh(payment)
    return payment


@router.post("/payments/{payment_id}/reject", response_model=PaymentResponse)
def reject_payment(
    payment_id: uuid.UUID,
    payload: PaymentReject,
    session: Session = Depends(get_session),
    _actor: User = Depends(_CAN_SIGN_PAYMENTS),
) -> Payment:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        )
    if payment.status == "verified":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A verified payment cannot be rejected",
        )

    payment.status = "rejected"
    payment.rejected_reason = payload.reason
    session.commit()
    session.refresh(payment)
    return payment
