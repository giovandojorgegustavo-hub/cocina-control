"""delivery_orders_unique_corrects

Add UniqueConstraint on delivery_orders.corrects_id to prevent concurrent
bifurcation of the append-only correction chain.  Only one new order can
reference a given order as corrects_id — the second concurrent INSERT
raises IntegrityError → HTTP 409 at the application layer.

This mirrors the same constraint already on delivery_items (migration 0006).

Revision ID: 0008_delivery_orders_unique_corrects
Revises: 0007_confirmed_audit
Create Date: 2026-07-09

"""

import os
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_do_unique_corrects"
down_revision: str | Sequence[str] | None = "0007_confirmed_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add unique constraint on delivery_orders.corrects_id."""
    op.create_unique_constraint(
        "uq_delivery_orders_corrects_id",
        "delivery_orders",
        ["corrects_id"],
    )


def downgrade() -> None:
    """Remove unique constraint on delivery_orders.corrects_id.

    Raises RuntimeError in production to prevent accidental data loss.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    op.drop_constraint(
        "uq_delivery_orders_corrects_id",
        "delivery_orders",
        type_="unique",
    )
