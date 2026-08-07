"""service principals

Credencial para clientes no humanos que actuan en nombre de un usuario real
(caso motivador: el asistente de WhatsApp bonabowlinterno).

El esquema ya exige atribucion por persona via created_by/updated_by con
ON DELETE RESTRICT. Darle usuario propio al asistente satisface la foreign key
pero rompe ese invariante: todo quedaria a nombre del bot. Con esta tabla el
asistente presenta su token y nombra al usuario real en el header X-Act-As, y
la fila sigue registrando a la persona.

El token se guarda hasheado (SHA-256) y se revoca poniendo is_active en false.

Revision ID: 0017_service_principals
Revises: 0016_po_item_removed
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_service_principals"
down_revision: str | None = "0016_po_item_removed"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_principals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # Momento de la revocacion. Sin esto, el unico registro de cuando se
        # corto un acceso son los logs del servidor, que rotan; investigar un
        # incidente meses despues exige acotar esa ventana desde la base.
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Un hash nunca se repite, ni siquiera entre principals revocados: si el
    # mismo token vuelve a aparecer es un error de operacion, no un caso valido.
    op.create_index(
        "ix_service_principals_token_hash",
        "service_principals",
        ["token_hash"],
        unique=True,
    )
    # Nombre unico solo entre activos — mismo criterio que suppliers. Permite
    # rotar el token: se desactiva el viejo y se crea uno nuevo con igual nombre.
    op.create_index(
        "ix_service_principals_name_active_unique",
        "service_principals",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_service_principals_name_active_unique", table_name="service_principals")
    op.drop_index("ix_service_principals_token_hash", table_name="service_principals")
    op.drop_table("service_principals")
