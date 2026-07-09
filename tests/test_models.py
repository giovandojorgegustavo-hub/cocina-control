"""Integration tests for the initial schema migration and SQLAlchemy models.

These tests require a live PostgreSQL database.  The db_engine fixture in
conftest.py runs `alembic upgrade head` before the session starts and
`alembic downgrade base` after it finishes.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    "users",
    "products",
    "deliveries",
    "delivery_items",
    "delivery_orders",
    "delivery_order_items",
    "inventory_counts",
    "inventory_count_items",
}


def _make_user(name: str = "Test User", email: str | None = None) -> dict:
    return {
        "id": uuid.uuid4(),
        "name": name,
        "email": email or f"{uuid.uuid4().hex[:8]}@test.com",
        "password_hash": "hashed",
        "role": "operator",
        "created_at": datetime.now(UTC),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_migration_upgrade_creates_tables(db_engine):
    """After upgrade head, all 8 expected tables must exist."""
    inspector = inspect(db_engine)
    existing = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(existing), (
        f"Missing tables: {EXPECTED_TABLES - existing}"
    )


def test_users_email_unique(db_session: Session):
    """Inserting two users with the same email must raise IntegrityError."""
    from cocina_control.models.user import User

    email = f"{uuid.uuid4().hex[:8]}@unique.com"

    user1 = User(**_make_user(name="Alice", email=email))
    user2 = User(**_make_user(name="Bob", email=email))

    db_session.add(user1)
    db_session.flush()

    db_session.add(user2)
    # Use a nested savepoint so we can catch the error without invalidating
    # the outer transaction that the conftest fixture manages.
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.flush()


def test_product_defaults(db_session: Session):
    """A product inserted with only name/unit/created_by must have is_active=True."""
    from cocina_control.models.product import Product
    from cocina_control.models.user import User

    user = User(**_make_user())
    db_session.add(user)
    db_session.flush()

    product = Product(
        id=uuid.uuid4(),
        name="PALTA",
        unit="kg",
        created_by=user.id,
    )
    db_session.add(product)
    db_session.flush()
    db_session.refresh(product)

    assert product.is_active is True
    assert product.low_stock_threshold is None


def test_delivery_item_corrects_id_self_fk(db_session: Session):
    """A DeliveryItem can point to another DeliveryItem via corrects_id."""
    from cocina_control.models.delivery import Delivery, DeliveryItem
    from cocina_control.models.product import Product
    from cocina_control.models.user import User

    user = User(**_make_user())
    db_session.add(user)
    db_session.flush()

    product = Product(
        id=uuid.uuid4(),
        name="POLLO",
        unit="kg",
        created_by=user.id,
    )
    db_session.add(product)
    db_session.flush()

    delivery = Delivery(
        id=uuid.uuid4(),
        supplier_name="Proveedor SA",
        status="no_leida",
        created_by=user.id,
    )
    db_session.add(delivery)
    db_session.flush()

    original_item = DeliveryItem(
        id=uuid.uuid4(),
        delivery_id=delivery.id,
        product_id=product.id,
        announced_qty=10,
        received_qty=10,
        created_by=user.id,
    )
    db_session.add(original_item)
    db_session.flush()

    correction = DeliveryItem(
        id=uuid.uuid4(),
        delivery_id=delivery.id,
        product_id=product.id,
        announced_qty=10,
        received_qty=8,
        created_by=user.id,
        corrects_id=original_item.id,
    )
    db_session.add(correction)
    db_session.flush()
    db_session.refresh(correction)

    assert correction.corrects_id == original_item.id
    assert correction.received_qty == 8


def test_migration_downgrade_drops_all_tables(postgres_url: str):
    """After downgrade base, no application tables remain in the database.

    This test runs its own Alembic cycle (upgrade + downgrade) against a
    separate, isolated database connection so it does not interfere with the
    session-scoped db_engine that drives the other tests.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from cocina_control.db import build_engine

    # Build a fresh engine for the isolated cycle.
    engine = build_engine(postgres_url)

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", postgres_url)

    # Ensure we start from a clean slate.
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    # Tables must exist after upgrade.
    inspector = inspect(engine)
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))

    # Downgrade — tables must disappear.
    command.downgrade(cfg, "base")

    inspector = inspect(engine)
    remaining = set(inspector.get_table_names())
    overlap = EXPECTED_TABLES & remaining
    assert not overlap, f"Tables still present after downgrade: {overlap}"

    engine.dispose()

    # Restore schema so the session-scoped fixtures remain functional.
    command.upgrade(cfg, "head")
