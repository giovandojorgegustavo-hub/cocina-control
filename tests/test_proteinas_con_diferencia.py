"""Integration test de la migracion 0030: la proteina cobra su diferencia de costo."""

from decimal import Decimal

import pytest
import sqlalchemy as sa


@pytest.mark.anyio
async def test_la_migracion_cobra_la_diferencia_y_se_puede_deshacer(postgres_url: str, db_engine):
    from alembic import command
    from alembic.config import Config

    from cocina_control.db import build_engine

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    engine = build_engine(postgres_url)

    def precios(conn):
        return {
            r.name: r.price
            for r in conn.execute(
                sa.text(
                    "SELECT oi.name, oi.price FROM option_items oi "
                    "JOIN option_groups og ON og.id = oi.group_id WHERE og.name = 'Proteína'"
                )
            ).all()
        }

    try:
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert precios(conn) == {
                "Sin proteína": Decimal("0.00"),
                "Filete de pollo": Decimal("0.00"),
                "Filete de pollo en salsa BBQ ahumada": Decimal("1.00"),
                "Milanesa": Decimal("2.00"),
                # 0031 la bajo de 3.00 a 2.50.
                "Tilapia": Decimal("2.50"),
            }

        command.downgrade(cfg, "0030_proteinas_con_diferencia")
        with engine.connect() as conn:
            assert precios(conn)["Tilapia"] == Decimal("3.00")

        command.downgrade(cfg, "0029_precios_minimo_25")
        with engine.connect() as conn:
            assert set(precios(conn).values()) == {Decimal("0.00")}
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
