"""Regression guards for the release pipeline (.github/workflows/release.yml).

The deploy job cannot be exercised by the test suite — it only runs against the
real server. So the one thing we can do is pin the invariants that already broke
a release once, in the file itself.
"""

from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow_code(workflow_text: str) -> str:
    """El workflow sin sus comentarios.

    Hace falta para poder afirmar cosas sobre los flags REALES: un comentario
    que documente por que no usamos una opcion no puede contar como si la
    usaramos. (Este test se cayo exactamente por eso la primera vez.)
    """
    lines = []
    for raw in workflow_text.splitlines():
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            continue
        lines.append(raw)
    return "\n".join(lines)


def test_release_workflow_exists():
    assert WORKFLOW.is_file(), f"falta {WORKFLOW}"


def test_rsync_excludes_pycache(workflow_code: str):
    """Issue #123: root-owned .pyc en el deploy path abortaban el release.

    __pycache__ lo genera el server, no el repo. Un script CLI corrido como
    root deja .pyc de root dentro de un deploy path del usuario de deploy;
    rsync --delete intenta borrarlos, cobra EACCES y corta con codigo 23.
    """
    assert "--exclude '__pycache__/'" in workflow_code
    assert "--exclude '*.pyc'" in workflow_code


def test_rsync_never_deletes_excluded(workflow_code: str):
    """--delete-excluded revive el issue #123: borraria los .pyc ajenos."""
    assert "--delete-excluded" not in workflow_code


def test_backup_runs_before_any_rsync(workflow_code: str):
    """El pg_dump va antes de tocar codigo: sin backup no hay rollback."""
    backup_at = workflow_code.index("Backup PostgreSQL")
    rsync_at = workflow_code.index("Rsync backend source")
    assert backup_at < rsync_at
