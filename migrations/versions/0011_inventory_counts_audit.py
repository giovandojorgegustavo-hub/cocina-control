"""inventory_counts_audit

Add audit columns to inventory_counts and reason column to inventory_count_items.

inventory_counts:
  - updated_at TIMESTAMPTZ NULL — stamped when complete() or a correction changes
    the count session.
  - updated_by UUID NULL FK(users.id) — who triggered the last change.

inventory_count_items:
  - reason TEXT NULL — optional explanation for correction rows.  NULL on
    original items; set by correct_item() when the caller provides it.

Revision ID: 0011_inventory_counts_audit
Revises: 0010_inventory_count_items_unique_corrects
Create Date: 2026-07-09

"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_ic_audit"
down_revision: str | Sequence[str] | None = "0010_ici_uq_corrects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add updated_at/updated_by to inventory_counts and reason to inventory_count_items."""
    op.add_column(
        "inventory_counts",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "inventory_counts",
        sa.Column(
            "updated_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "inventory_count_items",
        sa.Column("reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove audit columns.

    Raises RuntimeError in production to prevent accidental data loss.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    op.drop_column("inventory_count_items", "reason")
    op.drop_column("inventory_counts", "updated_by")
    op.drop_column("inventory_counts", "updated_at")
