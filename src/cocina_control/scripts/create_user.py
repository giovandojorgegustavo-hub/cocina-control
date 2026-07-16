"""CLI script to create a user with an explicit role.

Usage:
    uv run python -m cocina_control.scripts.create_user \\
        --name "Nombre Apellido" \\
        --email "usuario@ejemplo.com" \\
        --role admin

The script prompts for the password via stdin (hidden input).
It fails explicitly if COCINA_DATABASE_URL or COCINA_JWT_SECRET are not set.
"""

import argparse
import getpass
import sys
import uuid


VALID_ROLES = ["owner", "admin", "cocinero"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a user with the specified role in the database."
    )
    parser.add_argument("--name", required=True, help="Full display name of the user")
    parser.add_argument("--email", required=True, help="Email address (used for login)")
    parser.add_argument(
        "--role",
        required=True,
        choices=VALID_ROLES,
        help="Role to assign: owner, admin, or cocinero",
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

    password = getpass.getpass(f"Password for new {args.role} account: ")
    if not password:
        print("ERROR: password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    if len(password) < 8:
        print("ERROR: password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)

    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        print("ERROR: passwords do not match.", file=sys.stderr)
        sys.exit(1)

    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError, OperationalError

    from cocina_control.db import build_engine, build_session_factory
    from cocina_control.models.user import User
    from cocina_control.security.passwords import hash_password

    settings = get_settings()
    engine = build_engine(settings.database_url)
    SessionLocal = build_session_factory(engine)

    email = args.email.strip().lower()

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        with SessionLocal() as session:
            existing = session.scalar(select(User).where(User.email == email))
            if existing is not None:
                print(f"ERROR: a user with email '{email}' already exists.", file=sys.stderr)
                sys.exit(1)

            user = User(
                id=uuid.uuid4(),
                name=args.name,
                email=email,
                password_hash=password_hash,
                role=args.role,
            )
            session.add(user)
            session.commit()
    except IntegrityError:
        print(
            f"ERROR: a user with email '{email}' already exists "
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

    print(f"{args.role} user created: {email}")


if __name__ == "__main__":
    main()
