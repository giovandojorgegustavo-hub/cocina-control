from fastapi import FastAPI

# IMPORTANT: ProxyHeadersMiddleware is required when running behind Caddy (or
# any reverse proxy on the same host).  Without it, request.client.host is
# always 127.0.0.1 (loopback), which makes the per-IP rate limiter useless.
# The operator MUST configure Caddy to forward the real client IP via the
# X-Forwarded-For header.  trusted_hosts is restricted to loopback only —
# only traffic that arrives via the local Caddy process is trusted.
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from cocina_control.api.auth import router as auth_router
from cocina_control.api.deliveries import router as deliveries_router
from cocina_control.api.health import router as health_router
from cocina_control.api.products import router as products_router
from cocina_control.config import get_settings

app = FastAPI(
    title="Cocina Control API",
    version="0.1.0",
    description="Dark-kitchen inventory system API",
)

# Trust X-Forwarded-For only from loopback (Caddy runs on the same droplet).
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "localhost"])

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(products_router, prefix="/api/v1")
app.include_router(deliveries_router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Test-only endpoints
#
# In non-prod environments the test router is included so that the test suite
# can exercise role enforcement without shipping a real protected resource.
# In production (app_env == "prod") the router is never registered, so the
# path returns a genuine 404 — not a guarded 401/403.
# ---------------------------------------------------------------------------
settings = get_settings()
if settings.app_env != "prod":
    from cocina_control.api.test_endpoints import router as test_router  # noqa: PLC0415

    app.include_router(test_router, prefix="/api/v1", tags=["_test"])
