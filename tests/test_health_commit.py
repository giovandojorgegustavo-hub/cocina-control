"""El contrato de salud de fabrica (docs/salud-endpoint.md).

Sin el campo `commit`, `scripts/deploy.sh` no puede confirmar que el proceso
vivo corre lo que se acaba de desplegar y falla el deploy. Estos tests fijan
el contrato para que nadie lo quite sin enterarse.
"""

import importlib

import pytest
from httpx import AsyncClient

import cocina_control.api.health as health


def _recargar(monkeypatch, *, env=None, cwd=None, tmp_path=None):
    """Re-importa el modulo para volver a resolver el commit de arranque."""
    if env is None:
        monkeypatch.delenv("APP_COMMIT", raising=False)
    else:
        monkeypatch.setenv("APP_COMMIT", env)
    if cwd is not None:
        monkeypatch.chdir(cwd)
    elif tmp_path is not None:
        monkeypatch.chdir(tmp_path)
    return importlib.reload(health)


@pytest.mark.asyncio
async def test_health_expone_status_y_commit(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "commit" in body


def test_toma_el_sha_de_la_variable_de_entorno(monkeypatch, tmp_path):
    sha = "a" * 40
    mod = _recargar(monkeypatch, env=sha, tmp_path=tmp_path)
    assert mod.APP_COMMIT == sha


def test_toma_el_sha_del_archivo_del_despliegue(monkeypatch, tmp_path):
    sha = "b" * 40
    (tmp_path / "COMMIT").write_text(sha + "\n", encoding="utf-8")
    mod = _recargar(monkeypatch, tmp_path=tmp_path)
    assert mod.APP_COMMIT == sha


def test_la_variable_gana_sobre_el_archivo(monkeypatch, tmp_path):
    (tmp_path / "COMMIT").write_text("b" * 40, encoding="utf-8")
    mod = _recargar(monkeypatch, env="c" * 40, tmp_path=tmp_path)
    assert mod.APP_COMMIT == "c" * 40


def test_sin_fuente_reporta_unknown(monkeypatch, tmp_path):
    """unknown nunca coincide con el commit desplegado: deploy.sh falla, que es
    lo correcto. Devolver algo plausible seria peor que no devolver nada."""
    mod = _recargar(monkeypatch, tmp_path=tmp_path)
    assert mod.APP_COMMIT == "unknown"


@pytest.mark.parametrize("basura", ["no-es-un-sha", "abc123", "A" * 40, "a" * 39, ""])
def test_rechaza_lo_que_no_sea_un_sha_completo(monkeypatch, tmp_path, basura):
    """Un SHA corto o en mayusculas no coincidiria con el desplegado; mejor
    decir unknown que publicar algo que parece valido y no lo es."""
    (tmp_path / "COMMIT").write_text(basura, encoding="utf-8")
    mod = _recargar(monkeypatch, tmp_path=tmp_path)
    assert mod.APP_COMMIT == "unknown"
