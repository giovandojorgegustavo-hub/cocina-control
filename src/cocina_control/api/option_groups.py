"""Extras y opciones de plato: grupos, opciones con precio y asignacion.

Routes
------
GET   /api/v1/option-groups                    — grupos con sus opciones;
                                                 ?all=true incluye apagados
POST  /api/v1/option-groups                    — alta de grupo
PATCH /api/v1/option-groups/{id}               — nombre, reglas, activo
POST  /api/v1/option-groups/{id}/items         — alta de opcion
PATCH /api/v1/option-items/{id}                — nombre, precio, activa
GET   /api/v1/products/{id}/option-groups      — grupos asignados a un plato
PUT   /api/v1/products/{id}/option-groups      — reemplaza la asignacion

Todo es de owner/admin. El asistente de WhatsApp y la carta no leen de aca:
leen de /catalog/menu, que ya trae los grupos activos de cada plato.

Invariants
----------
- Un grupo 'single' tiene max_choices = 1; uno obligatorio tiene
  min_choices >= 1; y min <= max cuando hay max. Las tres reglas se evaluan
  sobre el grupo ya mezclado con el PATCH, no sobre el body, y devuelven 422.
- Una opcion se repite por nombre dentro del grupo sin distinguir caja: dos
  "Tilapia" son la misma escrita dos veces (409).
- No hay DELETE. Un grupo o una opcion que deja de ofrecerse se apaga: los
  pedidos viejos apuntan a la fila y el panel puede volver a encenderla.
- El precio de una opcion enlazada a un producto es el de la opcion, no el
  del producto: lo que cuesta un adicional dentro de un bowl lo decide el
  grupo. Ver models/option_group.py.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cocina_control.api.deps import require_any_role
from cocina_control.db import get_session
from cocina_control.models.option_group import (
    SELECTION_SINGLE,
    OptionGroup,
    OptionItem,
    ProductOptionGroup,
)
from cocina_control.models.product import Product
from cocina_control.models.user import User
from cocina_control.schemas.option_group import (
    MenuOptionGroupResponse,
    MenuOptionResponse,
    OptionGroupCreate,
    OptionGroupResponse,
    OptionGroupUpdate,
    OptionItemCreate,
    OptionItemResponse,
    OptionItemUpdate,
    ProductOptionGroupResponse,
    ProductOptionGroupsPut,
)

router = APIRouter(tags=["option-groups"])

_CAN_EDIT = require_any_role("owner", "admin")
_CENTS = Decimal("0.01")


# ---------------------------------------------------------------------------
# Reglas entre campos de un grupo
# ---------------------------------------------------------------------------


def _apply_group_rules(
    *, selection: str, required: bool, min_choices: int | None, max_choices: int | None
) -> tuple[int, int | None]:
    """Devuelve (min_choices, max_choices) coherentes o lanza 422.

    - 'single' es "elige una": max_choices queda en 1; cualquier otro valor
      explicito es una contradiccion, no un dato.
    - Obligatorio sin minimo es "al menos una": min_choices sube a 1.
    - Un minimo mayor que el maximo no se puede cumplir nunca.
    """
    if selection == SELECTION_SINGLE:
        if max_choices not in (None, 1):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Un grupo de una sola opción tiene máximo 1.",
            )
        max_choices = 1
    minimum = min_choices if min_choices is not None else 0
    if required and minimum < 1:
        minimum = 1
    if max_choices is not None and minimum > max_choices:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El mínimo no puede ser mayor que el máximo.",
        )
    return minimum, max_choices


# ---------------------------------------------------------------------------
# Lecturas compartidas con /catalog/menu y /sales-orders
# ---------------------------------------------------------------------------


def _active_items_by_group(
    session: Session, group_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[OptionItem]]:
    ids = list(group_ids)
    if not ids:
        return {}
    items = session.scalars(
        select(OptionItem)
        .where(OptionItem.group_id.in_(ids), OptionItem.is_active.is_(True))
        .order_by(OptionItem.sort_order, OptionItem.name)
    ).all()
    grouped: dict[uuid.UUID, list[OptionItem]] = defaultdict(list)
    for item in items:
        grouped[item.group_id].append(item)
    return grouped


def load_assigned_groups(
    session: Session, product_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[OptionGroup]]:
    """Grupos ACTIVOS asignados a cada plato, en el orden de la asignacion."""
    ids = list(product_ids)
    if not ids:
        return {}
    rows = session.execute(
        select(ProductOptionGroup.product_id, OptionGroup)
        .join(OptionGroup, OptionGroup.id == ProductOptionGroup.group_id)
        .where(
            ProductOptionGroup.product_id.in_(ids),
            OptionGroup.is_active.is_(True),
        )
        .order_by(ProductOptionGroup.sort_order, OptionGroup.sort_order, OptionGroup.name)
    ).all()
    assigned: dict[uuid.UUID, list[OptionGroup]] = defaultdict(list)
    for product_id, group in rows:
        assigned[product_id].append(group)
    return assigned


def menu_option_groups(
    session: Session, product_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[MenuOptionGroupResponse]]:
    """Lo que la carta expone por plato: grupos activos con opciones activas."""
    assigned = load_assigned_groups(session, product_ids)
    group_ids = {group.id for groups in assigned.values() for group in groups}
    items = _active_items_by_group(session, group_ids)
    result: dict[uuid.UUID, list[MenuOptionGroupResponse]] = {}
    for product_id, groups in assigned.items():
        result[product_id] = [
            MenuOptionGroupResponse(
                id=group.id,
                name=group.name,
                selection=group.selection,
                required=group.required,
                min_choices=group.min_choices,
                max_choices=group.max_choices,
                options=[
                    MenuOptionResponse(id=item.id, name=item.name, price=item.price)
                    for item in items.get(group.id, [])
                ],
            )
            for group in groups
        ]
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_group_or_404(session: Session, group_id: uuid.UUID) -> OptionGroup:
    group = session.get(OptionGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Option group not found")
    return group


def _get_item_or_404(session: Session, item_id: uuid.UUID) -> OptionItem:
    item = session.get(OptionItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Option item not found")
    return item


def _get_sale_product_or_400(session: Session, product_id: uuid.UUID) -> Product:
    product = session.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    if not product.is_sale:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product '{product.name}' is not a sale product",
        )
    return product


def _assert_item_name_free(
    session: Session, group_id: uuid.UUID, name: str, *, exclude_id: uuid.UUID | None = None
) -> None:
    stmt = select(OptionItem).where(
        OptionItem.group_id == group_id,
        func.lower(OptionItem.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(OptionItem.id != exclude_id)
    existing = session.scalars(stmt).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Option '{existing.name}' already exists in this group",
        )


def _group_response(group: OptionGroup, items: list[OptionItem]) -> OptionGroupResponse:
    return OptionGroupResponse(
        id=group.id,
        name=group.name,
        selection=group.selection,
        required=group.required,
        min_choices=group.min_choices,
        max_choices=group.max_choices,
        sort_order=group.sort_order,
        is_active=group.is_active,
        updated_at=group.updated_at,
        items=[OptionItemResponse.model_validate(item) for item in items],
    )


def _group_with_items(session: Session, group: OptionGroup) -> OptionGroupResponse:
    items = session.scalars(
        select(OptionItem)
        .where(OptionItem.group_id == group.id)
        .order_by(OptionItem.sort_order, OptionItem.name)
    ).all()
    return _group_response(group, list(items))


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------


@router.get("/option-groups", response_model=list[OptionGroupResponse])
def list_option_groups(
    all: bool = Query(default=False, description="Incluir grupos y opciones apagados"),
    session: Session = Depends(get_session),
    _actor: User = Depends(_CAN_EDIT),
) -> list[OptionGroupResponse]:
    """Todos los grupos con sus opciones.

    Sin ?all solo lo activo, que es lo mismo que ve el asistente. Con ?all
    tambien lo apagado: el panel es el unico lugar desde donde se vuelve a
    encender un grupo, asi que es el unico que necesita verlo.
    """
    groups_query = select(OptionGroup)
    items_query = select(OptionItem)
    if not all:
        groups_query = groups_query.where(OptionGroup.is_active.is_(True))
        items_query = items_query.where(OptionItem.is_active.is_(True))
    groups = session.scalars(
        groups_query.order_by(OptionGroup.sort_order, OptionGroup.name)
    ).all()
    items = session.scalars(items_query.order_by(OptionItem.sort_order, OptionItem.name)).all()
    by_group: dict[uuid.UUID, list[OptionItem]] = defaultdict(list)
    for item in items:
        by_group[item.group_id].append(item)
    return [_group_response(group, by_group.get(group.id, [])) for group in groups]


@router.post(
    "/option-groups", response_model=OptionGroupResponse, status_code=status.HTTP_201_CREATED
)
def create_option_group(
    body: OptionGroupCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(_CAN_EDIT),
) -> OptionGroupResponse:
    minimum, maximum = _apply_group_rules(
        selection=body.selection.value,
        required=body.required,
        min_choices=body.min_choices,
        max_choices=body.max_choices,
    )
    group = OptionGroup(
        id=uuid.uuid4(),
        name=body.name,
        selection=body.selection.value,
        required=body.required,
        min_choices=minimum,
        max_choices=maximum,
        sort_order=body.sort_order,
        is_active=True,
        created_by=actor.id,
    )
    session.add(group)
    session.flush()
    return _group_response(group, [])


@router.patch("/option-groups/{group_id}", response_model=OptionGroupResponse)
def update_option_group(
    group_id: uuid.UUID,
    body: OptionGroupUpdate,
    session: Session = Depends(get_session),
    actor: User = Depends(_CAN_EDIT),
) -> OptionGroupResponse:
    group = _get_group_or_404(session, group_id)

    # Las reglas se evaluan sobre el resultado de mezclar el body con lo que
    # hay: pasar a 'single' con max 5 guardado tiene que fallar igual que
    # crearlo asi.
    selection = body.selection.value if body.selection is not None else group.selection
    required = body.required if body.required is not None else group.required
    minimum, maximum = _apply_group_rules(
        selection=selection,
        required=required,
        min_choices=body.min_choices if body.min_choices is not None else group.min_choices,
        max_choices=(
            body.max_choices
            if body.max_choices is not None
            else (group.max_choices if selection == group.selection else None)
        ),
    )

    if body.name is not None:
        group.name = body.name
    group.selection = selection
    group.required = required
    group.min_choices = minimum
    group.max_choices = maximum
    if body.sort_order is not None:
        group.sort_order = body.sort_order
    if body.is_active is not None:
        group.is_active = body.is_active
    group.updated_at = datetime.now(UTC)
    group.updated_by = actor.id
    session.flush()
    return _group_with_items(session, group)


# ---------------------------------------------------------------------------
# Opciones
# ---------------------------------------------------------------------------


@router.post(
    "/option-groups/{group_id}/items",
    response_model=OptionItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_option_item(
    group_id: uuid.UUID,
    body: OptionItemCreate,
    session: Session = Depends(get_session),
    _actor: User = Depends(_CAN_EDIT),
) -> OptionItem:
    group = _get_group_or_404(session, group_id)
    _assert_item_name_free(session, group.id, body.name)
    if body.product_id is not None:
        _get_sale_product_or_400(session, body.product_id)

    item = OptionItem(
        id=uuid.uuid4(),
        group_id=group.id,
        name=body.name,
        price=body.price.quantize(_CENTS),
        product_id=body.product_id,
        sort_order=body.sort_order,
        is_active=True,
    )
    session.add(item)
    session.flush()
    return item


@router.patch("/option-items/{item_id}", response_model=OptionItemResponse)
def update_option_item(
    item_id: uuid.UUID,
    body: OptionItemUpdate,
    session: Session = Depends(get_session),
    _actor: User = Depends(_CAN_EDIT),
) -> OptionItem:
    item = _get_item_or_404(session, item_id)

    if body.name is not None:
        _assert_item_name_free(session, item.group_id, body.name, exclude_id=item.id)
        item.name = body.name
    if body.price is not None:
        item.price = body.price.quantize(_CENTS)
    if "product_id" in body.model_fields_set:
        if body.product_id is not None:
            _get_sale_product_or_400(session, body.product_id)
        item.product_id = body.product_id
    if body.sort_order is not None:
        item.sort_order = body.sort_order
    if body.is_active is not None:
        item.is_active = body.is_active
    session.flush()
    return item


# ---------------------------------------------------------------------------
# Asignacion plato -> grupos
# ---------------------------------------------------------------------------


@router.get(
    "/products/{product_id}/option-groups",
    response_model=list[ProductOptionGroupResponse],
)
def list_product_option_groups(
    product_id: uuid.UUID,
    session: Session = Depends(get_session),
    _actor: User = Depends(_CAN_EDIT),
) -> list[ProductOptionGroupResponse]:
    """Grupos asignados al plato, activos o no, en el orden en que se preguntan."""
    _get_sale_product_or_400(session, product_id)
    rows = session.execute(
        select(ProductOptionGroup, OptionGroup)
        .join(OptionGroup, OptionGroup.id == ProductOptionGroup.group_id)
        .where(ProductOptionGroup.product_id == product_id)
        .order_by(ProductOptionGroup.sort_order, OptionGroup.name)
    ).all()
    return [
        ProductOptionGroupResponse(
            group_id=link.group_id, name=group.name, sort_order=link.sort_order
        )
        for link, group in rows
    ]


@router.put(
    "/products/{product_id}/option-groups",
    response_model=list[ProductOptionGroupResponse],
)
def replace_product_option_groups(
    product_id: uuid.UUID,
    body: ProductOptionGroupsPut,
    session: Session = Depends(get_session),
    _actor: User = Depends(_CAN_EDIT),
) -> list[ProductOptionGroupResponse]:
    """Reemplaza la asignacion completa. El orden de la lista es el orden.

    Es un PUT y no un POST/DELETE por grupo porque lo que el dueno decide es
    "este plato lleva estos grupos, en este orden", y eso es un solo hecho.
    """
    product = _get_sale_product_or_400(session, product_id)

    groups = session.scalars(
        select(OptionGroup).where(OptionGroup.id.in_(body.group_ids))
    ).all() if body.group_ids else []
    found = {group.id for group in groups}
    unknown = [gid for gid in body.group_ids if gid not in found]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown option group {unknown[0]}",
        )

    existing = session.scalars(
        select(ProductOptionGroup).where(ProductOptionGroup.product_id == product.id)
    ).all()
    for link in existing:
        session.delete(link)
    session.flush()
    for position, group_id in enumerate(body.group_ids):
        session.add(
            ProductOptionGroup(product_id=product.id, group_id=group_id, sort_order=position)
        )
    session.flush()
    return list_product_option_groups(product_id, session, _actor)
