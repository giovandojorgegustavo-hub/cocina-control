import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    # `commit` entra por el contrato de fabrica (issue #150); su resolucion se
    # prueba aparte en test_health_commit.py. Aca solo se fija que status siga
    # siendo el campo que dice si la app esta lista.
    assert body["status"] == "ok"
