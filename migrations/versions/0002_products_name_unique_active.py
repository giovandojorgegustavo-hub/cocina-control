"""products_name_unique_active

Make the products.name index a unique partial index filtered by is_active = true.
This allows the same product name to be reused after deactivation.

Revision ID: 0002_products_name_unique_active
Revises: 85ec14b1dea9
Create Date: 2026-07-09

"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_products_name_unique_active"
down_revision: Union[str, Sequence[str], None] = "85ec14b1dea9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace the non-unique partial index with a unique one."""
    # Drop the existing non-unique partial index created in 0001.
    op.drop_index(
        "ix_products_name_active",
        table_name="products",
        postgresql_where=sa.text("is_active = true"),
    )
    # Create a unique partial index: uniqueness is enforced only among active products.
    # Inactive products with the same name are explicitly allowed.
    op.create_index(
        "ix_products_name_active_unique",
        "products",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    """Revert to the non-unique partial index.

    Raises RuntimeError in production to prevent accidental data loss.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    op.drop_index(
        "ix_products_name_active_unique",
        table_name="products",
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "ix_products_name_active",
        "products",
        ["name"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
