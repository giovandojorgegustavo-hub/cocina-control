"""Integration test de la migracion 0027: carta nueva.

La propiedad que se prueba: **al subir a head, los platos quedan con el precio
nuevo, la proteina deja de cobrarse aparte, "Proteína extra" y los combos salen
de la carta y los postres existen; y al bajar, todo vuelve a como estaba**.

Corre un ciclo propio de Alembic con los productos presentes, como produccion:
en la base de tests recien creada no hay platos ni usuarios, asi que la
migracion no tendria nada que tocar.
"""

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa

_POSTRES = ("Chocobrownie Frutos Rojos", "Pack 3 Chocobrownies Frutos Rojos")


@pytest.mark.anyio
async def test_la_migracion_aplica_la_carta_nueva_y_se_puede_deshacer(
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
        "Focus Bowl": (uuid.uuid4(), "33.00"),
        "Wrap Mediterráneo Verde": (uuid.uuid4(), "28.00"),
        "Arma tu Bowl": (uuid.uuid4(), "24.90"),
        "COMBO OFFICE": (uuid.uuid4(), "54.00"),
        "Mini Camote Burger": (uuid.uuid4(), "15.00"),
    }

    def precio(conn, name):
        return conn.execute(
            sa.text("SELECT sale_price FROM products WHERE name = :n"), {"n": name}
        ).scalar()

    def activo(conn, name):
        return conn.execute(
            sa.text("SELECT is_active FROM products WHERE name = :n"), {"n": name}
        ).scalar()

    def precios_proteina(conn):
        return {
            r.name: r.price
            for r in conn.execute(
                sa.text(
                    "SELECT oi.name, oi.price FROM option_items oi "
                    "JOIN option_groups og ON og.id = oi.group_id WHERE og.name = 'Proteína'"
                )
            ).all()
        }

    def max_proteinas(conn):
        return conn.execute(
            sa.text("SELECT max_choices FROM option_groups WHERE name = 'Proteína'")
        ).scalar()

    def grupo_extra_activo(conn):
        return conn.execute(
            sa.text("SELECT is_active FROM option_groups WHERE name = 'Proteína extra'")
        ).scalar()

    try:
        command.downgrade(cfg, "0026_proteina_extra_opcional")
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, name, email, password_hash, role) "
                    "VALUES (:id, 'Dueño', :email, 'x', 'owner')"
                ),
                {"id": owner_id, "email": f"owner-0027-{uuid.uuid4().hex[:6]}@test.com"},
            )
            for name, (pid, price) in platos.items():
                conn.execute(
                    sa.text(
                        "INSERT INTO products (id, name, unit, is_active, is_purchase, "
                        "is_sale, sale_price, created_by) "
                        "VALUES (:id, :name, 'un', true, false, true, :price, :owner)"
                    ),
                    {"id": pid, "name": name, "price": price, "owner": owner_id},
                )

        # Se sube hasta 0027 y no a head: 0029 vuelve a mover estos precios.
        command.upgrade(cfg, "0027_carta_precios_x2")
        with engine.connect() as conn:
            # Precios al doble del costo, en soles enteros.
            assert precio(conn, "Focus Bowl") == Decimal("24.00")
            assert precio(conn, "Wrap Mediterráneo Verde") == Decimal("21.00")
            assert precio(conn, "Arma tu Bowl") == Decimal("24.00")
            # La proteina ya va incluida: ninguna opcion suma.
            assert set(precios_proteina(conn).values()) == {Decimal("0.00")}
            # ...y por eso se elige una sola: dos gratis serian regalar costo.
            assert max_proteinas(conn) == 1
            assert grupo_extra_activo(conn) is False
            # Fuera de carta, sin borrarse.
            assert activo(conn, "COMBO OFFICE") is False
            assert activo(conn, "Mini Camote Burger") is False
            # Postres nuevos, vendibles y con cubiertos opcionales.
            assert precio(conn, _POSTRES[0]) == Decimal("15.00")
            assert precio(conn, _POSTRES[1]) == Decimal("33.00")
            grupos = conn.execute(
                sa.text(
                    "SELECT og.name FROM product_option_groups pog "
                    "JOIN option_groups og ON og.id = pog.group_id "
                    "JOIN products p ON p.id = pog.product_id WHERE p.name = :n"
                ),
                {"n": _POSTRES[0]},
            ).scalars().all()
            assert grupos == ["Cubiertos"]

        command.downgrade(cfg, "0026_proteina_extra_opcional")
        with engine.connect() as conn:
            assert precio(conn, "Focus Bowl") == Decimal("33.00")
            assert precio(conn, "Arma tu Bowl") == Decimal("24.90")
            proteinas = precios_proteina(conn)
            assert proteinas["Sin proteína"] == Decimal("0.00")
            assert proteinas["Tilapia"] == Decimal("8.00")
            assert max_proteinas(conn) == 2
            assert grupo_extra_activo(conn) is True
            assert activo(conn, "COMBO OFFICE") is True
            assert activo(conn, _POSTRES[0]) is False
    finally:
        with engine.begin() as conn:
            nombres = list(platos) + list(_POSTRES)
            conn.execute(
                sa.text(
                    "DELETE FROM product_option_groups WHERE product_id IN "
                    "(SELECT id FROM products WHERE name IN :names)"
                ).bindparams(sa.bindparam("names", expanding=True)),
                {"names": nombres},
            )
            conn.execute(
                sa.text("DELETE FROM products WHERE name IN :names").bindparams(
                    sa.bindparam("names", expanding=True)
                ),
                {"names": nombres},
            )
            conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": owner_id})
        command.upgrade(cfg, "head")
        engine.dispose()
