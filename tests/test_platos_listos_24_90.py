"""Integration test de la migracion 0033: platos listos a S/ 24.90, Arma tu intactos."""

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa


@pytest.mark.anyio
async def test_la_migracion_unifica_los_platos_listos_y_se_puede_deshacer(
    postgres_url: str, db_engine
):
    from alembic import command
    from alembic.config import Config

    from cocina_control.db import build_engine

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    engine = build_engine(postgres_url)

    owner_id = uuid.uuid4()
    platos = {
        "Focus Bowl": (uuid.uuid4(), "27.00", "24.90"),
        "Wrap Fresh": (uuid.uuid4(), "25.00", "24.90"),
        "Arma tu Bowl": (uuid.uuid4(), "27.00", "27.00"),
    }

    def precio(conn, name):
        return conn.execute(
            sa.text("SELECT sale_price FROM products WHERE name = :n"), {"n": name}
        ).scalar()

    try:
        command.downgrade(cfg, "0032_toppings_y_bases")
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, name, email, password_hash, role) "
                    "VALUES (:id, 'Dueño', :email, 'x', 'owner')"
                ),
                {"id": owner_id, "email": f"owner-0033-{uuid.uuid4().hex[:6]}@test.com"},
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

        # Hasta 0033 y no a head: 0035 vuelve a mover un plato listo.
        command.upgrade(cfg, "0033_platos_listos_24_90")
        with engine.connect() as conn:
            for name, (_, _, despues) in platos.items():
                assert precio(conn, name) == Decimal(despues), name

        command.downgrade(cfg, "0032_toppings_y_bases")
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
