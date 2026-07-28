"""CLI script to load the Bonabowl sale catalogue (productos de venta).

Usage:
    uv run python -m cocina_control.scripts.seed_sale_products \\
        --owner-email "dueno@ejemplo.com" --dry-run
    uv run python -m cocina_control.scripts.seed_sale_products \\
        --owner-email "dueno@ejemplo.com"

Why this exists: the pedidos screen already asks the operator "que salio en este
pedido" and refuses to close a pedido with zero products, but the catalogue had
no sale products at all — only raw inputs wrongly flagged is_sale. The operator
saw a useless grid and fell back to "dejar solo foto". This loads the real menu.

What it does NOT do, on purpose: it never mutates an existing product. It only
inserts what is missing. Anything ambiguous is REPORTED for the owner to resolve
through PATCH /products, which is owner-only, one row at a time, and leaves the
audit trail this script cannot. See docs/backend/decisiones-catalogo-venta.md.

Authorisation: --owner-email names the account recorded as created_by, and the
script asks for that account's password. Verifying it is what makes created_by
an attributable fact instead of a free-form claim — anyone with a shell on the
server can already write to the database, so the check is about the honesty of
the audit trail, not about keeping an attacker out.

Exit codes: 0 all clean, 1 error, 2 seeded but there are conflicts to review.
"""

import argparse
import getpass
import sys
import unicodedata
import uuid

# The sale catalogue, transcribed from the Bonabowl - Orbea menu on Rappi
# (rappi.com.pe/restaurantes/86834-bonabowl, consultado el 28 jul 2026).
# Sections: "Personaliza Tu Plato", "Bowl", "Wraps", "Bebidas" + the sauces
# offered in the "Elige la salsa de tu bowl" step.
#
# Combos are deliberately absent: a combo is a combination of these products,
# not a product of its own, and registering it would double count the
# consumption that the leak detector exists to measure.
#
# Names carry their proper accents; comparison against the database is
# accent- and case-insensitive (see _normalise_key) so that a row the owner
# typed by hand is recognised as the same product instead of duplicated.
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
    "MARACUYÁ REFRESCANTE 12 OZ",
    "JAMAICA CON STEVIA 12 OZ",
    # Cremas / salsas que salen en el pedido. "RUNCH" es la grafia que usa el
    # menu publicado, no un typo de "ranch" — se transcribe tal cual.
    "SALSA DE PALTA PROTEICA",
    "SALSA RUNCH PROTEICA",
    "MAYONESA PROTEICA",
    "VINAGRETA",
    "HONEY MUSTARD PROTEICA",
]

# Every product above is counted by the unit (un): un bowl, un wrap, una bebida,
# una crema. Ninguno se pesa al momento de empacar.
SALE_UNIT = "un"


def _normalise_key(name: str) -> str:
    """Collapse a product name to a comparison key: no accents, no case.

    The API normalises names with strip + collapse + upper but leaves accents
    alone, and the unique partial index is over the raw text. So MARACUYÁ and
    MARACUYA are two different rows as far as Postgres is concerned, and both
    would show up in the operator's grid as the same drink. Matching on this
    key is what stops the script from creating that twin.
    """
    collapsed = " ".join(name.strip().split()).upper()
    decomposed = unicodedata.normalize("NFKD", collapsed)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load the Bonabowl sale catalogue into the products table."
    )
    parser.add_argument(
        "--owner-email",
        required=True,
        help="Email of the owner/admin recorded as created_by (password required)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing anything",
    )
    args = parser.parse_args()

    # Imported here so a missing env var surfaces as a clear message rather than
    # a cryptic ImportError chain — same convention as create_user.py.
    try:
        from cocina_control.config import get_settings

        get_settings()
    except Exception as exc:
        # Never print the raw exception: pydantic includes input_value in its
        # ValidationError text, which would dump COCINA_JWT_SECRET to stderr.
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

    # One message for "no existe", "rol equivocado" and "password mala": telling
    # them apart would turn this into a user/role enumeration oracle.
    denied = "ERROR: el email o la contraseña no corresponden a un owner/admin habilitado."

    created: list[str] = []
    skipped: list[str] = []
    # (nombre del catalogo, nombre en la base, motivo) — nunca se mutan acá.
    conflicts: list[tuple[str, str, str]] = []
    review: list[str] = []

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
                select(Product).where(Product.is_active.is_(True))
            ).all()
            by_key: dict[str, Product] = {}
            for product in active:
                # First row wins; a pre-existing twin is itself reported below.
                by_key.setdefault(_normalise_key(product.name), product)

            catalogue_keys = {_normalise_key(name) for name in SALE_CATALOGUE}

            for name in SALE_CATALOGUE:
                existing = by_key.get(_normalise_key(name))
                if existing is None:
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
                    continue

                # Ya hay una fila que representa este producto. No la tocamos:
                # promoverla a venta o renombrarla es una decisión del dueño,
                # y la ruta con auditoría para eso es PATCH /products.
                if existing.name != name:
                    conflicts.append(
                        (name, existing.name, "ya existe con otra grafía")
                    )
                elif not existing.is_sale:
                    conflicts.append(
                        (name, existing.name, "existe pero NO está marcado como venta")
                    )
                else:
                    skipped.append(name)

            # Productos marcados como venta que no están en el menú. Puede ser
            # reventa legítima (una gaseosa que se compra hecha, ver migración
            # 0015), un insumo mal flageado, o un typo cargado desde el alta
            # inline del pedido. NO hay señal en los datos para distinguirlos,
            # así que se listan para que los mire el dueño — no se tocan.
            for product in active:
                if product.is_sale and _normalise_key(product.name) not in catalogue_keys:
                    review.append(product.name)

            if args.dry_run:
                # flush ejerce el índice único, el enum de unit y los checks;
                # sin esto el dry-run sería un ensayo solo en memoria.
                session.flush()
                session.rollback()
            else:
                session.commit()
    except IntegrityError:
        print(
            "ERROR: otro proceso creó un producto con el mismo nombre mientras "
            "corría el script. No se escribió nada — volvé a correrlo.",
            file=sys.stderr,
        )
        sys.exit(1)
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
    print(f"{prefix}ya estaban: {len(skipped)}")
    for name in skipped:
        print(f"  = {name}")

    if conflicts:
        print(f"\n{prefix}CONFLICTOS — no se tocaron, resolvelos vos: {len(conflicts)}")
        for name, existing_name, reason in conflicts:
            print(f"  ! {name}: {reason} (en la base: '{existing_name}')")
    if review:
        print(f"\n{prefix}MARCADOS COMO VENTA Y FUERA DEL MENÚ — revisalos: {len(review)}")
        for name in review:
            print(f"  ? {name}")
        print(
            "    Si alguno es un insumo mal marcado, sacale is_sale con "
            "PATCH /products/{id} (owner). Si es reventa, dejalo como está."
        )

    if conflicts:
        sys.exit(2)


if __name__ == "__main__":
    main()
