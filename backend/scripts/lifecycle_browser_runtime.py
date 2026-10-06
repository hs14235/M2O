"""Run real browser acceptance against a disposable PostgreSQL schema.

The only removed schema is the UUID-named schema created by this invocation.
Synthetic owner credentials are saved in a new ignored file, never printed.
"""

import argparse
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from ipaddress import IPv4Address
from pathlib import Path
from uuid import uuid4

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.auth import hasher
from app.models import Membership, User, Workspace
from app.services.lifecycle import RecoveryService
from app.settings import settings
from scripts.bootstrap import create_owner
from scripts.serve_demo import stop_children

ROOT = Path(__file__).resolve().parents[2]


def validate_binding(host: str, phone_demo: bool) -> str:
    address = IPv4Address(host)
    if phone_demo:
        if not address.is_private or address.is_loopback or address.is_unspecified or address.is_link_local:
            raise ValueError("Phone demos require an assigned private LAN IPv4 address")
    elif str(address) != "127.0.0.1":
        raise ValueError("Private acceptance fixtures must stay on loopback")
    return str(address)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=19080)
    parser.add_argument("--seconds", type=int, default=1200)
    parser.add_argument("--fixture-file", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--phone-demo", action="store_true", help="LAN-bound synthetic-only demo without private accounts"
    )
    args = parser.parse_args()
    try:
        host = validate_binding(args.host, args.phone_demo)
    except ValueError as exc:
        parser.error(str(exc))
    target = args.fixture_file.resolve()
    stop_file = target.with_suffix(".stop")
    if (
        not target.is_relative_to(ROOT / "backend" / ".runtime")
        or target.suffix != ".json"
        or target.exists()
        or stop_file.exists()
    ):
        parser.error("Choose a new fixture file under backend/.runtime")
    if not 1024 <= args.port <= 65535 or not 10 <= args.seconds <= 3600:
        parser.error("Use an unprivileged port and a lifetime of 10 to 3600 seconds")
    static_root = ROOT / "frontend" / "dist"
    if not (static_root / "index.html").is_file():
        parser.error("Build the current frontend first")
    url = make_url(settings.database_url.get_secret_value())
    if url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Configure loopback PostgreSQL; this helper never targets a remote database")
    with socket.socket() as probe:
        probe.bind((host, args.port))
    schema = "m2o_browser_" + uuid4().hex
    origin = f"http://{host}:{args.port}"
    base = create_engine(url, hide_parameters=True)
    children = []
    created = False
    fixture_written = False
    stopping = False
    log = None
    previous = {}

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    try:
        for value in (signal.SIGINT, signal.SIGTERM):
            previous[value] = signal.signal(value, stop)
        with base.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        isolated_url = url.update_query_dict({"options": "-csearch_path=" + schema})
        isolated = create_engine(isolated_url, hide_parameters=True)
        try:
            with isolated.begin() as connection:
                config = Config(str(ROOT / "backend" / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            fixture: dict[str, object] = {"url": origin, "schema": schema, "stop_file": str(stop_file)}
            if args.phone_demo:
                fixture["mode"] = "synthetic_phone_demo"
            else:
                password = secrets.token_urlsafe(24)
                with Session(isolated, expire_on_commit=False) as session:
                    user, _ = create_owner(
                        session, "owner@browser.example.test", "Synthetic Browser Owner", password
                    )
                    session.flush()
                    spaces = [
                        {"id": row.id, "name": row.name, "department": row.department}
                        for row in session.scalars(select(Workspace))
                    ]
                    recovery_password = secrets.token_urlsafe(24)
                    recipient = User(
                        email="recovery@browser.example.test",
                        name="Synthetic Recovery Recipient",
                        password_hash=hasher.hash(recovery_password),
                    )
                    session.add(recipient)
                    session.flush()
                    engineering = next(row for row in spaces if row["department"] == "engineering")
                    session.add(
                        Membership(workspace_id=engineering["id"], user_id=recipient.id, role="editor")
                    )
                    session.flush()
                    recovery_link = RecoveryService(session).issue_for_operator(recipient.email)
                    recovery = {
                        "email": recipient.email,
                        "password": recovery_password,
                        "url": origin + "/recover#" + recovery_link.split("#", 1)[1],
                    }
                    session.commit()
                fixture.update(email=user.email, password=password, workspaces=spaces, recovery=recovery)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as output:
                json.dump(fixture, output)
            fixture_written = True
        finally:
            isolated.dispose()
        env = dict(os.environ)
        # Empty environment entries override private values loaded from backend/.env.
        for field in type(settings).model_fields:
            if any(
                word in field for word in ("secret", "token", "client_id", "encryption_key", "allowed_repos")
            ):
                env[field.upper()] = ""
        env.update(
            DATABASE_URL=isolated_url.render_as_string(hide_password=False),
            APP_ORIGIN=origin,
            APP_ENVIRONMENT="test",
            COOKIE_SECURE="false",
            PUBLIC_DEMO_MODE="true" if args.phone_demo else "false",
            VISITOR_DEMO_ENABLED="true",
            EMBED_PROVIDER="hash",
            OLLAMA_MODEL="",
            M2O_STATIC_ROOT=str(static_root),
        )
        if args.phone_demo:
            env.update(LINKEDIN_PUBLISHING_ENABLED="false", SLACK_INTERACTIONS_ENABLED="false")
        log = target.with_suffix(".log").open("x", encoding="utf-8")
        for command_args in (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.hosted:create_app",
                "--factory",
                "--host",
                host,
                "--port",
                str(args.port),
                "--no-access-log",
            ],
            [sys.executable, "-m", "app.worker"],
        ):
            children.append(
                subprocess.Popen(command_args, cwd=ROOT / "backend", env=env, stdout=log, stderr=log)
            )
        deadline = time.monotonic() + args.seconds
        with httpx.Client(trust_env=False, timeout=2) as client:
            for _ in range(50):
                if stopping or any(child.poll() is not None for child in children):
                    raise RuntimeError("Browser runtime ended before readiness; inspect the private log")
                try:
                    if client.get(origin + "/readyz").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Browser runtime did not become ready; inspect the private log")
        print("Isolated lifecycle browser runtime ready at " + origin, flush=True)
        print(
            "Synthetic-only phone preview; no private accounts or provider credentials."
            if args.phone_demo
            else "Synthetic credentials are in the requested ignored fixture file. No shared schema changed.",
            flush=True,
        )
        while not stopping and not stop_file.exists() and time.monotonic() < deadline:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("Browser runtime child stopped; inspect the private log")
            time.sleep(0.2)
        return 0
    finally:
        stop_children(children)
        if log:
            log.close()
        if created:
            with base.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()
        # Do not leave a reusable credential artifact after the isolated database ends.
        if fixture_written and target.is_file():
            target.unlink()
        if fixture_written and stop_file.is_file():
            stop_file.unlink()
        for value, handler in previous.items():
            signal.signal(value, handler)


if __name__ == "__main__":
    raise SystemExit(main())
