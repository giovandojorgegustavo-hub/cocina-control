"""Tests for the seed_sale_products CLI script.

Like the user scripts, this one opens its own session and commits — writes land
in the shared test database, not in the SAVEPOINT-wrapped ``db_session``. The
catalogue names are fixed constants (not UUID-suffixed), so every test cleans
up the rows it created; otherwise the first test to run would make the rest see
an already-seeded catalogue.
"""

import sys
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.models.product import Product
from cocina_control.models.user import User
from cocina_control.scripts.seed_sale_products import SALE_CATALOGUE


@pytest.fixture
def script_env(postgres_url, monkeypatch):
    """Point the script at the pytest-postgresql ephemeral database."""
    from cocina_control import config

    monkeypatch.setattr(config, "_settings", None)
    monkeypatch.setenv("COCINA_DATABASE_URL", postgres_url)
    yield


@pytest.fixture
def committed_session(db_engine):
    """A real (non-SAVEPOINT) session, so the script can observe what we write."""
    from cocina_control.db import build_session_factory

    factory = build_session_factory(db_engine)
    with factory() as session:
        yield session


@pytest.fixture
def seed_owner(committed_session: Session):
    """An owner the script can record as created_by, committed and then removed."""
    from cocina_control.security.passwords import hash_password

    owner = User(
        id=uuid.uuid4(),
        name="Duena Seed",
        email=f"seed-owner-{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("strongpass123"),
        role="owner",
    )
    committed_session.add(owner)
    committed_session.commit()
    yield owner
    # Products reference the owner with ondelete=RESTRICT, so they go first.
    committed_session.query(Product).filter(
        Product.created_by == owner.id
    ).delete(synchronize_session=False)
    committed_session.delete(owner)
    committed_session.commit()


@pytest.fixture
def catalogue_cleanup(committed_session: Session):
    """Remove every catalogue-named product left behind by a test."""
    yield
    committed_session.query(Product).filter(
        Product.name.in_(SALE_CATALOGUE)
    ).delete(synchronize_session=False)
    committed_session.commit()


def _run(monkeypatch, email, *flags):
    monkeypatch.setattr(
        sys, "argv", ["seed_sale_products", "--owner-email", email, *flags]
    )
    from cocina_control.scripts.seed_sale_products import main

    main()


def _catalogue_rows(session: Session) -> list[Product]:
    session.expire_all()
    return list(
        session.scalars(select(Product).where(Product.name.in_(SALE_CATALOGUE))).all()
    )


# ---------------------------------------------------------------------------
# El catalogo en si
# ---------------------------------------------------------------------------


def test_catalogue_has_no_combos():
    """Un combo es combinacion de productos: contarlo duplicaria el consumo."""
    assert not [name for name in SALE_CATALOGUE if "COMBO" in name]


def test_catalogue_names_are_unique_and_upper():
    assert len(SALE_CATALOGUE) == len(set(SALE_CATALOGUE))
    assert all(name == name.upper() for name in SALE_CATALOGUE)


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------


def test_seed_creates_every_catalogue_product(
    script_env, monkeypatch, seed_owner, catalogue_cleanup, committed_session
):
    _run(monkeypatch, seed_owner.email)

    rows = _catalogue_rows(committed_session)
    assert {p.name for p in rows} == set(SALE_CATALOGUE)
    assert all(p.is_sale for p in rows)
    # Un bowl que sale no es un insumo que entra: venta pura.
    assert all(not p.is_purchase for p in rows)
    assert all(p.unit == "un" for p in rows)
    assert all(p.is_active for p in rows)
    assert all(p.created_by == seed_owner.id for p in rows)


def test_seed_is_idempotent(
    script_env, monkeypatch, seed_owner, catalogue_cleanup, committed_session, capsys
):
    _run(monkeypatch, seed_owner.email)
    capsys.readouterr()

    _run(monkeypatch, seed_owner.email)
    out = capsys.readouterr().out

    assert "creados: 0" in out
    assert f"ya existian: {len(SALE_CATALOGUE)}" in out
    assert len(_catalogue_rows(committed_session)) == len(SALE_CATALOGUE)


def test_dry_run_writes_nothing(
    script_env, monkeypatch, seed_owner, catalogue_cleanup, committed_session, capsys
):
    _run(monkeypatch, seed_owner.email, "--dry-run")
    out = capsys.readouterr().out

    assert "[dry-run]" in out
    assert _catalogue_rows(committed_session) == []


# ---------------------------------------------------------------------------
# --fix-mismarked
# ---------------------------------------------------------------------------


def test_fix_mismarked_clears_raw_input_but_keeps_purchase(
    script_env, monkeypatch, seed_owner, catalogue_cleanup, committed_session
):
    raw = Product(
        id=uuid.uuid4(),
        name=f"SAL IODADA {uuid.uuid4().hex[:6]}",
        unit="kg",
        is_active=True,
        is_purchase=True,
        is_sale=True,  # el flag mal puesto que ensucia la grilla del pedido
        created_by=seed_owner.id,
    )
    committed_session.add(raw)
    committed_session.commit()

    _run(monkeypatch, seed_owner.email, "--fix-mismarked")

    committed_session.expire_all()
    refreshed = committed_session.get(Product, raw.id)
    assert refreshed is not None
    assert refreshed.is_sale is False
    # Sigue siendo insumo de compra — la check constraint se mantiene.
    assert refreshed.is_purchase is True
    assert refreshed.updated_by == seed_owner.id
    assert refreshed.updated_at is not None


def test_fix_mismarked_leaves_catalogue_products_alone(
    script_env, monkeypatch, seed_owner, catalogue_cleanup, committed_session
):
    _run(monkeypatch, seed_owner.email, "--fix-mismarked")

    rows = _catalogue_rows(committed_session)
    assert len(rows) == len(SALE_CATALOGUE)
    assert all(p.is_sale for p in rows)


def test_without_flag_mismarked_is_untouched(
    script_env, monkeypatch, seed_owner, catalogue_cleanup, committed_session
):
    raw = Product(
        id=uuid.uuid4(),
        name=f"HUEVO {uuid.uuid4().hex[:6]}",
        unit="kg",
        is_active=True,
        is_purchase=True,
        is_sale=True,
        created_by=seed_owner.id,
    )
    committed_session.add(raw)
    committed_session.commit()

    _run(monkeypatch, seed_owner.email)

    committed_session.expire_all()
    refreshed = committed_session.get(Product, raw.id)
    assert refreshed is not None
    assert refreshed.is_sale is True


# ---------------------------------------------------------------------------
# Autorizacion
# ---------------------------------------------------------------------------


def test_rejects_unknown_email(script_env, monkeypatch, committed_session):
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, f"fantasma-{uuid.uuid4().hex[:6]}@test.com")
    assert exc.value.code == 1
    assert _catalogue_rows(committed_session) == []


def test_rejects_cocinero(script_env, monkeypatch, committed_session):
    """El cocinero no crea catalogo — mismo estandar que el POST /products."""
    from cocina_control.security.passwords import hash_password

    cocinero = User(
        id=uuid.uuid4(),
        name="Cocinero Seed",
        email=f"seed-cocinero-{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("strongpass123"),
        role="cocinero",
    )
    committed_session.add(cocinero)
    committed_session.commit()

    try:
        with pytest.raises(SystemExit) as exc:
            _run(monkeypatch, cocinero.email)
        assert exc.value.code == 1
        assert _catalogue_rows(committed_session) == []
    finally:
        committed_session.delete(cocinero)
        committed_session.commit()
