"""purchase_orders_schema

Add purchase_orders, purchase_order_items, purchase_order_item_costs,
purchase_order_status_events tables (v0.3 partidas + costos).

Also adds two nullable FK columns to existing tables (backward-compatible):
  - deliveries.purchase_order_id
  - delivery_items.purchase_order_item_id

Revision ID: 0012_po_schema
Revises: 0011_ic_audit
Create Date: 2026-07-13

"""

import os
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_po_schema"
down_revision: str | Sequence[str] | None = "0011_ic_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    """Create 4 new tables, DB-layer role guard triggers, and 2 nullable columns on existing tables."""

    # ------------------------------------------------------------------
    # 1. purchase_orders
    # ------------------------------------------------------------------
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column("supplier_name", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_purchase_orders_created_by"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "corrects_id",
            sa.Uuid(),
            sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT", name="fk_purchase_orders_corrects_id"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("corrects_id", name="uq_purchase_orders_corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_purchase_orders_no_self_correction",
        ),
    )
    op.create_index("ix_purchase_orders_created_by", "purchase_orders", ["created_by"])
    op.create_index("ix_purchase_orders_corrects_id", "purchase_orders", ["corrects_id"])

    # ------------------------------------------------------------------
    # 2. purchase_order_items
    # ------------------------------------------------------------------
    op.create_table(
        "purchase_order_items",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "purchase_order_id",
            sa.Uuid(),
            sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT", name="fk_purchase_order_items_order_id"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="RESTRICT", name="fk_purchase_order_items_product_id"),
            nullable=False,
        ),
        sa.Column("expected_qty", sa.Numeric(), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_purchase_order_items_created_by"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "corrects_id",
            sa.Uuid(),
            sa.ForeignKey("purchase_order_items.id", ondelete="RESTRICT", name="fk_purchase_order_items_corrects_id"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("corrects_id", name="uq_purchase_order_items_corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_purchase_order_items_no_self_correction",
        ),
        sa.CheckConstraint(
            "expected_qty > 0",
            name="ck_purchase_order_items_expected_qty_positive",
        ),
    )
    op.create_index(
        "ix_purchase_order_items_order_id", "purchase_order_items", ["purchase_order_id"]
    )
    op.create_index(
        "ix_purchase_order_items_product_id", "purchase_order_items", ["product_id"]
    )
    op.create_index(
        "ix_purchase_order_items_corrects_id", "purchase_order_items", ["corrects_id"]
    )
    # Partial unique: one ROOT item (corrects_id IS NULL) per product per order.
    # Combined with UNIQUE(corrects_id) globally, this guarantees a single linear
    # correction chain per product.  The leaf is identified with NOT EXISTS, not
    # this index (see decisiones-orden-compra.md P3).
    op.create_index(
        "uq_purchase_order_items_root_per_product",
        "purchase_order_items",
        ["purchase_order_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("corrects_id IS NULL"),
    )

    # ------------------------------------------------------------------
    # 3. purchase_order_item_costs
    # ------------------------------------------------------------------
    op.create_table(
        "purchase_order_item_costs",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "purchase_order_item_id",
            sa.Uuid(),
            sa.ForeignKey(
                "purchase_order_items.id",
                ondelete="RESTRICT",
                name="fk_purchase_order_item_costs_item_id",
            ),
            nullable=False,
        ),
        sa.Column("unit_cost", sa.Numeric(), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_purchase_order_item_costs_created_by"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "corrects_id",
            sa.Uuid(),
            sa.ForeignKey(
                "purchase_order_item_costs.id",
                ondelete="RESTRICT",
                name="fk_purchase_order_item_costs_corrects_id",
            ),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("corrects_id", name="uq_purchase_order_item_costs_corrects_id"),
        sa.CheckConstraint(
            "corrects_id IS DISTINCT FROM id",
            name="ck_purchase_order_item_costs_no_self_correction",
        ),
        sa.CheckConstraint(
            "unit_cost > 0",
            name="ck_purchase_order_item_costs_positive",
        ),
    )
    op.create_index(
        "ix_purchase_order_item_costs_item_id",
        "purchase_order_item_costs",
        ["purchase_order_item_id"],
    )
    op.create_index(
        "ix_purchase_order_item_costs_corrects_id",
        "purchase_order_item_costs",
        ["corrects_id"],
    )

    # ------------------------------------------------------------------
    # 4. purchase_order_status_events  (immutable event log — no corrects_id)
    # ------------------------------------------------------------------
    op.create_table(
        "purchase_order_status_events",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "purchase_order_id",
            sa.Uuid(),
            sa.ForeignKey(
                "purchase_orders.id",
                ondelete="RESTRICT",
                name="fk_purchase_order_status_events_order_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.Enum(
                "closed_auto", "closed_manual", "reopened", "annulled",
                name="purchase_order_status_event_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_purchase_order_status_events_created_by"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_purchase_order_status_events_order_created",
        "purchase_order_status_events",
        ["purchase_order_id", sa.text("created_at DESC")],
    )

    # ------------------------------------------------------------------
    # 5. DB-layer role guards (triggers + functions)
    #
    # purchase_orders, purchase_order_items, purchase_order_item_costs:
    #   BEFORE INSERT must have created_by with role='owner'.
    #
    # purchase_order_status_events:
    #   closed_manual, reopened, annulled → role='owner' required.
    #   closed_auto → any valid user role (validated at app layer that it
    #   corresponds to a partida completion).
    # ------------------------------------------------------------------

    op.execute("""
CREATE OR REPLACE FUNCTION cocina_require_owner_creator() RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE id = NEW.created_by AND role = 'owner') THEN
        RAISE EXCEPTION 'created_by must be a user with role=owner (got role=%)',
            (SELECT role FROM users WHERE id = NEW.created_by);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

    op.execute("""
CREATE TRIGGER trg_purchase_orders_owner_creator
BEFORE INSERT ON purchase_orders
FOR EACH ROW EXECUTE FUNCTION cocina_require_owner_creator();
""")

    op.execute("""
CREATE TRIGGER trg_purchase_order_items_owner_creator
BEFORE INSERT ON purchase_order_items
FOR EACH ROW EXECUTE FUNCTION cocina_require_owner_creator();
""")

    op.execute("""
CREATE TRIGGER trg_purchase_order_item_costs_owner_creator
BEFORE INSERT ON purchase_order_item_costs
FOR EACH ROW EXECUTE FUNCTION cocina_require_owner_creator();
""")

    op.execute("""
CREATE OR REPLACE FUNCTION cocina_check_po_status_event_role() RETURNS TRIGGER AS $$
DECLARE
    v_role TEXT;
BEGIN
    IF NEW.event_type IN ('closed_manual', 'reopened', 'annulled') THEN
        SELECT role INTO v_role FROM users WHERE id = NEW.created_by;
        IF v_role IS DISTINCT FROM 'owner' THEN
            RAISE EXCEPTION 'event_type=% requires created_by with role=owner (got role=%)',
                NEW.event_type, v_role;
        END IF;
    END IF;
    -- closed_auto: no role restriction (validated at app layer that it
    -- corresponds to a partida completion).
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

    op.execute("""
CREATE TRIGGER trg_purchase_order_status_events_role_check
BEFORE INSERT ON purchase_order_status_events
FOR EACH ROW EXECUTE FUNCTION cocina_check_po_status_event_role();
""")

    # ------------------------------------------------------------------
    # 6. Nullable FK columns on existing tables (backward-compatible)
    # ------------------------------------------------------------------
    op.add_column(
        "deliveries",
        sa.Column(
            "purchase_order_id",
            sa.Uuid(),
            sa.ForeignKey(
                "purchase_orders.id",
                ondelete="RESTRICT",
                name="fk_deliveries_purchase_order_id",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_deliveries_purchase_order_id", "deliveries", ["purchase_order_id"]
    )

    op.add_column(
        "delivery_items",
        sa.Column(
            "purchase_order_item_id",
            sa.Uuid(),
            sa.ForeignKey(
                "purchase_order_items.id",
                ondelete="RESTRICT",
                name="fk_delivery_items_purchase_order_item_id",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_delivery_items_purchase_order_item_id",
        "delivery_items",
        ["purchase_order_item_id"],
    )


def downgrade() -> None:
    """Drop purchase_order tables and nullable columns added in upgrade.

    Raises RuntimeError in production to prevent accidental data loss.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    # Drop triggers and functions before dropping the tables they depend on.
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_order_status_events_role_check ON purchase_order_status_events;")
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_order_item_costs_owner_creator ON purchase_order_item_costs;")
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_order_items_owner_creator ON purchase_order_items;")
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_orders_owner_creator ON purchase_orders;")
    op.execute("DROP FUNCTION IF EXISTS cocina_check_po_status_event_role();")
    op.execute("DROP FUNCTION IF EXISTS cocina_require_owner_creator();")

    # Reverse order of upgrade.
    op.drop_index("ix_delivery_items_purchase_order_item_id", table_name="delivery_items")
    op.drop_column("delivery_items", "purchase_order_item_id")

    op.drop_index("ix_deliveries_purchase_order_id", table_name="deliveries")
    op.drop_column("deliveries", "purchase_order_id")

    op.drop_index(
        "ix_purchase_order_status_events_order_created",
        table_name="purchase_order_status_events",
    )
    op.drop_table("purchase_order_status_events")
    sa.Enum(name="purchase_order_status_event_type").drop(op.get_bind(), checkfirst=True)

    op.drop_index(
        "ix_purchase_order_item_costs_corrects_id",
        table_name="purchase_order_item_costs",
    )
    op.drop_index(
        "ix_purchase_order_item_costs_item_id",
        table_name="purchase_order_item_costs",
    )
    op.drop_table("purchase_order_item_costs")

    op.drop_index(
        "uq_purchase_order_items_root_per_product",
        table_name="purchase_order_items",
    )
    op.drop_index(
        "ix_purchase_order_items_corrects_id", table_name="purchase_order_items"
    )
    op.drop_index(
        "ix_purchase_order_items_product_id", table_name="purchase_order_items"
    )
    op.drop_index(
        "ix_purchase_order_items_order_id", table_name="purchase_order_items"
    )
    op.drop_table("purchase_order_items")

    op.drop_index("ix_purchase_orders_corrects_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_created_by", table_name="purchase_orders")
    op.drop_table("purchase_orders")
