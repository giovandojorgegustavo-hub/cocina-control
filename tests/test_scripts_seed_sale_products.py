"""Tests for the seed_sale_products CLI script.

Like the user scripts, this one opens its own session and commits — writes land
in the shared test database, not in the SAVEPOINT-wrapped ``db_session``.

Two rules keep that safe, and they are the point of this docstring:

1. **Nothing here deletes a row.** ``products`` is never physically deleted in
   this system (``api/products.py``: is_active goes false instead), and a test
   fixture is not the place to make an exception. Cleanup is the ephemeral
   database being dropped at the end of the session.
2. **The real catalogue names never reach the database.** Every test that
   writes monkeypatches ``SALE_CATALOGUE`` to UUID-suffixed names, the same way
   ``test_scripts_users.py`` uses UUID-suffixed emails. Tests that care about
   the real catalogue's *content* assert on the constant without touching the DB.
"""

import secrets
import sys
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.models.product import Product
from cocina_control.models.user import User
from cocina_control.scripts import seed_sale_products as seed_module
from cocina_control.scripts.seed_sale_products import SALE_CATALOGUE, _normalise_key


@pytest.fixture
def script_env(postgres_url, db_engine, monkeypatch):
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
def seed_password() -> str:
    """Never a fixed credential: the row lives in a real table until teardown."""
    return secrets.token_urlsafe(16)


def _make_user(session: Session, role: str, password: str) -> User:
    from cocina_control.security.passwords import hash_password

    user = User(
        id=uuid.uuid4(),
        name=f"Seed {role}",
        email=f"seed-{role}-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password(password),
        role=role,
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def seed_owner(committed_session: Session, seed_password: str) -> User:
    return _make_user(committed_session, "owner", seed_password)


@pytest.fixture
def fake_catalogue(monkeypatch) -> list[str]:
    """A catalogue of throwaway names, so no real product name is ever written."""
    suffix = uuid.uuid4().hex[:8].upper()
    names = [f"BOWL TEST {suffix}", f"WRAP TEST {suffix}", f"BEBIDA TEST {suffix}"]
    monkeypatch.setattr(seed_module, "SALE_CATALOGUE", names)
    return names


def _run(monkeypatch, email, password, *flags):
    monkeypatch.setattr("getpass.getpass", lambda prompt="": password)
    monkeypatch.setattr(
        sys, "argv", ["seed_sale_products", "--owner-email", email, *flags]
    )
    seed_module.main()


def _rows(session: Session, names: list[str]) -> list[Product]:
    session.expire_all()
    return list(session.scalars(select(Product).where(Product.name.in_(names))).all())


# ---------------------------------------------------------------------------
# El catalogo real — aserciones puras, sin tocar la base
# ---------------------------------------------------------------------------


def test_catalogue_has_no_combos():
    """Un combo es combinacion de productos: contarlo duplicaria el consumo."""
    assert not [name for name in SALE_CATALOGUE if "COMBO" in _normalise_key(name)]


def test_catalogue_names_are_unique_even_ignoring_accents():
    keys = [_normalise_key(name) for name in SALE_CATALOGUE]
    assert len(keys) == len(set(keys))


def test_catalogue_names_are_already_normalised_upper():
    assert all(name == " ".join(name.strip().split()).upper() for name in SALE_CATALOGUE)


def test_normalise_key_ignores_accents_and_case():
    assert _normalise_key("Maracuyá  Refrescante") == _normalise_key(
        "MARACUYA REFRESCANTE"
    )


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------


def test_seed_creates_every_catalogue_product(
    script_env, monkeypatch, seed_owner, seed_password, fake_catalogue, committed_session
):
    _run(monkeypatch, seed_owner.email, seed_password)

    rows = _rows(committed_session, fake_catalogue)
    assert {p.name for p in rows} == set(fake_catalogue)
    assert all(p.is_sale for p in rows)
    # Un bowl que sale no es un insumo que entra: venta pura.
    assert all(not p.is_purchase for p in rows)
    assert all(p.unit == "un" for p in rows)
    assert all(p.is_active for p in rows)
    assert all(p.created_by == seed_owner.id for p in rows)


def test_seed_is_idempotent(
    script_env,
    monkeypatch,
    seed_owner,
    seed_password,
    fake_catalogue,
    committed_session,
    capsys,
):
    _run(monkeypatch, seed_owner.email, seed_password)
    capsys.readouterr()

    _run(monkeypatch, seed_owner.email, seed_password)
    out = capsys.readouterr().out

    assert "creados: 0" in out
    assert f"ya estaban: {len(fake_catalogue)}" in out
    assert len(_rows(committed_session, fake_catalogue)) == len(fake_catalogue)


def test_dry_run_writes_nothing(
    script_env,
    monkeypatch,
    seed_owner,
    seed_password,
    fake_catalogue,
    committed_session,
    capsys,
):
    _run(monkeypatch, seed_owner.email, seed_password, "--dry-run")
    out = capsys.readouterr().out

    assert "[dry-run]" in out
    assert _rows(committed_session, fake_catalogue) == []


def test_admin_can_seed(
    script_env,
    monkeypatch,
    seed_password,
    fake_catalogue,
    committed_session,
):
    """POST /products acepta owner y admin — el script mantiene esa paridad."""
    admin = _make_user(committed_session, "admin", seed_password)

    _run(monkeypatch, admin.email, seed_password)

    assert len(_rows(committed_session, fake_catalogue)) == len(fake_catalogue)


# ---------------------------------------------------------------------------
# Conflictos: el script REPORTA, nunca muta lo que ya existe
# ---------------------------------------------------------------------------


def test_existing_name_not_flagged_as_sale_is_reported_not_promoted(
    script_env,
    monkeypatch,
    seed_owner,
    seed_password,
    fake_catalogue,
    committed_session,
    capsys,
):
    """Una VINAGRETA cargada como insumo no se promueve a venta en silencio."""
    insumo = Product(
        id=uuid.uuid4(),
        name=fake_catalogue[0],
        unit="lt",
        is_active=True,
        is_purchase=True,
        is_sale=False,
        created_by=seed_owner.id,
    )
    committed_session.add(insumo)
    committed_session.commit()

    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, seed_owner.email, seed_password)
    assert exc.value.code == 2

    out = capsys.readouterr().out
    assert "CONFLICTOS" in out
    assert "NO está marcado como venta" in out

    committed_session.expire_all()
    refreshed = committed_session.get(Product, insumo.id)
    assert refreshed is not None
    # No lo tocamos: promoverlo es decision del dueno, via PATCH /products.
    assert refreshed.is_sale is False
    assert refreshed.unit == "lt"
    assert refreshed.updated_by is None


def test_accented_twin_is_detected_instead_of_duplicated(
    script_env,
    monkeypatch,
    seed_owner,
    seed_password,
    committed_session,
    capsys,
):
    """MARACUYA y MARACUYÁ son el mismo producto para el operario apurado."""
    suffix = uuid.uuid4().hex[:8].upper()
    canonical = f"MARACUYÁ TEST {suffix}"
    typed_by_hand = f"MARACUYA TEST {suffix}"
    monkeypatch.setattr(seed_module, "SALE_CATALOGUE", [canonical])

    existing = Product(
        id=uuid.uuid4(),
        name=typed_by_hand,
        unit="un",
        is_active=True,
        is_purchase=False,
        is_sale=True,
        created_by=seed_owner.id,
    )
    committed_session.add(existing)
    committed_session.commit()

    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, seed_owner.email, seed_password)
    assert exc.value.code == 2

    assert "otra grafía" in capsys.readouterr().out
    # Lo que no puede pasar: dos filas del mismo producto en la grilla.
    assert _rows(committed_session, [canonical]) == []


def test_resale_product_is_reported_never_unflagged(
    script_env,
    monkeypatch,
    seed_owner,
    seed_password,
    fake_catalogue,
    committed_session,
    capsys,
):
    """Una gaseosa que se compra hecha y se revende (migracion 0015) sobrevive.

    Es el caso que hundio la version anterior de este script: desmarcarla la
    convertia en una fuga de inventario fantasma.
    """
    gaseosa = Product(
        id=uuid.uuid4(),
        name=f"GASEOSA TEST {uuid.uuid4().hex[:8].upper()}",
        unit="un",
        is_active=True,
        is_purchase=True,
        is_sale=True,
        created_by=seed_owner.id,
    )
    committed_session.add(gaseosa)
    committed_session.commit()

    _run(monkeypatch, seed_owner.email, seed_password)

    out = capsys.readouterr().out
    assert "FUERA DEL MENÚ" in out
    assert gaseosa.name in out

    committed_session.expire_all()
    refreshed = committed_session.get(Product, gaseosa.id)
    assert refreshed is not None
    assert refreshed.is_sale is True
    assert refreshed.is_purchase is True
    assert refreshed.updated_by is None


def test_script_never_mutates_an_existing_product(
    script_env,
    monkeypatch,
    seed_owner,
    seed_password,
    fake_catalogue,
    committed_session,
):
    """Invariante del script: solo inserta. Ninguna fila previa cambia."""
    before = Product(
        id=uuid.uuid4(),
        name=f"INSUMO TEST {uuid.uuid4().hex[:8].upper()}",
        unit="kg",
        is_active=True,
        is_purchase=True,
        is_sale=True,
        created_by=seed_owner.id,
    )
    committed_session.add(before)
    committed_session.commit()
    snapshot = (before.name, before.unit, before.is_purchase, before.is_sale)

    _run(monkeypatch, seed_owner.email, seed_password)

    committed_session.expire_all()
    after = committed_session.get(Product, before.id)
    assert after is not None
    assert (after.name, after.unit, after.is_purchase, after.is_sale) == snapshot
    assert after.updated_at is None


# ---------------------------------------------------------------------------
# Autorizacion
# ---------------------------------------------------------------------------


def test_rejects_unknown_email(
    script_env, monkeypatch, seed_password, fake_catalogue, committed_session
):
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, f"fantasma-{uuid.uuid4().hex[:6]}@test.com", seed_password)
    assert exc.value.code == 1
    assert _rows(committed_session, fake_catalogue) == []


def test_rejects_cocinero(
    script_env, monkeypatch, seed_password, fake_catalogue, committed_session
):
    """El cocinero no crea catalogo — mismo estandar que el POST /products."""
    cocinero = _make_user(committed_session, "cocinero", seed_password)

    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, cocinero.email, seed_password)
    assert exc.value.code == 1
    assert _rows(committed_session, fake_catalogue) == []


def test_rejects_wrong_password(
    script_env, monkeypatch, seed_owner, fake_catalogue, committed_session
):
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, seed_owner.email, "la-que-no-es")
    assert exc.value.code == 1
    assert _rows(committed_session, fake_catalogue) == []


def test_denial_message_does_not_leak_whether_the_user_exists(
    script_env, monkeypatch, seed_owner, seed_password, fake_catalogue, capsys
):
    """Mismo texto para inexistente, rol equivocado y password mala."""
    with pytest.raises(SystemExit):
        _run(monkeypatch, f"fantasma-{uuid.uuid4().hex[:6]}@test.com", seed_password)
    unknown = capsys.readouterr().err

    with pytest.raises(SystemExit):
        _run(monkeypatch, seed_owner.email, "la-que-no-es")
    bad_password = capsys.readouterr().err

    assert unknown == bad_password
    assert "role" not in unknown.lower()
