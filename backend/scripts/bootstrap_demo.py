"""Create a synthetic local E2E account; never run in a shared environment."""

import json
import secrets
from pathlib import Path

from app.database import session_scope
from app.settings import settings
from scripts.bootstrap import create_owner


def main():
    if settings.app_environment != "development" or not settings.public_demo_mode:
        raise ValueError("Synthetic bootstrap requires local development in demo mode")
    target = Path(__file__).resolve().parents[2] / ".runtime" / "demo-account.json"
    if target.exists():
        print("Synthetic account file already exists; credentials unchanged.")
        return
    account = {
        "email": "demo-owner@example.test",
        "name": "Synthetic Demo Owner",
        "password": secrets.token_urlsafe(24),
    }
    with session_scope() as session:
        _, created = create_owner(session, **account)
        if not created:
            raise ValueError(
                "Synthetic account already exists without its credential file; use an explicitly managed account"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(account), encoding="utf-8")
    print("Synthetic account created. Credentials are stored only in ignored .runtime/demo-account.json.")


if __name__ == "__main__":
    main()
