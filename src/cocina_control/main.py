from typing import Annotated

from fastapi import Depends, FastAPI

from cocina_control.api.auth import router as auth_router
from cocina_control.api.health import router as health_router
from cocina_control.models.user import User

app = FastAPI(
    title="Cocina Control API",
    version="0.1.0",
    description="Dark-kitchen inventory system API",
)

app.include_router(health_router)
app.include_router(auth_router)

# ---------------------------------------------------------------------------
# Test-only endpoint
#
# This route is always registered but carries include_in_schema=False so it
# never appears in the production OpenAPI spec.  An additional runtime guard
# checks app_env: if it is "prod" the endpoint returns 404 immediately.
# We cannot evaluate get_settings() at import time because COCINA_DATABASE_URL
# may not be present during test collection (the URL is injected by the
# db_engine fixture).
# ---------------------------------------------------------------------------
from cocina_control.api.deps import require_role  # noqa: E402


@app.get("/api/v1/_test/protected-owner", include_in_schema=False)
async def _test_protected_owner(
    user: Annotated[User, Depends(require_role("owner"))],
) -> dict:
    """Owner-only endpoint used exclusively by the test suite.

    In production (app_env == 'prod') this returns 404 so it is effectively
    unreachable even if someone discovers the path.
    """
    from fastapi import HTTPException

    from cocina_control.config import get_settings

    if get_settings().app_env == "prod":
        raise HTTPException(status_code=404)
    return {"user_id": str(user.id), "role": user.role}
