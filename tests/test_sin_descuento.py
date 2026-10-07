"""Integration test de la migracion 0034: la promo de primera compra queda apagada."""

import pytest
import sqlalchemy as sa


@pytest.mark.anyio
async def test_la_promo_de_primera_compra_queda_apagada_y_se_puede_deshacer(
    postgres_url: str, db_engine
):
    from alembic import command
    from alembic.config import Config

    from cocina_control.db import build_engine

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    engine = build_engine(postgres_url)

    def activa(conn):
        return conn.execute(
            sa.text("SELECT is_active FROM promotions WHERE code = 'primera_compra'")
        ).scalar()

    try:
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert activa(conn) is False
        command.downgrade(cfg, "0033_platos_listos_24_90")
        with engine.connect() as conn:
            assert activa(conn) is True
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
