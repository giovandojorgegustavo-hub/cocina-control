"""Integration tests for the composition schema (migration 0018).

The invariants under test are the ones the database must hold on its own,
because the service layer cannot be trusted to be the only writer: the seeding
scripts and any future import path write straight to these tables.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cocina_control.models.delivery_order import DeliveryOrder, DeliveryOrderItem
from cocina_control.models.product import Product
from cocina_control.models.recipe import DeliveryOrderItemIngredient, ProductRecipe

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _product(db_session: Session, user_id: uuid.UUID, name: str) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        unit="kg",
        created_by=user_id,
    )
    db_session.add(product)
    db_session.flush()
    return product


def _order_item(
    db_session: Session, user_id: uuid.UUID, product_id: uuid.UUID
) -> DeliveryOrderItem:
    order = DeliveryOrder(id=uuid.uuid4(), created_by=user_id)
    db_session.add(order)
    db_session.flush()

    item = DeliveryOrderItem(
        id=uuid.uuid4(),
        delivery_order_id=order.id,
        product_id=product_id,
        quantity=Decimal("1"),
        created_by=user_id,
    )
    db_session.add(item)
    db_session.flush()
    return item


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_migration_creates_composition_tables(db_engine):
    existing = set(inspect(db_engine).get_table_names())
    assert {"product_recipe", "delivery_order_item_ingredients"}.issubset(existing)


# ---------------------------------------------------------------------------
# ProductRecipe
# ---------------------------------------------------------------------------


def test_recipe_quantity_is_optional(db_session: Session, cocinero_user):
    """The whole point of the first release: capture WHAT before HOW MUCH."""
    plato = _product(db_session, cocinero_user.id, "FOCUS BOWL")
    insumo = _product(db_session, cocinero_user.id, "TILAPIA")

    row = ProductRecipe(
        id=uuid.uuid4(),
        product_id=plato.id,
        ingredient_id=insumo.id,
        created_by=cocinero_user.id,
    )
    db_session.add(row)
    db_session.flush()
    db_session.refresh(row)

    assert row.quantity is None
    assert row.updated_at is None


def test_recipe_rejects_duplicate_ingredient(db_session: Session, cocinero_user):
    """Two rows of the same insumo would silently double the expected consumption."""
    plato = _product(db_session, cocinero_user.id, "ENERGY BOWL")
    insumo = _product(db_session, cocinero_user.id, "PALTA")

    for _ in range(2):
        db_session.add(
            ProductRecipe(
                id=uuid.uuid4(),
                product_id=plato.id,
                ingredient_id=insumo.id,
                created_by=cocinero_user.id,
            )
        )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()


def test_recipe_rejects_self_reference(db_session: Session, cocinero_user):
    plato = _product(db_session, cocinero_user.id, "BONA WRAP")

    db_session.add(
        ProductRecipe(
            id=uuid.uuid4(),
            product_id=plato.id,
            ingredient_id=plato.id,
            created_by=cocinero_user.id,
        )
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()


def test_recipe_rejects_zero_quantity(db_session: Session, cocinero_user):
    """NULL means 'not measured yet'. Zero would mean 'measured as nothing'."""
    plato = _product(db_session, cocinero_user.id, "WRAP FRESH")
    insumo = _product(db_session, cocinero_user.id, "LECHUGA")

    db_session.add(
        ProductRecipe(
            id=uuid.uuid4(),
            product_id=plato.id,
            ingredient_id=insumo.id,
            quantity=Decimal("0"),
            created_by=cocinero_user.id,
        )
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()


# ---------------------------------------------------------------------------
# DeliveryOrderItemIngredient
# ---------------------------------------------------------------------------


def test_order_ingredient_defaults_to_included(db_session: Session, cocinero_user):
    plato = _product(db_session, cocinero_user.id, "ARMA TU BOWL")
    insumo = _product(db_session, cocinero_user.id, "QUINUA")
    item = _order_item(db_session, cocinero_user.id, plato.id)

    row = DeliveryOrderItemIngredient(
        id=uuid.uuid4(),
        delivery_order_item_id=item.id,
        ingredient_id=insumo.id,
        created_by=cocinero_user.id,
    )
    db_session.add(row)
    db_session.flush()
    db_session.refresh(row)

    assert row.status == "included"
    assert row.quantity is None


def test_out_of_stock_ingredient_cannot_carry_quantity(db_session: Session, cocinero_user):
    """What never left the kitchen consumed nothing — no phantom consumption."""
    plato = _product(db_session, cocinero_user.id, "ARMA TU SALAD")
    insumo = _product(db_session, cocinero_user.id, "CHUCRUT")
    item = _order_item(db_session, cocinero_user.id, plato.id)

    db_session.add(
        DeliveryOrderItemIngredient(
            id=uuid.uuid4(),
            delivery_order_item_id=item.id,
            ingredient_id=insumo.id,
            quantity=Decimal("0.05"),
            status="out_of_stock",
            created_by=cocinero_user.id,
        )
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()


def test_out_of_stock_ingredient_without_quantity_is_accepted(db_session: Session, cocinero_user):
    plato = _product(db_session, cocinero_user.id, "ARMA TU WRAP")
    insumo = _product(db_session, cocinero_user.id, "TOMATE")
    item = _order_item(db_session, cocinero_user.id, plato.id)

    row = DeliveryOrderItemIngredient(
        id=uuid.uuid4(),
        delivery_order_item_id=item.id,
        ingredient_id=insumo.id,
        status="out_of_stock",
        created_by=cocinero_user.id,
    )
    db_session.add(row)
    db_session.flush()
    db_session.refresh(row)

    assert row.status == "out_of_stock"


def test_order_ingredient_rejects_duplicate_on_same_item(db_session: Session, cocinero_user):
    plato = _product(db_session, cocinero_user.id, "BOWL CRISPY")
    insumo = _product(db_session, cocinero_user.id, "ZANAHORIA")
    item = _order_item(db_session, cocinero_user.id, plato.id)

    for _ in range(2):
        db_session.add(
            DeliveryOrderItemIngredient(
                id=uuid.uuid4(),
                delivery_order_item_id=item.id,
                ingredient_id=insumo.id,
                created_by=cocinero_user.id,
            )
        )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()
