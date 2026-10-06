"""Fail-fast API/worker supervision for a sleeping, synthetic-only web service."""

import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from urllib.parse import urlsplit


def demo_environment(source: Mapping[str, str]) -> dict[str, str]:
    env = dict(source)
    if env.get("PUBLIC_DEMO_MODE", "").casefold() != "true":
        raise ValueError("Hosted demo runtime requires PUBLIC_DEMO_MODE=true")
    if env.get("OLLAMA_MODEL", "").strip() or env.get("EMBED_PROVIDER", "hash") != "hash":
        raise ValueError("Hosted free demo uses deterministic rules and hash retrieval")
    credentials = (
        "GITHUB_TOKEN",
        "MTT_GITHUB_TOKEN",
        "MCP_API_TOKEN",
        "PROVIDER_ENCRYPTION_KEY",
        "JIRA_CLIENT_ID",
        "JIRA_CLIENT_SECRET",
        "SLACK_CLIENT_ID",
        "SLACK_CLIENT_SECRET",
        "SLACK_SIGNING_SECRET",
        "LINKEDIN_CLIENT_ID",
        "LINKEDIN_CLIENT_SECRET",
    )
    if any(env.get(key, "").strip() for key in credentials):
        raise ValueError("Provider credentials must not be configured in the hosted synthetic demo")
    origin = urlsplit(env.get("APP_ORIGIN", ""))
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username is not None
        or origin.password is not None
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
    ):
        raise ValueError("APP_ORIGIN must be the exact HTTPS application origin")
    database = env.get("DATABASE_URL", "")
    if database.startswith("postgres://"):
        database = "postgresql+psycopg://" + database.removeprefix("postgres://")
    elif database.startswith("postgresql://"):
        database = "postgresql+psycopg://" + database.removeprefix("postgresql://")
    if not database.startswith("postgresql+psycopg://"):
        raise ValueError("Hosted demo requires PostgreSQL")
    env["DATABASE_URL"] = database
    port = env.get("PORT", "10000")
    if not port.isdigit() or not 1024 <= int(port) <= 65535:
        raise ValueError("PORT must be an unprivileged TCP port")
    env.update(APP_ENVIRONMENT="production", COOKIE_SECURE="true", PORT=port)
    return env


def stop_children(children: list[subprocess.Popen], timeout: float = 10) -> None:
    for child in children:
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + timeout
    for child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def supervise(commands: list[list[str]], env: Mapping[str, str]) -> int:
    children: list[subprocess.Popen] = []
    stopping = False

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {value: signal.signal(value, request_stop) for value in (signal.SIGTERM, signal.SIGINT)}
    try:
        for command in commands:
            if stopping:
                return 0
            children.append(subprocess.Popen(command, env=dict(env)))
        while not stopping:
            for child in children:
                code = child.poll()
                if code is not None:
                    # Even an unexpected clean exit means the whole runtime is unhealthy.
                    return code if code > 0 else 1
            time.sleep(0.2)
        return 0
    finally:
        stop_children(children)
        for value, handler in previous.items():
            signal.signal(value, handler)


def main() -> int:
    try:
        env = demo_environment(os.environ)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    # The existing migration entry point serializes upgrades with an advisory lock.
    migration = subprocess.run([sys.executable, "-m", "scripts.migrate"], env=env, check=False)
    if migration.returncode:
        return migration.returncode
    return supervise(
        [
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.hosted:create_app",
                "--factory",
                "--host",
                "0.0.0.0",
                "--port",
                env["PORT"],
                "--no-access-log",
                "--no-proxy-headers",
            ],
            [sys.executable, "-m", "app.worker"],
        ],
        env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
