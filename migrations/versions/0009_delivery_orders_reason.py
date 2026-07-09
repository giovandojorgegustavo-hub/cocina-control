"""delivery_orders_reason

Add reason TEXT NULL column to delivery_orders.
Populated by cancel_order and correct_order to record why the order was
cancelled or corrected — visible to the owner via GET /delivery-orders/{id}.

Revision ID: 0009_delivery_orders_reason
Revises: 0008_do_unique_corrects
Create Date: 2026-07-09

"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_delivery_orders_reason"
down_revision: str | Sequence[str] | None = "0008_do_unique_corrects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add reason column to delivery_orders."""
    op.add_column(
        "delivery_orders",
        sa.Column("reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove reason column from delivery_orders.

    Raises RuntimeError in production to prevent accidental data loss.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    op.drop_column("delivery_orders", "reason")
