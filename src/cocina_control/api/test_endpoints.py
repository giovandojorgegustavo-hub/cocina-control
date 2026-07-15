"""Test-only endpoints.

This module is imported ONLY when app_env != "prod" (see main.py).
It must never be imported in production code paths.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from cocina_control.api.deps import require_any_role, require_role
from cocina_control.models.user import User

router = APIRouter()


@router.get("/_test/protected-owner", include_in_schema=False)
async def _test_protected_owner(
    user: Annotated[User, Depends(require_role("owner"))],
) -> dict:
    """Owner-only endpoint used exclusively by the test suite.

    Only registered when app_env != 'prod', so in production this path returns
    a genuine 404 — it is not even in the routing table.
    """
    return {"user_id": str(user.id), "role": user.role}


@router.get("/_test/protected-admin-or-owner", include_in_schema=False)
async def _test_protected_admin_or_owner(
    user: Annotated[User, Depends(require_any_role("owner", "admin"))],
) -> dict:
    """Owner-or-admin endpoint used exclusively by the test suite.

    Tests the require_any_role dependency with two allowed roles.
    Only registered when app_env != 'prod'.
    """
    return {"user_id": str(user.id), "role": user.role}
