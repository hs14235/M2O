"""Create the hosted site's owner at start, from the host's private settings.

OWNER_EMAIL, OWNER_NAME (optional) and OWNER_PASSWORD_HASH come from scripts.hosted_secrets
on the operator's machine. An existing account keeps its password; change it in the app.
"""

import os
import sys

from app.database import session_scope
from scripts.bootstrap import create_owner


def main() -> int:
    email = os.environ.get("OWNER_EMAIL", "").strip()
    name = os.environ.get("OWNER_NAME", "").strip() or "Owner"
    password_hash = os.environ.get("OWNER_PASSWORD_HASH", "").strip()
    try:
        with session_scope() as session:
            _, created = create_owner(session, email, name, password_hash=password_hash)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)  # Never the configured values.
        return 2
    print("Hosted owner created." if created else "Hosted owner already exists; password unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
