"""Create a local owner. Passwords are read without echo or from a process variable."""

import argparse
import getpass
import os
import secrets
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.auth import digest, hasher
from app.database import session_scope
from app.models import ApiToken, Membership, User, Workspace, now


def create_owner(session, email, name, password=None, *, password_hash=None):
    """An owner with one workspace per department; an existing account is left unchanged.

    The hosted site passes a hash made on the operator's machine, so the password itself
    never reaches the host (see scripts/hosted_secrets.py)."""
    user = session.scalar(select(User).where(User.email == email.casefold()))
    if user:
        return user, False
    if password_hash is None:
        if password is None or len(password) < 12 or len(password) > 256:
            raise ValueError("Use an email address and a password of 12 to 256 characters")
        password_hash = hasher.hash(password)
    if "@" not in email or not password_hash.startswith("$argon2id$"):
        raise ValueError("Use an email address and a password of 12 to 256 characters")
    user = User(email=email.casefold(), name=name, password_hash=password_hash)
    session.add(user)
    session.flush()
    for department in ("engineering", "hr", "finance"):
        workspace = Workspace(
            name={
                "engineering": "Engineering delivery",
                "hr": "People operations",
                "finance": "Finance controls",
            }[department],
            department=department,
        )
        session.add(workspace)
        session.flush()
        session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    return user, True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--mcp-token-file", type=Path)
    args = parser.parse_args()
    password = os.getenv("MTT_BOOTSTRAP_PASSWORD") or getpass.getpass("New local owner password: ")
    with session_scope() as session:
        user, created = create_owner(session, args.email, args.name, password)
        if args.mcp_token_file:
            target = args.mcp_token_file.resolve()
            backend = Path(__file__).resolve().parents[1]
            if not target.is_relative_to(backend / ".runtime") or target.exists():
                raise ValueError("Token output must be a new file under backend/.runtime")
            workspace = session.scalar(
                select(Workspace)
                .join(Membership)
                .where(Membership.user_id == user.id, Workspace.department == "engineering")
            )
            token = secrets.token_urlsafe(40)
            session.add(
                ApiToken(
                    token_hash=digest(token),
                    user_id=user.id,
                    workspace_id=workspace.id,
                    expires_at=now() + timedelta(days=30),
                )
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("MCP_API_TOKEN=" + token + "\n", encoding="utf-8")
    print("Local owner created." if created else "Owner already exists; password unchanged.")
    if args.mcp_token_file:
        print("Scoped token saved to the requested ignored file. Keep it private.")


if __name__ == "__main__":
    main()
