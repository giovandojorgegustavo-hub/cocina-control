"""CLI script to load sale prices onto the Bonabowl catalogue.

Usage:
    uv run python -m cocina_control.scripts.seed_sale_prices \\
        --owner-email "dueno@ejemplo.com" --dry-run
    uv run python -m cocina_control.scripts.seed_sale_prices \\
        --owner-email "dueno@ejemplo.com"

Why this exists: la migracion 0019 agrego products.sale_price y lo dejo en NULL
para los 20 productos de venta que ya existian. GET /catalog/menu esconde a
proposito los productos sin precio, asi que hasta que esto corra la carta que ve
el asistente esta VACIA.

FUENTE DE LOS PRECIOS: menu publico de Rappi
(rappi.com.pe/restaurantes/86834-bonabowl), leido del #__NEXT_DATA__ y
verificado en vivo el 2026-08-25 contra /var/www/landing/carta.json. Coinciden.

OJO — se usa `realPrice`, NUNCA `price`. `price` trae el descuento vigente de la
app: al 2026-08-25 los tres combos estaban a -37% (Combo Office aparecia en
33.75 cuando su precio real es 54). Publicar el precio con descuento de Rappi
como precio propio regala 37% sin que nadie lo note.

OJO 2 — estos precios INCLUYEN el margen de Rappi. Si por WhatsApp se cobra
distinto hay que corregirlos, y antes hay que revisar si el contrato con
Rappi/PedidosYa tiene clausula de paridad de precios. Es una decision del dueno,
no de este script.

What it does NOT do, on purpose: nunca pisa un precio ya cargado. Si el producto
ya tiene sale_price y no coincide con esta lista, lo reporta y sigue. El dueno
pudo haberlo corregido a mano ayer, y este script no tiene forma de saberlo.

Exit codes: 0 all clean, 1 error, 2 loaded but there are conflicts to review.
"""

import argparse
import getpass
import sys
import unicodedata
from decimal import Decimal

# Clave: el nombre CANONICO en cocina_control (products.name, en mayusculas).
# Valor: (precio, nombre en Rappi) — el segundo solo para rastrear de donde sale.
#
# Los nombres NO coinciden entre sistemas y esa desalineacion es real, no un
# typo: cocina_control dice "BBQ PROTEIN BOWL" y "BOWL CRISPY" donde Rappi dice
# "BBQ Protein Salad" y "Crispy Salad". Se mapea explicitamente en vez de
# adivinar por parecido, porque un match difuso que se equivoca le pone el
# precio de un plato a otro y nadie lo nota hasta que alguien cuadra caja.
SALE_PRICES: dict[str, tuple[str, str]] = {
    # Platos
    "FOCUS BOWL": ("33.00", "Focus Bowl"),
    "ENERGY BOWL": ("33.00", "Energy Bowl"),
    "BBQ PROTEIN BOWL": ("36.00", "BBQ Protein Salad"),
    "BOWL CRISPY": ("34.00", "Crispy Salad"),
    "WRAP FRESH": ("28.00", "Wrap fresh"),
    "WRAP MEDITERRANEO VERDE": ("28.00", "Wrap mediterraneo verde"),
    "ARMA TU BOWL": ("24.90", "Arma tu bowl"),
    "ARMA TU SALAD": ("24.90", "Arma tu salad"),
    "ARMA TU WRAP": ("21.90", "Arma Tu Wrap"),
    # Bebidas y complementos que se venden solos
    "MARACUYÁ REFRESCANTE 12 OZ": ("8.00", "Maracuyá refrescante 12 oz."),
    # Proteina extra (grupo "Escoge tu proteina extra" del modal de Rappi)
    "FILETE DE POLLO EN SALSAS BBQ": ("8.00", "Filete de pollo en salsa BBQ ahumada"),
    # Salsas: van INCLUIDAS en el plato ("1 salsa a eleccion"), no se cobran
    # aparte. Precio 0 y no NULL porque una opcion que nombra un producto exige
    # que el producto tenga precio; NULL la haria irrepresentable.
    "SALSA DE PALTA PROTEICA": ("0.00", "incluida"),
    "SALSA RUNCH PROTEICA": ("0.00", "incluida"),
    "MAYONESA PROTEICA": ("0.00", "incluida"),
    "HONEY MUSTARD PROTEICA": ("0.00", "incluida"),
    "VINAGRETA": ("0.00", "incluida"),
}

# Productos activos de venta que NO reciben precio, y por que. Se listan para
# que el reporte diga explicitamente que quedaron fuera en vez de que
# desaparezcan en silencio de la carta.
DELIBERATELY_UNPRICED: dict[str, str] = {
    "BONA WRAP": (
        "no figura en el menú de Rappi — el dueño tiene que decir si sigue "
        "a la venta y a cuánto"
    ),
    "JAMAICA CON STEVIA 12 OZ": "en carta.json está activo=false y sin precio",
    "CUCHILLO BIO FECULA": "es un cubierto, no un producto de carta",
    "TENEDOR BIO FECULA": "es un cubierto, no un producto de carta",
}


def _normalise_key(name: str) -> str:
    """Igual que en seed_sale_products: sin tildes, sin caja, sin espacios de mas."""
    collapsed = " ".join(name.strip().split()).upper()
    decomposed = unicodedata.normalize("NFKD", collapsed)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load sale prices onto the Bonabowl catalogue."
    )
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        from cocina_control.config import get_settings

        get_settings()
    except Exception as exc:
        fields = getattr(exc, "errors", None)
        detail = (
            ", ".join(str(err.get("loc", ("?",))[0]) for err in exc.errors())
            if callable(fields)
            else "revisá las variables de entorno"
        )
        print(f"ERROR: configuration is invalid — campos: {detail}", file=sys.stderr)
        sys.exit(1)

    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError, OperationalError

    from cocina_control.db import build_engine, build_session_factory
    from cocina_control.models.product import Product
    from cocina_control.models.user import User
    from cocina_control.security.passwords import verify_password

    settings = get_settings()
    engine = build_engine(settings.database_url)
    SessionLocal = build_session_factory(engine)

    email = args.owner_email.strip().lower()
    password = getpass.getpass(f"Password de {email}: ")
    denied = "ERROR: el email o la contraseña no corresponden a un owner/admin habilitado."

    priced: list[tuple[str, str]] = []
    already: list[str] = []
    conflicts: list[tuple[str, str, str]] = []
    not_found: list[str] = []
    unpriced: list[tuple[str, str]] = []

    try:
        with SessionLocal() as session:
            owner = session.scalar(select(User).where(User.email == email))
            if (
                owner is None
                or owner.role not in ("owner", "admin")
                or not verify_password(password, owner.password_hash)
            ):
                print(denied, file=sys.stderr)
                sys.exit(1)

            active = session.scalars(
                select(Product).where(
                    Product.is_active.is_(True), Product.is_sale.is_(True)
                )
            ).all()
            by_key = {_normalise_key(p.name): p for p in active}

            for name, (price_text, source) in SALE_PRICES.items():
                product = by_key.get(_normalise_key(name))
                if product is None:
                    not_found.append(name)
                    continue

                price = Decimal(price_text)
                if product.sale_price is None:
                    product.sale_price = price
                    product.updated_by = owner.id
                    priced.append((product.name, price_text))
                elif Decimal(product.sale_price) != price:
                    conflicts.append((product.name, f"{product.sale_price}", price_text))
                else:
                    already.append(product.name)

            listed = {_normalise_key(n) for n in SALE_PRICES}
            for product in active:
                if _normalise_key(product.name) in listed:
                    continue
                if product.sale_price is not None:
                    continue
                reason = DELIBERATELY_UNPRICED.get(
                    product.name, "sin precio y sin motivo declarado — REVISAR"
                )
                unpriced.append((product.name, reason))

            if args.dry_run:
                session.rollback()
            else:
                session.commit()

    except (IntegrityError, OperationalError) as exc:
        print(f"ERROR: la base rechazó la operación — {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}Precios cargados: {len(priced)}")
    for name, price_text in priced:
        print(f"  + {name} — S/ {price_text}")
    if already:
        print(f"{prefix}Ya tenían el mismo precio: {len(already)}")
    if unpriced:
        print(f"{prefix}Quedan SIN precio (no salen en la carta del asistente): {len(unpriced)}")
        for name, reason in unpriced:
            print(f"  - {name}: {reason}")
    if not_found:
        print(f"{prefix}En la lista pero NO en el catálogo: {len(not_found)}")
        for name in not_found:
            print(f"  ? {name}")
    if conflicts:
        print(f"{prefix}CONFLICTOS para revisar ({len(conflicts)}):")
        for name, in_db, listed_price in conflicts:
            print(f"  ! {name}: en la base S/ {in_db}, en la lista S/ {listed_price}")
        print("  No se modificó ninguno. Cambiar un precio es decisión del dueño.")
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
