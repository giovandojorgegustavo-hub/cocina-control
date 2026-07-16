"""Tests for user management CLI scripts.

The scripts (create_user, create_owner, reset_password) open their own DB
session with commit=True — writes land in the shared test database, not in
the SAVEPOINT-wrapped ``db_session`` fixture.  We use unique UUID-based
emails to avoid cross-test collisions, and query with ``expire_all()`` from
``db_session`` to observe the script-committed rows.
"""

import sys
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from cocina_control.models.user import User
from cocina_control.security.passwords import verify_password


@pytest.fixture
def script_env(postgres_url, db_engine, monkeypatch):
    """Point the scripts at the pytest-postgresql ephemeral database."""
    from cocina_control import config

    monkeypatch.setattr(config, "_settings", None)
    monkeypatch.setenv("COCINA_DATABASE_URL", postgres_url)
    # COCINA_JWT_SECRET is already set in conftest at import time.
    yield


def _mock_getpass(monkeypatch, passwords):
    """Return successive values from `passwords` on each getpass.getpass call."""
    iterator = iter(passwords)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(iterator))


def _run_create_user(monkeypatch, name, email, role):
    monkeypatch.setattr(
        sys,
        "argv",
        ["create_user", "--name", name, "--email", email, "--role", role],
    )
    from cocina_control.scripts.create_user import main

    main()


def _run_create_owner(monkeypatch, name, email, extra_args=None):
    argv = ["create_owner", "--name", name, "--email", email]
    if extra_args:
        argv.extend(extra_args)
    monkeypatch.setattr(sys, "argv", argv)
    from cocina_control.scripts.create_owner import main

    main()


def _run_reset_password(monkeypatch, email):
    monkeypatch.setattr(sys, "argv", ["reset_password", "--email", email])
    from cocina_control.scripts.reset_password import main

    main()


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------


def test_create_user_admin_ok(script_env, monkeypatch, db_session: Session):
    email = f"admin-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    _run_create_user(monkeypatch, "Admin Test", email, "admin")

    db_session.expire_all()
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.role == "admin"
    assert user.name == "Admin Test"
    assert verify_password("strongpass123", user.password_hash)


def test_create_user_cocinero_ok(script_env, monkeypatch, db_session: Session):
    email = f"cocinero-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    _run_create_user(monkeypatch, "Cocinero Test", email, "cocinero")

    db_session.expire_all()
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.role == "cocinero"


def test_create_user_owner_via_create_user_ok(script_env, monkeypatch, db_session: Session):
    email = f"owner-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    _run_create_user(monkeypatch, "Owner Test", email, "owner")

    db_session.expire_all()
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.role == "owner"


def test_create_user_invalid_role_argparse(script_env, monkeypatch):
    email = f"test-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    with pytest.raises(SystemExit) as exc:
        _run_create_user(monkeypatch, "Test", email, "hacker")
    assert exc.value.code != 0


def test_create_user_missing_role_argparse(script_env, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["create_user", "--name", "T", "--email", "t@x.com"]
    )
    from cocina_control.scripts.create_user import main

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code != 0


def test_create_user_duplicate_email_rejected(script_env, monkeypatch, db_session: Session):
    email = f"dup-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    _run_create_user(monkeypatch, "First", email, "admin")

    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    with pytest.raises(SystemExit) as exc:
        _run_create_user(monkeypatch, "Second", email, "cocinero")
    assert exc.value.code == 1


def test_create_user_email_lowercased(script_env, monkeypatch, db_session: Session):
    raw = f"MiXeD-{uuid.uuid4().hex[:6]}@TeSt.COM"
    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    _run_create_user(monkeypatch, "Mixed Case", raw, "admin")

    db_session.expire_all()
    user = db_session.scalar(select(User).where(User.email == raw.lower()))
    assert user is not None
    assert user.email == raw.lower()


def test_create_user_short_password_rejected(script_env, monkeypatch):
    email = f"short-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["short12"])  # 7 chars
    with pytest.raises(SystemExit) as exc:
        _run_create_user(monkeypatch, "Short", email, "admin")
    assert exc.value.code == 1


def test_create_user_empty_password_rejected(script_env, monkeypatch):
    email = f"empty-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, [""])
    with pytest.raises(SystemExit) as exc:
        _run_create_user(monkeypatch, "Empty", email, "admin")
    assert exc.value.code == 1


def test_create_user_password_mismatch_rejected(script_env, monkeypatch):
    email = f"mismatch-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["strongpass123", "differentpass"])
    with pytest.raises(SystemExit) as exc:
        _run_create_user(monkeypatch, "Mismatch", email, "admin")
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# create_owner (wrapper)
# ---------------------------------------------------------------------------


def test_create_owner_wrapper_creates_owner(script_env, monkeypatch, db_session: Session):
    email = f"wrapper-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    _run_create_owner(monkeypatch, "Wrapper Owner", email)

    db_session.expire_all()
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.role == "owner"


def test_create_owner_wrapper_rejects_role_argument(script_env, monkeypatch):
    """Passing --role via the wrapper is rejected by the guard with exit 1."""
    email = f"conflict-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    with pytest.raises(SystemExit) as exc:
        _run_create_owner(monkeypatch, "Conflict", email, extra_args=["--role", "admin"])
    assert exc.value.code == 1


def test_create_user_multibyte_password_over_72_bytes_rejected(
    script_env, monkeypatch
):
    """A password of 19 emojis (76 bytes UTF-8) passes len()>=8 but bcrypt rejects it.

    Must exit cleanly with error message, not raise ValueError traceback.
    """
    email = f"mb-{uuid.uuid4().hex[:6]}@test.com"
    long_pw = "🔑" * 19  # 19 chars, 76 bytes
    _mock_getpass(monkeypatch, [long_pw, long_pw])
    with pytest.raises(SystemExit) as exc:
        _run_create_user(monkeypatch, "Multibyte", email, "admin")
    assert exc.value.code == 1


def test_create_user_email_whitespace_stripped(
    script_env, monkeypatch, db_session: Session
):
    """Email with surrounding whitespace is stripped before persist."""
    raw = f"  ws-{uuid.uuid4().hex[:6]}@test.com  "
    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    _run_create_user(monkeypatch, "Whitespace", raw, "admin")

    db_session.expire_all()
    user = db_session.scalar(select(User).where(User.email == raw.strip().lower()))
    assert user is not None
    assert user.email == raw.strip().lower()
    assert user.email.startswith("ws-")
    assert not user.email.startswith(" ")


def test_create_user_concurrent_creation_returns_clean_error(script_env, monkeypatch):
    """If another process created the user between SELECT and INSERT, we get a clean 1.

    The pre-existing user is created through the script itself (own connection,
    real commit) — inserting through the transaction-wrapped db_session leaves
    the row uncommitted and deadlocks the script's INSERT on the unique index.
    The second run patches Session.scalar so the existence check misses,
    forcing the INSERT onto the unique constraint (the IntegrityError path).
    """
    from sqlalchemy.orm import Session as OrmSession

    email = f"race-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["someexisting123", "someexisting123"])
    _run_create_user(monkeypatch, "Pre Existing", email, "cocinero")

    monkeypatch.setattr(OrmSession, "scalar", lambda self, *a, **kw: None)
    _mock_getpass(monkeypatch, ["strongpass123", "strongpass123"])
    with pytest.raises(SystemExit) as exc:
        _run_create_user(monkeypatch, "Race", email, "admin")
    assert exc.value.code == 1


def test_reset_password_multibyte_password_over_72_bytes_rejected(
    script_env, monkeypatch
):
    """Reset with a >72 bytes password must exit cleanly, not raise ValueError."""
    email = f"mb-reset-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["oldpass123", "oldpass123"])
    _run_create_user(monkeypatch, "Multibyte Reset", email, "admin")

    long_pw = "🔑" * 19
    _mock_getpass(monkeypatch, [long_pw, long_pw])
    with pytest.raises(SystemExit) as exc:
        _run_reset_password(monkeypatch, email)
    assert exc.value.code == 1


def test_reset_password_email_whitespace_stripped(
    script_env, monkeypatch, db_session: Session
):
    """Email with surrounding whitespace on reset finds the underlying user."""
    email = f"ws-reset-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["oldpass123", "oldpass123"])
    _run_create_user(monkeypatch, "WS Reset", email, "admin")

    _mock_getpass(monkeypatch, ["newpass456", "newpass456"])
    _run_reset_password(monkeypatch, f"  {email}  ")

    db_session.expire_all()
    user = db_session.scalar(select(User).where(User.email == email))
    assert verify_password("newpass456", user.password_hash)


# ---------------------------------------------------------------------------
# reset_password
# ---------------------------------------------------------------------------


def test_reset_password_ok(script_env, monkeypatch, db_session: Session):
    email = f"reset-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["oldpass123", "oldpass123"])
    _run_create_user(monkeypatch, "Reset Test", email, "admin")

    _mock_getpass(monkeypatch, ["newpass456", "newpass456"])
    _run_reset_password(monkeypatch, email)

    db_session.expire_all()
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert verify_password("newpass456", user.password_hash)
    assert not verify_password("oldpass123", user.password_hash)


def test_reset_password_email_case_insensitive(script_env, monkeypatch, db_session: Session):
    email = f"case-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["oldpass123", "oldpass123"])
    _run_create_user(monkeypatch, "Case Test", email, "admin")

    _mock_getpass(monkeypatch, ["newpass456", "newpass456"])
    _run_reset_password(monkeypatch, email.upper())

    db_session.expire_all()
    user = db_session.scalar(select(User).where(User.email == email))
    assert verify_password("newpass456", user.password_hash)


def test_reset_password_unknown_email_rejected(script_env, monkeypatch):
    email = f"ghost-{uuid.uuid4().hex[:6]}@nowhere.com"
    with pytest.raises(SystemExit) as exc:
        _run_reset_password(monkeypatch, email)
    assert exc.value.code == 1


def test_reset_password_short_password_rejected(script_env, monkeypatch, db_session: Session):
    email = f"short-reset-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["oldpass123", "oldpass123"])
    _run_create_user(monkeypatch, "Short Reset", email, "admin")

    _mock_getpass(monkeypatch, ["short12"])
    with pytest.raises(SystemExit) as exc:
        _run_reset_password(monkeypatch, email)
    assert exc.value.code == 1


def test_reset_password_mismatch_rejected(script_env, monkeypatch, db_session: Session):
    email = f"mismatch-reset-{uuid.uuid4().hex[:6]}@test.com"
    _mock_getpass(monkeypatch, ["oldpass123", "oldpass123"])
    _run_create_user(monkeypatch, "Mismatch Reset", email, "admin")

    _mock_getpass(monkeypatch, ["newpass456", "differentpass"])
    with pytest.raises(SystemExit) as exc:
        _run_reset_password(monkeypatch, email)
    assert exc.value.code == 1
