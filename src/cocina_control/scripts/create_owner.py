"""Backward-compatible wrapper around create_user with --role owner injected.

Usage (unchanged from v0.1):
    uv run python -m cocina_control.scripts.create_owner \\
        --name "Nombre Apellido" --email "dueno@ejemplo.com"

Passing --role explicitly to this script is rejected by the guard below.
Argparse would otherwise silently take the last --role value (letting someone
create an admin via `create_owner --role admin`).  Use create_user directly
if you need to specify a role.
"""

import sys

from cocina_control.scripts.create_user import main as _create_user_main


def main() -> None:
    if "--role" in sys.argv[1:]:
        print(
            "ERROR: --role is not supported by create_owner. "
            "Use create_user for other roles.",
            file=sys.stderr,
        )
        sys.exit(1)
    # Insert --role owner before any user-supplied arguments so that
    # create_user's argparse receives it as its role value.
    sys.argv.insert(1, "--role")
    sys.argv.insert(2, "owner")
    _create_user_main()


if __name__ == "__main__":
    main()
