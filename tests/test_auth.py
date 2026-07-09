"""Integration tests for authentication (login, JWT, role enforcement).

Test database is provided by the db_session fixture from conftest.py.
Every test runs in a SAVEPOINT that is rolled back afterwards, so user
records created here never persist to other tests.
"""

import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from cocina_control.models.user import User
from cocina_control.security.passwords import hash_password
from cocina_control.security.rate_limit import reset as reset_rate_limit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_PASSWORD = "correct-horse-battery-staple"


def create_test_user(
    session: Session,
    role: str,
    email: str,
    password: str = _TEST_PASSWORD,
) -> User:
    """Insert and return a User with the given role.

    Email is lowercased here to match the application-layer convention.
    """
    user = User(
        id=uuid.uuid4(),
        name=f"Test {role.capitalize()}",
        email=email.lower(),
        password_hash=hash_password(password),
        role=role,
        created_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    return user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def owner_user(db_session: Session) -> User:
    return create_test_user(db_session, "owner", f"owner-{uuid.uuid4().hex[:6]}@test.com")


@pytest.fixture
def operator_user(db_session: Session) -> User:
    return create_test_user(db_session, "operator", f"op-{uuid.uuid4().hex[:6]}@test.com")


@pytest.fixture
def owner_token(owner_user: User) -> str:
    from cocina_control.security.tokens import create_access_token

    return create_access_token(owner_user.id, owner_user.role)


@pytest.fixture
def operator_token(operator_user: User) -> str:
    from cocina_control.security.tokens import create_access_token

    return create_access_token(operator_user.id, operator_user.role)


# ---------------------------------------------------------------------------
# Test: login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_valid_credentials_returns_token(
    client: AsyncClient, owner_user: User
) -> None:
    reset_rate_limit("testclient")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": owner_user.email, "password": _TEST_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["role"] == "owner"
    assert data["user_id"] == str(owner_user.id)


@pytest.mark.asyncio
async def test_login_invalid_password_returns_401_generic(
    client: AsyncClient, owner_user: User
) -> None:
    reset_rate_limit("testclient")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": owner_user.email, "password": "wrong-password"},
    )
    assert response.status_code == 401
    # The message must not distinguish "user not found" from "wrong password"
    assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_nonexistent_email_returns_401(client: AsyncClient) -> None:
    reset_rate_limit("testclient")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.com", "password": "irrelevant"},
    )
    assert response.status_code == 401
    # Same message as wrong-password — no user enumeration
    assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_email_case_insensitive(client: AsyncClient, db_session: Session) -> None:
    """User created with lowercase email can log in with mixed-case email."""
    create_test_user(db_session, "operator", "juan@test.com")
    reset_rate_limit("testclient")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "Juan@Test.com", "password": _TEST_PASSWORD},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_login_expired_token_returns_401(
    client: AsyncClient, owner_user: User
) -> None:
    """A token with exp in the past must be rejected with 401."""
    from cocina_control.config import get_settings

    settings = get_settings()
    past = datetime.now(UTC) - timedelta(hours=1)
    expired_token = jwt.encode(
        {"sub": str(owner_user.id), "role": "owner", "iat": past, "exp": past},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response = await client.get(
        "/api/v1/_test/protected-owner",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_tampered_signature_returns_401(
    client: AsyncClient, owner_token: str
) -> None:
    """Modifying any character of a valid token must yield 401."""
    # Flip the last character of the signature segment
    parts = owner_token.split(".")
    parts[-1] = parts[-1][:-1] + ("A" if parts[-1][-1] != "A" else "B")
    tampered = ".".join(parts)

    response = await client.get(
        "/api/v1/_test/protected-owner",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test: current-user dependency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_no_token_returns_401(client: AsyncClient) -> None:
    """Accessing a protected endpoint without a token must return 401."""
    response = await client.get("/api/v1/_test/protected-owner")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test: role enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_role_owner_rejects_operator(
    client: AsyncClient, operator_token: str
) -> None:
    """An operator token must be rejected by an owner-only endpoint (403)."""
    response = await client.get(
        "/api/v1/_test/protected-owner",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_require_role_owner_accepts_owner(
    client: AsyncClient, owner_token: str
) -> None:
    """An owner token must be accepted by an owner-only endpoint (200)."""
    response = await client.get(
        "/api/v1/_test/protected-owner",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_role_reread_from_db_not_token(
    client: AsyncClient, db_session: Session
) -> None:
    """Role enforcement uses the DB value, not the JWT claim.

    Steps:
    1. Create a user as owner and mint an owner token.
    2. Downgrade the user to operator in the DB.
    3. The owner-only endpoint must now return 403, even though the token
       still carries role="owner".
    """
    user = create_test_user(db_session, "owner", f"downgrade-{uuid.uuid4().hex[:6]}@test.com")
    from cocina_control.security.tokens import create_access_token

    token = create_access_token(user.id, "owner")

    # Downgrade in DB
    user.role = "operator"
    db_session.flush()

    response = await client.get(
        "/api/v1/_test/protected-owner",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403, (
        "Role from DB must override the role claim in the token"
    )


# ---------------------------------------------------------------------------
# Test: logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_returns_204(client: AsyncClient, owner_token: str) -> None:
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# Test: CLI script create_owner
# ---------------------------------------------------------------------------


def test_create_owner_script_creates_user(postgres_url: str) -> None:
    """Run create_owner as a subprocess and verify the user exists in the DB.

    Uses the postgres_url fixture so it runs against the same ephemeral
    database as all other integration tests.  The script commits its own
    transaction, so the user is visible to a fresh connection.
    """
    import os

    from sqlalchemy import select

    from cocina_control.db import build_engine, build_session_factory
    from cocina_control.models.user import User

    test_email = f"cli-owner-{uuid.uuid4().hex[:6]}@test.com"
    test_name = "CLI Test Owner"
    test_password = "cli-test-password"

    env = {
        **os.environ,
        "COCINA_DATABASE_URL": postgres_url,
        "COCINA_JWT_SECRET": "test-secret-not-for-prod",
    }

    result = subprocess.run(
        [sys.executable, "-m", "cocina_control.scripts.create_owner",
         "--name", test_name, "--email", test_email],
        input=f"{test_password}\n{test_password}\n",
        capture_output=True,
        text=True,
        env=env,
        cwd="/home/fiax/cocina-control",
    )

    assert result.returncode == 0, (
        f"Script failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert test_email in result.stdout

    # Verify the user exists in the database
    engine = build_engine(postgres_url)
    factory = build_session_factory(engine)
    with factory() as session:
        user = session.scalar(select(User).where(User.email == test_email))
        assert user is not None, "User was not created in the database"
        assert user.name == test_name
        assert user.role == "owner"
        # Clean up so the test DB stays tidy
        session.delete(user)
        session.commit()
    engine.dispose()


# ---------------------------------------------------------------------------
# Test: rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_blocks_sixth_attempt(
    client: AsyncClient, owner_user: User
) -> None:
    """Six consecutive login attempts from the same IP: the sixth must get 429."""
    reset_rate_limit("testclient")
    for i in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"email": owner_user.email, "password": "wrong"},
        )
    # Sixth attempt
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": owner_user.email, "password": "wrong"},
    )
    assert response.status_code == 429
