"""CLI script to load the Bonabowl sale catalogue (productos de venta).

Usage:
    uv run python -m cocina_control.scripts.seed_sale_products \\
        --owner-email "dueno@ejemplo.com" --dry-run
    uv run python -m cocina_control.scripts.seed_sale_products \\
        --owner-email "dueno@ejemplo.com" --fix-mismarked

Why this exists: the pedidos screen already asks the operator "que salio en este
pedido" and refuses to close a pedido with zero products, but the catalogue had
no sale products at all — only raw inputs wrongly flagged is_sale. The operator
saw a useless grid and fell back to "dejar solo foto". This loads the real menu.

The script is idempotent: a product whose name already exists among the active
ones is left untouched and reported as skipped. Nothing is ever deleted.

--fix-mismarked additionally clears is_sale on active products that are flagged
as sale but are raw inputs (is_purchase and not in the catalogue below). They
keep is_purchase, so the "purchase or sale" check constraint still holds.
"""

import argparse
import sys
import uuid

# The sale catalogue, transcribed from the Bonabowl - Orbea menu (Rappi, jul 2026).
# Combos are deliberately absent: a combo is a combination of these products, not
# a product of its own, and registering it would double count the consumption.
# Names are stored UPPER CASE to match the normalisation the API schema applies.
SALE_CATALOGUE: list[str] = [
    # Personaliza tu plato — los armables. Sus ingredientes todavia no se
    # capturan (ver el issue de modificadores); por ahora entran como producto.
    "ARMA TU BOWL",
    "ARMA TU WRAP",
    # Bowls armados
    "BOWL BACON FIT",
    "BBQ PROTEIN BOWL",
    "BOWL BONABOWL",
    "BOWL ANDES",
    "BOWL INFLUENCER",
    "BOWL CRISPY",
    # Wraps armados
    "WRAP MEDITERRANEO VERDE",
    "WRAP FEST",
    "WRAP MILONGA",
    "WRAP FRESH",
    # Bebidas
    "MARACUYA REFRESCANTE 12 OZ",
    "JAMAICA CON STEVIA 12 OZ",
    # Cremas / salsas que salen en el pedido
    "SALSA DE PALTA PROTEICA",
    "SALSA RUNCH PROTEICA",
    "MAYONESA PROTEICA",
    "VINAGRETA",
    "HONEY MUSTARD PROTEICA",
]

# Every product above is counted by the unit (un): un bowl, un wrap, una bebida,
# una crema. Ninguno se pesa al momento de empacar.
SALE_UNIT = "un"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load the Bonabowl sale catalogue into the products table."
    )
    parser.add_argument(
        "--owner-email",
        required=True,
        help="Email of the owner/admin that will be recorded as created_by",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing anything",
    )
    parser.add_argument(
        "--fix-mismarked",
        action="store_true",
        help="Clear is_sale on active raw inputs wrongly flagged as sale",
    )
    args = parser.parse_args()

    # Imported here so a missing env var surfaces as a clear message rather than
    # a cryptic ImportError chain — same convention as create_user.py.
    try:
        from cocina_control.config import get_settings

        get_settings()
    except Exception as exc:
        print(f"ERROR: configuration is invalid — {exc}", file=sys.stderr)
        sys.exit(1)

    from datetime import UTC, datetime

    from sqlalchemy import select
    from sqlalchemy.exc import OperationalError

    from cocina_control.db import build_engine, build_session_factory
    from cocina_control.models.product import Product
    from cocina_control.models.user import User

    settings = get_settings()
    engine = build_engine(settings.database_url)
    SessionLocal = build_session_factory(engine)

    email = args.owner_email.strip().lower()
    created: list[str] = []
    skipped: list[str] = []
    unflagged: list[str] = []

    try:
        with SessionLocal() as session:
            owner = session.scalar(select(User).where(User.email == email))
            if owner is None:
                print(f"ERROR: no user with email '{email}'.", file=sys.stderr)
                sys.exit(1)
            if owner.role not in ("owner", "admin"):
                print(
                    f"ERROR: '{email}' has role '{owner.role}' — "
                    "only owner or admin can create products.",
                    file=sys.stderr,
                )
                sys.exit(1)

            active = session.scalars(
                select(Product).where(Product.is_active.is_(True))
            ).all()
            by_name = {p.name: p for p in active}

            for name in SALE_CATALOGUE:
                existing = by_name.get(name)
                if existing is not None:
                    skipped.append(name)
                    continue
                session.add(
                    Product(
                        id=uuid.uuid4(),
                        name=name,
                        unit=SALE_UNIT,
                        is_active=True,
                        is_purchase=False,
                        is_sale=True,
                        created_by=owner.id,
                    )
                )
                created.append(name)

            if args.fix_mismarked:
                catalogue = set(SALE_CATALOGUE)
                for product in active:
                    # Only raw inputs: something that is bought AND was flagged as
                    # sold but is not on the menu. Clearing is_sale keeps
                    # ck_products_purchase_or_sale satisfied because is_purchase holds.
                    if (
                        product.is_sale
                        and product.is_purchase
                        and product.name not in catalogue
                    ):
                        product.is_sale = False
                        product.updated_by = owner.id
                        product.updated_at = datetime.now(UTC)
                        unflagged.append(product.name)

            if args.dry_run:
                session.rollback()
            else:
                session.commit()
    except OperationalError:
        print(
            "ERROR: could not connect to the database. "
            "Check that COCINA_DATABASE_URL is correct and the server is reachable.",
            file=sys.stderr,
        )
        sys.exit(1)

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}creados: {len(created)}")
    for name in created:
        print(f"  + {name}")
    print(f"{prefix}ya existian: {len(skipped)}")
    for name in skipped:
        print(f"  = {name}")
    if args.fix_mismarked:
        print(f"{prefix}desmarcados como venta: {len(unflagged)}")
        for name in unflagged:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
