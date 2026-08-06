"""CLI script to create, rotate, or revoke a service principal.

Usage:
    # Create
    uv run python -m cocina_control.scripts.create_service_principal \\
        --name bonabowlinterno

    # Rotate (revoke the active one and issue a fresh token under the same name)
    uv run python -m cocina_control.scripts.create_service_principal \\
        --name bonabowlinterno --rotate

    # Revoke without issuing a replacement
    uv run python -m cocina_control.scripts.create_service_principal \\
        --name bonabowlinterno --revoke

The plaintext token is printed ONCE and never stored — only its SHA-256 digest
goes to the database.  If it is lost, rotate; it cannot be recovered.

Rotation and revocation take effect on the next request: the credential is a
database row, not a signed token waiting to expire.
"""

import argparse
import sys
import uuid


def main() -> None:
    parser = argparse.ArgumentParser(description="Create, rotate, or revoke a service principal.")
    parser.add_argument(
        "--name",
        required=True,
        help="Service principal name, e.g. bonabowlinterno",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--rotate",
        action="store_true",
        help="Revoke the active principal with this name and issue a new token",
    )
    mode.add_argument(
        "--revoke",
        action="store_true",
        help="Revoke the active principal with this name without issuing a new token",
    )
    args = parser.parse_args()

    # Import here so that missing env vars surface as clear ValidationError
    # messages rather than cryptic ImportError chains.
    try:
        from cocina_control.config import get_settings

        get_settings()  # raises ValidationError if required vars are missing
    except Exception as exc:
        print(f"ERROR: configuration is invalid — {exc}", file=sys.stderr)
        sys.exit(1)

    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError, OperationalError

    from cocina_control.db import build_engine, build_session_factory
    from cocina_control.models.service_principal import ServicePrincipal
    from cocina_control.security.service_tokens import (
        generate_service_token,
        hash_service_token,
    )

    settings = get_settings()
    engine = build_engine(settings.database_url)
    SessionLocal = build_session_factory(engine)

    name = args.name.strip()
    if not name:
        print("ERROR: name cannot be empty.", file=sys.stderr)
        sys.exit(1)

    token = generate_service_token()

    try:
        with SessionLocal() as session:
            existing = session.scalar(
                select(ServicePrincipal).where(
                    ServicePrincipal.name == name,
                    ServicePrincipal.is_active.is_(True),
                )
            )

            if args.revoke:
                if existing is None:
                    print(f"ERROR: no active service principal named '{name}'.", file=sys.stderr)
                    sys.exit(1)
                existing.is_active = False
                session.commit()
                print(f"service principal revoked: {name}")
                return

            if existing is not None:
                if not args.rotate:
                    print(
                        f"ERROR: an active service principal named '{name}' already exists. "
                        "Use --rotate to replace it, or --revoke to retire it.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                existing.is_active = False
                # Flush before inserting: the partial unique index on name
                # covers active rows only, so the old row must be deactivated
                # in the same transaction before the new one lands.
                session.flush()

            principal = ServicePrincipal(
                id=uuid.uuid4(),
                name=name,
                token_hash=hash_service_token(token),
                is_active=True,
            )
            session.add(principal)
            session.commit()
    except IntegrityError:
        print(
            f"ERROR: an active service principal named '{name}' already exists "
            "(created concurrently by another process).",
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

    verb = "rotated" if args.rotate else "created"
    print(f"service principal {verb}: {name}")
    print()
    print("Token (shown once — store it in the vault now):")
    print(f"  {token}")
    print()
    print("Use it with BOTH headers:")
    print(f"  Authorization: Bearer {token[:12]}...")
    print("  X-Act-As: <email of the cocinero the request acts for>")


if __name__ == "__main__":
    main()
