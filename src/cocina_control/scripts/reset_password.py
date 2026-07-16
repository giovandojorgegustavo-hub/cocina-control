"""CLI script to reset a user's password by email.

Usage:
    uv run python -m cocina_control.scripts.reset_password \\
        --email "usuario@ejemplo.com"

The script prompts for the new password via stdin (hidden input).
It fails explicitly if COCINA_DATABASE_URL or COCINA_JWT_SECRET are not set.
"""

import argparse
import getpass
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset the password for an existing user."
    )
    parser.add_argument("--email", required=True, help="Email address of the user")
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
    from sqlalchemy.exc import OperationalError

    from cocina_control.db import build_engine, build_session_factory
    from cocina_control.models.user import User
    from cocina_control.security.passwords import hash_password

    settings = get_settings()
    engine = build_engine(settings.database_url)
    SessionLocal = build_session_factory(engine)

    email = args.email.strip().lower()

    try:
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                print(
                    f"ERROR: no user found with email '{email}'.",
                    file=sys.stderr,
                )
                sys.exit(1)

            new_password = getpass.getpass(f"New password for {email}: ")
            if not new_password:
                print("ERROR: password cannot be empty.", file=sys.stderr)
                sys.exit(1)

            if len(new_password) < 8:
                print("ERROR: password must be at least 8 characters.", file=sys.stderr)
                sys.exit(1)

            password_confirm = getpass.getpass("Confirm password: ")
            if new_password != password_confirm:
                print("ERROR: passwords do not match.", file=sys.stderr)
                sys.exit(1)

            try:
                user.password_hash = hash_password(new_password)
            except ValueError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)
            session.commit()

            print(f"Password updated for {email} (role: {user.role})")

    except OperationalError:
        print(
            "ERROR: could not connect to the database. "
            "Check that COCINA_DATABASE_URL is correct and the server is reachable.",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
