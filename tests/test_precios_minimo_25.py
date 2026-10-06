"""Integration test de la migracion 0029: escalera de precios de S/ 25 a S/ 28."""

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa


@pytest.mark.anyio
async def test_la_migracion_sube_la_escalera_y_se_puede_deshacer(postgres_url: str, db_engine):
    from alembic import command
    from alembic.config import Config

    from cocina_control.db import build_engine

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    engine = build_engine(postgres_url)

    owner_id = uuid.uuid4()
    platos = {
        "Wrap Fresh": (uuid.uuid4(), "20.00", "25.00"),
        "Wrap Mediterráneo Verde": (uuid.uuid4(), "21.00", "26.00"),
        "BBQ Protein Salad": (uuid.uuid4(), "25.00", "28.00"),
        # Un extra no es un plato: no se toca.
        "Chucrut púrpura 4 oz": (uuid.uuid4(), "8.00", "8.00"),
    }

    def precio(conn, name):
        return conn.execute(
            sa.text("SELECT sale_price FROM products WHERE name = :n"), {"n": name}
        ).scalar()

    try:
        command.downgrade(cfg, "0028_salsas_y_guacamole")
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, name, email, password_hash, role) "
                    "VALUES (:id, 'Dueño', :email, 'x', 'owner')"
                ),
                {"id": owner_id, "email": f"owner-0029-{uuid.uuid4().hex[:6]}@test.com"},
            )
            for name, (pid, antes, _) in platos.items():
                conn.execute(
                    sa.text(
                        "INSERT INTO products (id, name, unit, is_active, is_purchase, "
                        "is_sale, sale_price, created_by) "
                        "VALUES (:id, :name, 'un', true, false, true, :price, :owner)"
                    ),
                    {"id": pid, "name": name, "price": antes, "owner": owner_id},
                )

        # Hasta 0029 y no a head: 0033 vuelve a mover los platos listos.
        command.upgrade(cfg, "0029_precios_minimo_25")
        with engine.connect() as conn:
            for name, (_, _, despues) in platos.items():
                assert precio(conn, name) == Decimal(despues), name

        command.downgrade(cfg, "0028_salsas_y_guacamole")
        with engine.connect() as conn:
            for name, (_, antes, _) in platos.items():
                assert precio(conn, name) == Decimal(antes), name
    finally:
        with engine.begin() as conn:
            conn.execute(
                sa.text("DELETE FROM products WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"ids": [pid for pid, _, _ in platos.values()]},
            )
            conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": owner_id})
        command.upgrade(cfg, "head")
        engine.dispose()
