"""delivery_item_reason

Add nullable `reason` column to delivery_items to persist the operator's or
owner's explanation when correcting an item after validation.

The column is intentionally nullable:
- Original items created during pre-load never have a reason.
- Confirmation updates (en_verificacion) do not require a reason.
- Correction items (corrects_id IS NOT NULL) may optionally carry a reason.

Storing reason in the row — rather than ignoring it — keeps the forensic CSV
complete: the owner can see *why* a quantity was corrected without needing a
side channel.

Revision ID: 0005_delivery_item_reason
Revises: 0004_delivery_audit_columns
Create Date: 2026-07-09

"""

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_delivery_item_reason"
down_revision: Union[str, Sequence[str], None] = "0004_delivery_audit_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add reason column to delivery_items (nullable TEXT)."""
    op.add_column(
        "delivery_items",
        sa.Column("reason", sa.Text, nullable=True),
    )


def downgrade() -> None:
    """Remove reason column from delivery_items.

    Raises RuntimeError in production to prevent accidental data loss.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    op.drop_column("delivery_items", "reason")
