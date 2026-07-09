import pytest
from httpx import ASGITransport, AsyncClient

from cocina_control.main import app


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
