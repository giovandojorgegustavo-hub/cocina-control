"""CLI script to load the Bonabowl delivery fee table (tarifas de reparto).

Usage:
    uv run python -m cocina_control.scripts.seed_delivery_zones \\
        --owner-email "dueno@ejemplo.com" --dry-run
    uv run python -m cocina_control.scripts.seed_delivery_zones \\
        --owner-email "dueno@ejemplo.com"

Why this exists: el asistente de WhatsApp no puede cerrar un pedido sin saber
cuanto cuesta el reparto, y delivery_zones nace vacia con la migracion 0019. Un
distrito sin fila es un distrito sin cobertura, asi que una tabla vacia significa
"no repartimos a ningun lado".

Por que un script y no una migracion de datos: una tarifa cambia. Hornear los
importes en el historial de migraciones obligaria a editar el pasado cada vez que
sube el motorizado, y dejaria el numero real escondido en un archivo que nadie
mira. Esto se puede volver a correr.

What it does NOT do, on purpose: nunca muta una zona existente. Si el distrito ya
esta con OTRA tarifa, lo reporta y sigue. Cambiar un precio es una decision del
dueno con su rastro de auditoria — no algo que un script decide en silencio
porque su lista interna dice otra cosa.

Authorisation: --owner-email names the account recorded as created_by, and the
script asks for that account's password. Verifying it is what makes created_by an
attributable fact instead of a free-form claim.

Exit codes: 0 all clean, 1 error, 2 seeded but there are conflicts to review.
"""

import argparse
import getpass
import sys
import unicodedata
import uuid
from decimal import Decimal

# Tarifas por distrito, medidas desde el local en Magdalena del Mar y
# confirmadas por el dueno el 2026-08-25.
#
# Por DISTRITO y no por kilometros, y no es una simplificacion perezosa: el
# asistente no puede medir distancia en una conversacion de WhatsApp. Lo unico
# que el cliente escribe es el nombre de un distrito. Una tarifa por sub-zona
# ("la parte este de San Miguel") seria irresoluble en el chat y terminaria en
# discusion con el cliente.
#
# Un distrito que no esta en esta lista NO tiene cobertura. Esa es toda la
# regla: la ausencia de fila es la respuesta.
#
# Los nombres llevan sus tildes; la comparacion contra la base es insensible a
# tildes y mayusculas (ver _normalise_key), asi que una fila que el dueno cargue
# a mano como "Jesus Maria" se reconoce como la misma y no se duplica.
DELIVERY_ZONES: list[tuple[str, str]] = [
    # Cerca — el local y sus vecinos inmediatos.
    ("Magdalena del Mar", "5.00"),
    ("Pueblo Libre", "5.00"),
    ("San Miguel", "5.00"),
    ("Jesús María", "5.00"),
    # Intermedio.
    ("San Isidro", "7.00"),
    ("Lince", "7.00"),
    ("Breña", "7.00"),
    ("Cercado de Lima", "7.00"),
    ("La Perla", "7.00"),
    # Lejos.
    ("Miraflores", "10.00"),
    ("Surquillo", "10.00"),
    ("San Borja", "10.00"),
    ("Bellavista", "10.00"),
    ("Barranco", "10.00"),
    ("Rímac", "10.00"),
]


def _normalise_key(name: str) -> str:
    """Collapse a district name to a comparison key: no accents, no case.

    El indice unico de la tabla es sobre lower(district) y NO ignora tildes, asi
    que para Postgres "Jesus Maria" y "Jesús María" son dos distritos distintos y
    aceptaria las dos filas. El asistente cotizaria con la que encuentre primero.
    Comparar por esta llave es lo que evita ese mellizo.
    """
    collapsed = " ".join(name.strip().split()).upper()
    decomposed = unicodedata.normalize("NFKD", collapsed)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load the Bonabowl delivery fee table into delivery_zones."
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
    # a cryptic ImportError chain — same convention as seed_sale_products.py.
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
    from cocina_control.models.delivery_zone import DeliveryZone
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

    created: list[tuple[str, str]] = []
    skipped: list[str] = []
    # (distrito, tarifa en la base, tarifa de la lista) — nunca se mutan acá.
    conflicts: list[tuple[str, str, str]] = []
    extra: list[str] = []

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

            existing_rows = session.scalars(select(DeliveryZone)).all()
            by_key: dict[str, DeliveryZone] = {}
            for zone in existing_rows:
                by_key.setdefault(_normalise_key(zone.district), zone)

            listed_keys = {_normalise_key(name) for name, _ in DELIVERY_ZONES}

            for name, fee_text in DELIVERY_ZONES:
                fee = Decimal(fee_text)
                zone = by_key.get(_normalise_key(name))
                if zone is None:
                    session.add(
                        DeliveryZone(
                            id=uuid.uuid4(),
                            district=name,
                            fee=fee,
                            is_active=True,
                            created_by=owner.id,
                        )
                    )
                    created.append((name, fee_text))
                    continue

                # Ya hay fila para este distrito. No la tocamos: cambiar una
                # tarifa es del dueño, y este script no puede saber si la de la
                # base es la vieja o la corregida a mano ayer.
                if zone.fee != fee:
                    conflicts.append((name, f"{zone.fee}", fee_text))
                elif not zone.is_active:
                    conflicts.append((name, "desactivada", fee_text))
                else:
                    skipped.append(name)

            # Distritos con fila que no están en esta lista. Puede ser una zona
            # que el dueño agregó a mano, o una que sacamos de la lista y
            # todavía está cobrando. No hay señal en los datos para
            # distinguirlas, así que se listan y no se tocan.
            for zone in existing_rows:
                if _normalise_key(zone.district) not in listed_keys:
                    extra.append(f"{zone.district} (S/ {zone.fee})")

            if args.dry_run:
                session.rollback()
            else:
                session.commit()

    except (IntegrityError, OperationalError) as exc:
        print(f"ERROR: la base rechazó la operación — {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}Zonas creadas: {len(created)}")
    for name, fee_text in created:
        print(f"  + {name} — S/ {fee_text}")
    if skipped:
        print(f"{prefix}Ya estaban con la misma tarifa: {len(skipped)}")
    if extra:
        print(f"{prefix}Zonas en la base que NO están en esta lista: {len(extra)}")
        for line in extra:
            print(f"  ? {line}")
    if conflicts:
        print(f"{prefix}CONFLICTOS para revisar ({len(conflicts)}):")
        for name, in_db, listed in conflicts:
            print(f"  ! {name}: en la base {in_db}, en la lista S/ {listed}")
        print("  No se modificó ninguna. Cambiar una tarifa es decisión del dueño.")
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
