"""After manual identity verification, write an expiring link to ignored local storage."""

import argparse
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import session_scope  # noqa: E402
from app.services.lifecycle import RecoveryService  # noqa: E402


def save_private_link(directory: Path, link: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("recovery-" + uuid4().hex + ".txt")
    with path.open("x", encoding="utf-8") as output:
        output.write(link + "\n")
    if os.name != "nt":
        path.chmod(0o600)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="Existing private account; omit to enter locally")
    args = parser.parse_args()
    email = args.email or input("Verified account email: ").strip()
    if input("Have you manually verified the account holder's identity? Type VERIFIED: ") != "VERIFIED":
        raise SystemExit("No recovery link issued")
    with session_scope() as session:
        link = RecoveryService(session).issue_for_operator(email)
        path = save_private_link(Path(__file__).resolve().parents[1] / ".runtime", link)
    print("Recovery link saved to", path)
    print("Share privately with the verified account holder. No email was sent.")


if __name__ == "__main__":
    main()
