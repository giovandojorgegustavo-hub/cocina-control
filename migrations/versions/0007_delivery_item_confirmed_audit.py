"""delivery_item_confirmed_audit

Add confirmed_by (FK → users) and confirmed_at (timestamptz) columns to
delivery_items to record who confirmed each item and when.

These columns are set by the confirm_item endpoint (operator sets
received_qty during en_verificacion).  They remain NULL on:
  - Pre-load rows (created during POST /deliveries — no confirmation yet).
  - Correction rows (created during POST /correct — those carry created_by).

The columns are NOT exposed in the public API by default.  Traceability lives
in the DB for internal audit and forensic CSV export.

Revision ID: 0007_delivery_item_confirmed_audit
Revises: 0006_delivery_items_unique_corrects
Create Date: 2026-07-09

"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_confirmed_audit"
down_revision: str | Sequence[str] | None = "0006_uq_corrects_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add confirmed_by and confirmed_at audit columns to delivery_items."""
    op.add_column(
        "delivery_items",
        sa.Column(
            "confirmed_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "delivery_items",
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove confirmed_by and confirmed_at columns from delivery_items.

    Raises RuntimeError in production to prevent accidental data loss.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    op.drop_column("delivery_items", "confirmed_at")
    op.drop_column("delivery_items", "confirmed_by")
