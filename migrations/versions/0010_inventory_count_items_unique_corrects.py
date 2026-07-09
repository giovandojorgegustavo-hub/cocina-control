"""inventory_count_items_unique_corrects

Add UNIQUE constraint on inventory_count_items.corrects_id to prevent chain
bifurcation: each item can be corrected at most once.

Problem: without this constraint, two concurrent corrections of the same
item_id can both pass the leaf check (neither sees the other's INSERT yet)
and both succeed, inserting two rows with the same corrects_id.  The
append-only chain silently forks.

Fix (two layers):
  Layer 1 (this migration): UNIQUE(corrects_id) causes the second concurrent
  INSERT to fail with IntegrityError, which the API layer catches and converts
  to HTTP 409.
  Layer 2 (API): SELECT FOR UPDATE on the inventory_count row serialises
  corrections at the application layer for the common case.

NULL values: PostgreSQL treats each NULL as distinct, so items with
corrects_id IS NULL (original items) are not affected — multiple originals
per session are allowed.

Revision ID: 0010_inventory_count_items_unique_corrects
Revises: 0009_delivery_orders_reason
Create Date: 2026-07-09

"""

import os
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_ici_uq_corrects"
down_revision: str | Sequence[str] | None = "0009_delivery_orders_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add unique constraint on corrects_id to prevent chain bifurcation."""
    op.create_unique_constraint(
        "uq_inventory_count_items_corrects_id",
        "inventory_count_items",
        ["corrects_id"],
    )


def downgrade() -> None:
    """Remove unique constraint on corrects_id.

    Raises RuntimeError in production to prevent accidental schema changes.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    op.drop_constraint(
        "uq_inventory_count_items_corrects_id",
        "inventory_count_items",
        type_="unique",
    )
