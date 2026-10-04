"""Integration test de la migracion 0028: salsas y guacamole.

La propiedad que se prueba: **salen palta, mayonesa y BBQ; los bowls suman
"Guacamole 4 oz" a +1.50 y los wraps pasan a su propio grupo "Salsa wrap" con
"Guacamole 2 oz" a +1.00 — y al bajar, todo vuelve a como estaba**.
"""

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa

_RETIRADAS = {"Salsa de palta proteica", "Mayonesa proteica", "Salsa BBQ"}
_SIN_COSTO = {"Honey Mustard proteica", "Salsa Runch proteica", "Vinagreta"}


@pytest.mark.anyio
async def test_la_migracion_cambia_las_salsas_y_se_puede_deshacer(postgres_url: str, db_engine):
    from alembic import command
    from alembic.config import Config

    from cocina_control.db import build_engine

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    engine = build_engine(postgres_url)

    owner_id = uuid.uuid4()
    focus_id = uuid.uuid4()
    wrap_id = uuid.uuid4()

    def activas(conn, grupo):
        return {
            r.name: r.price
            for r in conn.execute(
                sa.text(
                    "SELECT oi.name, oi.price FROM option_items oi "
                    "JOIN option_groups og ON og.id = oi.group_id "
                    "WHERE og.name = :g AND oi.is_active AND og.is_active"
                ),
                {"g": grupo},
            ).all()
        }

    def grupos_de(conn, product_id):
        return [
            r.name
            for r in conn.execute(
                sa.text(
                    "SELECT og.name FROM product_option_groups pog "
                    "JOIN option_groups og ON og.id = pog.group_id "
                    "WHERE pog.product_id = :p ORDER BY pog.sort_order"
                ),
                {"p": product_id},
            ).all()
        ]

    try:
        command.downgrade(cfg, "0027_carta_precios_x2")
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, name, email, password_hash, role) "
                    "VALUES (:id, 'Dueño', :email, 'x', 'owner')"
                ),
                {"id": owner_id, "email": f"owner-0028-{uuid.uuid4().hex[:6]}@test.com"},
            )
            salsa = conn.execute(
                sa.text("SELECT id FROM option_groups WHERE name = 'Salsa'")
            ).scalar()
            for pid, name in ((focus_id, "Focus Bowl"), (wrap_id, "Wrap Fresh")):
                conn.execute(
                    sa.text(
                        "INSERT INTO products (id, name, unit, is_active, is_purchase, "
                        "is_sale, sale_price, created_by) "
                        "VALUES (:id, :name, 'un', true, false, true, 20, :owner)"
                    ),
                    {"id": pid, "name": name, "owner": owner_id},
                )
                conn.execute(
                    sa.text(
                        "INSERT INTO product_option_groups (product_id, group_id, sort_order) "
                        "VALUES (:p, :g, 3)"
                    ),
                    {"p": pid, "g": salsa},
                )

        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            bowls = activas(conn, "Salsa")
            assert not (_RETIRADAS & set(bowls))
            assert _SIN_COSTO <= set(bowls)
            assert bowls["Guacamole 4 oz"] == Decimal("1.50")
            assert "Guacamole 2 oz" not in bowls

            wraps = activas(conn, "Salsa wrap")
            assert set(wraps) == _SIN_COSTO | {"Guacamole 2 oz"}
            assert wraps["Guacamole 2 oz"] == Decimal("1.00")
            assert all(wraps[n] == Decimal("0.00") for n in _SIN_COSTO)

            # El wrap cambia de grupo en la misma posicion; el bowl no se toca.
            assert grupos_de(conn, wrap_id) == ["Salsa wrap"]
            assert grupos_de(conn, focus_id) == ["Salsa"]

        command.downgrade(cfg, "0027_carta_precios_x2")
        with engine.connect() as conn:
            antes = activas(conn, "Salsa")
            assert _RETIRADAS <= set(antes)
            assert "Guacamole 4 oz" not in antes
            assert grupos_de(conn, wrap_id) == ["Salsa"]
            assert activas(conn, "Salsa wrap") == {}
    finally:
        with engine.begin() as conn:
            conn.execute(
                sa.text("DELETE FROM product_option_groups WHERE product_id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"ids": [focus_id, wrap_id]},
            )
            conn.execute(
                sa.text("DELETE FROM products WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"ids": [focus_id, wrap_id]},
            )
            conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": owner_id})
        command.upgrade(cfg, "head")
        engine.dispose()
