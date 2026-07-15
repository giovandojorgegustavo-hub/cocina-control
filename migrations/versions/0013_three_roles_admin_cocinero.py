"""three_roles_admin_cocinero

Expand user_role enum from (operator, owner) to (cocinero, owner, admin).

Changes:
- Rename enum value 'operator' -> 'cocinero'.
- Add enum value 'admin'.
- Replace DB triggers that required role='owner' to accept 'owner' OR 'admin':
    cocina_require_owner_creator  -> cocina_require_admin_or_owner_creator
    cocina_check_po_status_event_role  (same name, extended to owner/admin)

Revision ID: 0013_three_roles
Revises: 0012_po_schema
Create Date: 2026-07-14

Downgrade note
--------------
Postgres does not support DROP VALUE on an enum.  The downgrade reverts the
enum by creating a temporary type (user_role_v0) with ('operator', 'owner'),
migrating the column, dropping the old type, and renaming the temporary one.
This is only exercisable in dev/test (the production guard blocks it).
"""

import os
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_three_roles"
down_revision: str | Sequence[str] | None = "0012_po_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Extend user_role enum and update PL/pgSQL triggers accordingly."""

    # ------------------------------------------------------------------
    # 1. Expand the enum.
    #    RENAME VALUE renames 'operator' -> 'cocinero' in the type catalog;
    #    all existing rows that held 'operator' are automatically read back
    #    as 'cocinero' — no UPDATE of the users table is needed.
    #    ADD VALUE appends 'admin' to the enum.
    #    Both statements are supported inside a transaction in Postgres 12+.
    # ------------------------------------------------------------------
    op.execute("ALTER TYPE user_role RENAME VALUE 'operator' TO 'cocinero'")
    op.execute("ALTER TYPE user_role ADD VALUE 'admin'")

    # ------------------------------------------------------------------
    # 2. Replace cocina_require_owner_creator with
    #    cocina_require_admin_or_owner_creator (allows owner OR admin).
    # ------------------------------------------------------------------
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_orders_owner_creator ON purchase_orders")
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_order_items_owner_creator ON purchase_order_items")
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_order_item_costs_owner_creator ON purchase_order_item_costs")
    op.execute("DROP FUNCTION IF EXISTS cocina_require_owner_creator()")

    op.execute("""
CREATE OR REPLACE FUNCTION cocina_require_admin_or_owner_creator() RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM users
        WHERE id = NEW.created_by
          AND role IN ('owner', 'admin')
    ) THEN
        RAISE EXCEPTION 'created_by must be a user with role in (owner, admin) (got role=%)',
            (SELECT role FROM users WHERE id = NEW.created_by);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

    op.execute("""
CREATE TRIGGER trg_purchase_orders_admin_or_owner_creator
BEFORE INSERT ON purchase_orders
FOR EACH ROW EXECUTE FUNCTION cocina_require_admin_or_owner_creator();
""")

    op.execute("""
CREATE TRIGGER trg_purchase_order_items_admin_or_owner_creator
BEFORE INSERT ON purchase_order_items
FOR EACH ROW EXECUTE FUNCTION cocina_require_admin_or_owner_creator();
""")

    op.execute("""
CREATE TRIGGER trg_purchase_order_item_costs_admin_or_owner_creator
BEFORE INSERT ON purchase_order_item_costs
FOR EACH ROW EXECUTE FUNCTION cocina_require_admin_or_owner_creator();
""")

    # ------------------------------------------------------------------
    # 3. Replace cocina_check_po_status_event_role to accept owner OR admin
    #    for closed_manual, reopened, annulled.
    # ------------------------------------------------------------------
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_order_status_events_role_check ON purchase_order_status_events")
    op.execute("DROP FUNCTION IF EXISTS cocina_check_po_status_event_role()")

    op.execute("""
CREATE OR REPLACE FUNCTION cocina_check_po_status_event_role() RETURNS TRIGGER AS $$
DECLARE
    v_role TEXT;
BEGIN
    IF NEW.event_type IN ('closed_manual', 'reopened', 'annulled') THEN
        SELECT role INTO v_role FROM users WHERE id = NEW.created_by;
        IF v_role NOT IN ('owner', 'admin') THEN
            RAISE EXCEPTION 'event_type=% requires created_by with role in (owner, admin) (got role=%)',
                NEW.event_type, v_role;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

    op.execute("""
CREATE TRIGGER trg_purchase_order_status_events_role_check
BEFORE INSERT ON purchase_order_status_events
FOR EACH ROW EXECUTE FUNCTION cocina_check_po_status_event_role();
""")


def downgrade() -> None:
    """Revert to two-role enum (operator, owner) and restore original triggers.

    IMPORTANT: Postgres does not support ALTER TYPE ... DROP VALUE.
    The enum reversion is done via a temporary type user_role_v0.
    This downgrade is only runnable in dev/test — production is guarded.
    """
    app_env = os.environ.get("COCINA_APP_ENV", "dev")
    if app_env == "prod":
        raise RuntimeError(
            "Downgrade prohibited in production — restore from PostgreSQL backup instead"
        )

    # 1. Migrate any admin users to cocinero (they will become 'operator'
    #    once the enum is swapped back below).
    op.execute("UPDATE users SET role = 'cocinero' WHERE role = 'admin'")

    # 2. Drop the new triggers and functions.
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_orders_admin_or_owner_creator ON purchase_orders")
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_order_items_admin_or_owner_creator ON purchase_order_items")
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_order_item_costs_admin_or_owner_creator ON purchase_order_item_costs")
    op.execute("DROP TRIGGER IF EXISTS trg_purchase_order_status_events_role_check ON purchase_order_status_events")
    op.execute("DROP FUNCTION IF EXISTS cocina_require_admin_or_owner_creator()")
    op.execute("DROP FUNCTION IF EXISTS cocina_check_po_status_event_role()")

    # 3. Swap enum via a temporary type.
    #    user_role currently has values ('cocinero', 'owner', 'admin').
    #    We need to go back to ('operator', 'owner').
    #    Since DROP VALUE is not supported, we create a temporary enum,
    #    migrate the column using a CASE expression, drop the old type,
    #    and rename the temporary one.
    op.execute("CREATE TYPE user_role_v0 AS ENUM ('operator', 'owner')")
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN role TYPE user_role_v0
        USING (CASE WHEN role::text = 'cocinero' THEN 'operator' ELSE role::text END)::user_role_v0
    """)
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_v0 RENAME TO user_role")

    # 4. Recreate the OLD triggers/functions (owner-only, matching 0012 state).
    op.execute("""
        CREATE OR REPLACE FUNCTION cocina_require_owner_creator() RETURNS TRIGGER AS $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM users WHERE id = NEW.created_by AND role = 'owner') THEN
                RAISE EXCEPTION 'created_by must be a user with role=owner (got role=%)',
                    (SELECT role FROM users WHERE id = NEW.created_by);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_purchase_orders_owner_creator
        BEFORE INSERT ON purchase_orders
        FOR EACH ROW EXECUTE FUNCTION cocina_require_owner_creator()
    """)
    op.execute("""
        CREATE TRIGGER trg_purchase_order_items_owner_creator
        BEFORE INSERT ON purchase_order_items
        FOR EACH ROW EXECUTE FUNCTION cocina_require_owner_creator()
    """)
    op.execute("""
        CREATE TRIGGER trg_purchase_order_item_costs_owner_creator
        BEFORE INSERT ON purchase_order_item_costs
        FOR EACH ROW EXECUTE FUNCTION cocina_require_owner_creator()
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
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_purchase_order_status_events_role_check
        BEFORE INSERT ON purchase_order_status_events
        FOR EACH ROW EXECUTE FUNCTION cocina_check_po_status_event_role()
    """)
