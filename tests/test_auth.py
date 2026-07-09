"""Integration tests for authentication (login, JWT, role enforcement).

Test database is provided by the db_session fixture from conftest.py.
Every test runs in a SAVEPOINT that is rolled back afterwards, so user
records created here never persist to other tests.
"""

import statistics
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
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
async def test_login_password_too_long_returns_422(client: AsyncClient) -> None:
    """A password longer than 128 characters must return 422, not 500.

    FastAPI validates the LoginRequest model before the handler runs, so the
    max_length=128 constraint on the password field produces a 422 Unprocessable
    Entity response without ever reaching bcrypt.
    """
    reset_rate_limit("testclient")
    long_password = "a" * 129
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "any@test.com", "password": long_password},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_empty_password_returns_422(client: AsyncClient) -> None:
    """An empty password must return 422 (min_length=1 on the field)."""
    reset_rate_limit("testclient")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "any@test.com", "password": ""},
    )
    assert response.status_code == 422


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
    """Modifying the payload segment of a valid token must yield 401.

    We alter a character in the middle of the second segment (payload) rather
    than the last character of the signature, because mutating the signature
    tail can occasionally produce a cryptographically equivalent base64 value.
    Mutating the payload always invalidates the MAC.
    """
    parts = owner_token.split(".")
    payload_b64 = parts[1]
    mid = len(payload_b64) // 2
    # Replace the character at the midpoint with a different one
    replacement = "A" if payload_b64[mid] != "A" else "B"
    parts[1] = payload_b64[:mid] + replacement + payload_b64[mid + 1:]
    tampered = ".".join(parts)

    response = await client.get(
        "/api/v1/_test/protected-owner",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test: timing attack resistance
# ---------------------------------------------------------------------------


@pytest.mark.timing
@pytest.mark.asyncio
async def test_login_timing_similar_for_missing_and_wrong_password(
    db_session: Session,
) -> None:
    """Response time for missing email must be similar to wrong password.

    Both paths call verify_password() — missing email uses a pre-computed dummy
    hash so the response time is constant-time regardless of whether the account
    exists.

    Threshold: median latency difference < 30 ms.  This test is marked
    @pytest.mark.timing and can be excluded in CI with: pytest -m "not timing"
    """
    from cocina_control.db import get_session
    from cocina_control.main import app

    def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override

    existing_email = f"timing-owner-{uuid.uuid4().hex[:6]}@test.com"
    create_test_user(db_session, "owner", existing_email)

    samples = 10

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Warm up bcrypt cache (JIT effects)
        reset_rate_limit("testclient")
        await ac.post(
            "/api/v1/auth/login",
            json={"email": "warmup@nowhere.com", "password": "warmup-pass"},
        )
        reset_rate_limit("testclient")
        await ac.post(
            "/api/v1/auth/login",
            json={"email": existing_email, "password": "warmup-wrong"},
        )

        missing_times: list[float] = []
        wrong_times: list[float] = []

        for _ in range(samples):
            reset_rate_limit("testclient")
            t0 = time.perf_counter()
            await ac.post(
                "/api/v1/auth/login",
                json={"email": f"notexist-{uuid.uuid4().hex}@nowhere.com", "password": "pass"},
            )
            missing_times.append((time.perf_counter() - t0) * 1000)

            reset_rate_limit("testclient")
            t0 = time.perf_counter()
            await ac.post(
                "/api/v1/auth/login",
                json={"email": existing_email, "password": "wrong-password"},
            )
            wrong_times.append((time.perf_counter() - t0) * 1000)

    app.dependency_overrides.pop(get_session, None)

    median_missing = statistics.median(missing_times)
    median_wrong = statistics.median(wrong_times)
    diff_ms = abs(median_missing - median_wrong)

    assert diff_ms < 30, (
        f"Timing difference too large — suggests user enumeration vulnerability. "
        f"Median missing={median_missing:.1f}ms, wrong={median_wrong:.1f}ms, "
        f"diff={diff_ms:.1f}ms (threshold: 30ms)"
    )


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
async def test_logout_with_valid_token_returns_204(
    client: AsyncClient, owner_token: str
) -> None:
    """Logout with a valid Bearer token returns 204."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_logout_without_token_returns_401(client: AsyncClient) -> None:
    """Logout without a Bearer token must return 401."""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 401


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
        "COCINA_JWT_SECRET": "test-secret-not-for-prod-min-32-chars-1234",
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


@pytest.mark.asyncio
async def test_rate_limit_uses_forwarded_for_when_proxy_configured(
    db_session: Session,
) -> None:
    """Rate limit counters key off X-Forwarded-For when the proxy middleware is active.

    The ProxyHeadersMiddleware (trusted_hosts=["127.0.0.1", "localhost"]) rewrites
    request.client.host with the value from X-Forwarded-For when the connection
    comes from a trusted upstream.  This test simulates two clients with distinct
    forwarded IPs and verifies that exhausting one counter does not affect the other.
    """
    from cocina_control.db import get_session
    from cocina_control.main import app
    from cocina_control.security.rate_limit import reset as rl_reset

    def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override

    ip_a = "10.0.0.1"
    ip_b = "10.0.0.2"

    rl_reset(ip_a)
    rl_reset(ip_b)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Exhaust the rate limit for ip_a (5 attempts)
        for _ in range(5):
            await ac.post(
                "/api/v1/auth/login",
                json={"email": "any@test.com", "password": "wrong"},
                headers={"X-Forwarded-For": ip_a},
            )

        # ip_a must now be rate-limited
        resp_a = await ac.post(
            "/api/v1/auth/login",
            json={"email": "any@test.com", "password": "wrong"},
            headers={"X-Forwarded-For": ip_a},
        )
        assert resp_a.status_code == 429, "ip_a should be rate-limited after 5 attempts"

        # ip_b must still be allowed (different counter)
        resp_b = await ac.post(
            "/api/v1/auth/login",
            json={"email": "any@test.com", "password": "wrong"},
            headers={"X-Forwarded-For": ip_b},
        )
        assert resp_b.status_code != 429, (
            f"ip_b should NOT be rate-limited — got {resp_b.status_code}"
        )

    app.dependency_overrides.pop(get_session, None)
    rl_reset(ip_a)
    rl_reset(ip_b)
