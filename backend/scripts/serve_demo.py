"""Fail-fast API/worker supervision for a sleeping, synthetic-only web service."""

import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

PRIVATE_CREDENTIAL_KEYS = (
    "GITHUB_TOKEN",
    "MTT_GITHUB_TOKEN",
    "MCP_API_TOKEN",
    "PROVIDER_ENCRYPTION_KEY",
    "JIRA_CLIENT_ID",
    "JIRA_CLIENT_SECRET",
    "SLACK_CLIENT_ID",
    "SLACK_CLIENT_SECRET",
    "SLACK_APP_ID",
    "SLACK_SIGNING_SECRET",
    "LINKEDIN_CLIENT_ID",
    "LINKEDIN_CLIENT_SECRET",
    "GOOGLE_MEET_CLIENT_ID",
    "GOOGLE_MEET_CLIENT_SECRET",
)


def demo_environment(source: Mapping[str, str]) -> dict[str, str]:
    from app.settings import Settings

    env = dict(source)
    managed = set(PRIVATE_CREDENTIAL_KEYS) | {
        "PUBLIC_DEMO_MODE",
        "OLLAMA_MODEL",
        "EMBED_PROVIDER",
        "APP_ORIGIN",
        "DATABASE_URL",
        "PORT",
        "CLIENT_IDENTITY_MODE",
        "CLIENT_IP_HEADER",
        "TRUSTED_PROXY_CIDRS",
        "WORKER_HEARTBEAT_FILE",
        "WORKER_HEARTBEAT_TIMEOUT",
        "WORKER_JOB_DEADLINE",
        "APP_ENVIRONMENT",
        "COOKIE_SECURE",
        "LINKEDIN_PUBLISHING_ENABLED",
        "SLACK_INTERACTIONS_ENABLED",
    }
    values: dict[str, str] = {}
    for key, value in source.items():
        name = key.upper()
        if name in managed:
            if name in values:
                raise ValueError("Ambiguous case-insensitive hosted configuration")
            values[name] = value
            if key != name:
                del env[key]
            env[name] = value
    if values.get("PUBLIC_DEMO_MODE", "").casefold() != "true":
        raise ValueError("Hosted demo runtime requires PUBLIC_DEMO_MODE=true")
    if values.get("OLLAMA_MODEL", "").strip() or values.get("EMBED_PROVIDER", "hash") != "hash":
        raise ValueError("Hosted free demo uses deterministic rules and hash retrieval")
    if any(values.get(key, "").strip() for key in PRIVATE_CREDENTIAL_KEYS):
        raise ValueError("Provider credentials must not be configured in the hosted synthetic demo")
    if values.get("WORKER_HEARTBEAT_FILE", "").strip():
        raise ValueError("Hosted worker health file must be supervisor-managed")
    mode = values.get("CLIENT_IDENTITY_MODE", "")
    if mode not in {"trusted_proxy", "shared"}:
        raise ValueError("Hosted demo requires an explicit trusted_proxy or shared client budget policy")
    if mode == "trusted_proxy" and not values.get("CLIENT_IP_HEADER"):
        raise ValueError("Hosted proxy identity requires an explicit header")
    try:
        Settings(
            _env_file=None,
            app_environment="test",
            client_identity_mode=mode,
            client_ip_header=values.get("CLIENT_IP_HEADER", "x-m2o-client-ip"),
            trusted_proxy_cidrs=values.get("TRUSTED_PROXY_CIDRS", ""),
            worker_heartbeat_timeout=values.get("WORKER_HEARTBEAT_TIMEOUT", "45"),
            worker_job_deadline=values.get("WORKER_JOB_DEADLINE", "600"),
        )
    except ValueError:
        raise ValueError("Invalid hosted client identity or worker health policy") from None
    # Render assigns the public URL only when the service is created (with a suffix if
    # the name is taken) and exposes it as RENDER_EXTERNAL_URL; an explicit origin wins.
    if not env.get("APP_ORIGIN", "").strip():
        env["APP_ORIGIN"] = env.get("RENDER_EXTERNAL_URL", "").strip()
    origin = urlsplit(env["APP_ORIGIN"])
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
    # Browsers send Origin without a trailing slash, and the API compares it exactly.
    env["APP_ORIGIN"] = origin.scheme + "://" + origin.netloc
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
    # Explicit empty environment values also override an accidental local .env.
    env.update({key: "" for key in PRIVATE_CREDENTIAL_KEYS})
    env.update(
        APP_ENVIRONMENT="production",
        COOKIE_SECURE="true",
        PORT=port,
        PUBLIC_DEMO_MODE="true",
        EMBED_PROVIDER="hash",
        OLLAMA_MODEL="",
        LINKEDIN_PUBLISHING_ENABLED="false",
        SLACK_INTERACTIONS_ENABLED="false",
        WORKER_HEARTBEAT_TIMEOUT=values.get("WORKER_HEARTBEAT_TIMEOUT", "45"),
        WORKER_JOB_DEADLINE=values.get("WORKER_JOB_DEADLINE", "600"),
    )
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
    from app.worker_health import worker_available

    children: list[subprocess.Popen] = []
    stopping = False
    started = time.monotonic()

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
            timeout = int(env.get("WORKER_HEARTBEAT_TIMEOUT", "45"))
            if time.monotonic() - started > timeout and not worker_available(
                env.get("WORKER_HEARTBEAT_FILE", ""), timeout, int(env.get("WORKER_JOB_DEADLINE", "600"))
            ):
                print("Hosted worker health signal is unavailable", file=sys.stderr)
                return 1
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
    with TemporaryDirectory(prefix="m2o-worker-") as directory:
        env["WORKER_HEARTBEAT_FILE"] = str(Path(directory) / "health.json")
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
