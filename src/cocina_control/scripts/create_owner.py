"""CLI script to create the initial owner user.

Usage:
    uv run python -m cocina_control.scripts.create_owner \\
        --name "Nombre Apellido" --email "dueno@ejemplo.com"

The script prompts for the password via stdin (hidden input).
It fails explicitly if COCINA_DATABASE_URL or COCINA_JWT_SECRET are not set.
"""

import argparse
import getpass
import sys
import uuid
from datetime import UTC, datetime


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the initial owner user in the database."
    )
    parser.add_argument("--name", required=True, help="Full display name of the owner")
    parser.add_argument("--email", required=True, help="Email address (used for login)")
    args = parser.parse_args()

    # Import here so that missing env vars surface as clear ValidationError
    # messages rather than cryptic ImportError chains.
    try:
        from cocina_control.config import get_settings

        get_settings()  # raises ValidationError if required vars are missing
    except Exception as exc:
        print(f"ERROR: configuration is invalid — {exc}", file=sys.stderr)
        sys.exit(1)

    password = getpass.getpass("Password for new owner account: ")
    if not password:
        print("ERROR: password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        print("ERROR: passwords do not match.", file=sys.stderr)
        sys.exit(1)

    from sqlalchemy import select

    from cocina_control.db import build_engine, build_session_factory
    from cocina_control.models.user import User
    from cocina_control.security.passwords import hash_password

    settings = get_settings()
    engine = build_engine(settings.database_url)
    SessionLocal = build_session_factory(engine)

    email = args.email.lower()

    with SessionLocal() as session:
        existing = session.scalar(select(User).where(User.email == email))
        if existing is not None:
            print(f"ERROR: a user with email '{email}' already exists.", file=sys.stderr)
            sys.exit(1)

        owner = User(
            id=uuid.uuid4(),
            name=args.name,
            email=email,
            password_hash=hash_password(password),
            role="owner",
            created_at=datetime.now(UTC),
        )
        session.add(owner)
        session.commit()

    print(f"Owner user created: {email}")


if __name__ == "__main__":
    main()
