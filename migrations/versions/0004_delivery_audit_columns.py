"""delivery_audit_columns

Add updated_at and updated_by to deliveries to record who last edited a
draft delivery and when.  Both columns are nullable: existing rows have no
mutation history.

Revision ID: 0004_delivery_audit_columns
Revises: 0003_product_audit_columns
Create Date: 2026-07-09

"""

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_delivery_audit_columns"
down_revision: Union[str, Sequence[str], None] = "0003_product_audit_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add updated_at and updated_by columns to deliveries.

    Both columns are nullable: existing rows have no mutation history.
    The FK on updated_by uses RESTRICT so a user cannot be deleted while
    they are the last editor of a delivery.
    """
    op.add_column(
        "deliveries",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "deliveries",
        sa.Column(
            "updated_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove audit columns added in this revision.

    Raises RuntimeError in production to prevent accidental data loss.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    op.drop_column("deliveries", "updated_by")
    op.drop_column("deliveries", "updated_at")
