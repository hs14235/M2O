"""Verify Phase 9 against its own loopback PostgreSQL container, then stop it.

Uses an already-installed image/runtime, synthetic data and random test credentials.
Does not read private environment files or remove any database/container/volume.
"""

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    name = "m2o-phase9-checks-" + uuid4().hex[:12]
    password = secrets.token_hex(24)
    docker_env = {**os.environ, "POSTGRES_PASSWORD": password}
    subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--pull=never",
            "--name",
            name,
            "--env",
            "POSTGRES_PASSWORD",
            "--env",
            "POSTGRES_DB=m2o_phase9_checks",
            "--publish",
            "127.0.0.1::5432",
            "postgres:17-alpine",
        ],
        env=docker_env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    print("Created isolated synthetic PostgreSQL container: " + name, flush=True)
    try:
        port = subprocess.check_output(
            [
                "docker",
                "inspect",
                "--format",
                '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}',
                name,
            ],
            text=True,
        ).strip()
        if not port.isdigit():
            raise RuntimeError("Test port allocation failed")
        deadline = time.monotonic() + 60
        while True:
            try:
                with psycopg.connect(
                    host="127.0.0.1",
                    port=int(port),
                    user="postgres",
                    password=password,
                    dbname="m2o_phase9_checks",
                    connect_timeout=2,
                ):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Isolated PostgreSQL did not become ready") from None
                time.sleep(0.5)
        env = {
            **os.environ,
            "DATABASE_URL": f"postgresql+psycopg://postgres:{password}@127.0.0.1:{port}/m2o_phase9_checks",
            "APP_ENVIRONMENT": "test",
            "PUBLIC_DEMO_MODE": "true",
            "OLLAMA_MODEL": "",
            "EMBED_PROVIDER": "hash",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        for key in (
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
            "GOOGLE_MEET_CLIENT_ID",
            "GOOGLE_MEET_CLIENT_SECRET",
        ):
            env[key] = ""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--postgres", "--tb=short", *sys.argv[1:]],
            cwd=ROOT,
            env=env,
        )
        folder = ROOT / ".runtime"
        folder.mkdir(exist_ok=True)
        (folder / "phase9-checks.json").write_text(
            json.dumps({"container": name, "test_exit_code": result.returncode}), encoding="utf-8"
        )
        return result.returncode
    finally:
        subprocess.run(["docker", "stop", name], check=True, stdout=subprocess.DEVNULL)
        print("Stopped owned test container; retained for inspection: " + name, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
