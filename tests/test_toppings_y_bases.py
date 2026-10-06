"""Integration test de la migracion 0032: toppings y bases del Arma tu Bowl."""

from decimal import Decimal

import pytest
import sqlalchemy as sa


@pytest.mark.anyio
async def test_la_migracion_cambia_toppings_y_bases_y_se_puede_deshacer(
    postgres_url: str, db_engine
):
    from alembic import command
    from alembic.config import Config

    from cocina_control.db import build_engine

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    engine = build_engine(postgres_url)

    def activos(conn, grupo):
        return {
            r.name: r.price
            for r in conn.execute(
                sa.text(
                    "SELECT oi.name, oi.price FROM option_items oi "
                    "JOIN option_groups og ON og.id = oi.group_id "
                    "WHERE og.name = :g AND oi.is_active"
                ),
                {"g": grupo},
            ).all()
        }

    def grupo(conn, nombre):
        return conn.execute(
            sa.text(
                "SELECT selection, min_choices, max_choices FROM option_groups WHERE name = :g"
            ),
            {"g": nombre},
        ).one()

    try:
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            for g in ("Toppings (hasta 5)", "Toppings (hasta 6)"):
                t = activos(conn, g)
                assert "Pickles" not in t and "Cebolla roja" not in t
                assert {"Lechuga", "Camote", "Huevo", "Piña dulce"} <= set(t)
                assert t["Champiñones salteados"] == Decimal("1.00")
                assert t["Tomate"] == Decimal("0.00")
            base = activos(conn, "Base")
            assert "Lechuga orgánica" not in base
            assert {"Camote", "Quinua", "Lentejas", "Frejol negro"} <= set(base)
            assert tuple(grupo(conn, "Base")) == ("multiple", 1, 2)

        command.downgrade(cfg, "0031_tilapia_extra_2_50")
        with engine.connect() as conn:
            t = activos(conn, "Toppings (hasta 5)")
            assert {"Pickles", "Cebolla roja"} <= set(t)
            assert "Huevo" not in t
            assert t["Champiñones salteados"] == Decimal("0.00")
            assert "Lechuga orgánica" in activos(conn, "Base")
            assert tuple(grupo(conn, "Base")) == ("single", 1, 1)
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
