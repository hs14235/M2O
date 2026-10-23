"""Linux acceptance for a synthetic hosted image in owned disposable Docker resources.

No provider access, real transcripts, shared database or live service is used. With
--private the same image also serves a synthetic owner with synthetic provider settings
(HOSTED_PRIVATE_ACCOUNTS); no provider is contacted.
The exact resources created here carry a random ownership label before cleanup.
"""

import argparse
import base64
import http.cookies
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4

LABEL = "m2o.phase8.acceptance"
ORIGIN = "https://demo.example.test"


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise RuntimeError("Disposable Docker operation failed: " + args[0])
    return result.stdout.strip()


def wait_until(test, *, seconds: int = 90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if test():
            return
        time.sleep(0.5)
    raise RuntimeError("Synthetic runtime acceptance deadline exceeded")


class Browser:
    def __init__(self, base: str):
        self.base = base
        self.cookies: dict[str, str] = {}
        self.csrf = ""

    def request(self, method: str, path: str, body=None, *, headers=None):
        fields = {"Host": "demo.example.test", "Origin": ORIGIN}
        if self.cookies:
            fields["Cookie"] = "; ".join(key + "=" + value for key, value in self.cookies.items())
        if self.csrf:
            fields["X-CSRF-Token"] = self.csrf
        if headers:
            fields.update(headers)
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            fields["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=fields, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            for cookie in response.headers.get_all("Set-Cookie", []):
                parsed = http.cookies.SimpleCookie()
                parsed.load(cookie)
                self.cookies.update({key: value.value for key, value in parsed.items()})
            raw = response.read(1_000_001)
            value = (
                json.loads(raw)
                if response.headers.get("Content-Type", "").startswith("application/json")
                else raw
            )
            return response.status, value, response.headers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--private", action="store_true", help="Also check invited private accounts")
    args = parser.parse_args()
    operator_email, operator_password = "owner@example.test", secrets.token_urlsafe(18)
    private_env: list[str] = []
    if args.private:
        # Hashed by the image itself, as scripts.hosted_secrets does on the operator's machine.
        password_hash = docker(
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "--env",
            "SYNTHETIC_PASSWORD=" + operator_password,
            args.image,
            "-c",
            "import os; from app.auth import hasher; print(hasher.hash(os.environ['SYNTHETIC_PASSWORD']))",
        )
        for name, value in {
            "HOSTED_PRIVATE_ACCOUNTS": "true",
            "PROVIDER_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "JIRA_CLIENT_ID": "synthetic-jira-client",
            "JIRA_CLIENT_SECRET": "synthetic-jira-secret",
            "OWNER_EMAIL": operator_email,
            "OWNER_PASSWORD_HASH": password_hash,
        }.items():
            private_env += ["--env", name + "=" + value]
    owner = uuid4().hex
    network, db, web = ["m2o-phase8-" + owner[:12] + suffix for suffix in ("-net", "-db", "-web")]
    containers = []
    created_network = False
    try:
        docker("network", "create", "--label", LABEL + "=" + owner, network)
        created_network = True
        docker(
            "run",
            "--detach",
            "--name",
            db,
            "--network",
            network,
            "--label",
            LABEL + "=" + owner,
            "--env",
            "POSTGRES_USER=phase8_test",
            "--env",
            "POSTGRES_DB=phase8_test",
            "--env",
            "POSTGRES_PASSWORD=disposable_phase8_only",
            "postgres:17-alpine",
        )
        containers.append(db)
        wait_until(
            lambda: (
                "accepting connections"
                in docker(
                    "exec",
                    db,
                    "pg_isready",
                    "-U",
                    "phase8_test",
                    "-d",
                    "phase8_test",
                    check=False,
                )
            )
        )
        docker(
            "run",
            "--detach",
            "--name",
            web,
            "--network",
            network,
            "--label",
            LABEL + "=" + owner,
            "--publish",
            "127.0.0.1::10000",
            "--env",
            "DATABASE_URL=postgresql+psycopg://phase8_test:disposable_phase8_only@"
            + db
            + ":5432/phase8_test",
            "--env",
            "APP_ORIGIN=" + ORIGIN,
            "--env",
            "PUBLIC_DEMO_MODE=true",
            "--env",
            "CLIENT_IDENTITY_MODE=shared",
            "--env",
            "WORKER_HEARTBEAT_TIMEOUT=25",
            "--env",
            "WORKER_JOB_DEADLINE=60",
            *private_env,
            args.image,
        )
        containers.append(web)

        def published() -> str:
            # Docker assigns a new ephemeral host port each time the container starts.
            address = docker("port", web, "10000/tcp").splitlines()[0]
            if not address.startswith("127.0.0.1:"):
                raise RuntimeError("Acceptance port must bind only to loopback")
            return "http://" + address

        browser = Browser(published())

        def ready():
            try:
                return browser.request("GET", "/readyz")[0] == 200
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                return False

        wait_until(ready)
        assert docker("exec", web, "id", "-u") == "10001"
        status, value, headers = browser.request("GET", "/")
        assert (
            status == 200 and b"<html" in value and "script-src 'self'" in headers["Content-Security-Policy"]
        )
        assert browser.request("GET", "/assets/missing.js")[0] == 404
        assert browser.request("GET", "/api/not-a-route")[0] == 404
        assert browser.request("HEAD", "/scenes/engineering.mp4")[2]["Content-Type"].startswith("video/mp4")
        # The preview image feeds link cards, so it must be served as itself, not as the HTML shell.
        assert (browser.request("HEAD", "/og-image.png")[2]["Content-Type"] or "").startswith("image/png")
        assert browser.request("GET", "/", headers={"Host": "attacker.example.test"})[0] == 400
        status, person, headers = browser.request("POST", "/api/demo/start", {})
        assert status == 201
        session_cookie = next(
            cookie for cookie in headers.get_all("Set-Cookie") if cookie.startswith("mtt_session=")
        )
        assert (
            "HttpOnly" in session_cookie and "Secure" in session_cookie and "SameSite=lax" in session_cookie
        )
        browser.csrf = person["csrf_token"]
        status, spaces, _ = browser.request("GET", "/api/workspaces")
        assert status == 200
        workspace = next(space for space in spaces if space["department"] == "engineering")
        root = "/api/workspaces/" + workspace["id"]
        status, job, _ = browser.request("POST", root + "/demo/load", {"fixture_id": "engineering"})
        assert status == 202 and job["synthetic"]

        def completed(job_id):
            status, result, _ = browser.request("GET", root + "/jobs/" + job_id)
            assert status == 200 and result["state"] not in {"failed", "cancelled"}
            return result["state"] == "completed"

        wait_until(lambda: completed(job["job_id"]))
        meeting_path = root + "/meetings/" + job["meeting_id"]
        status, extraction, _ = browser.request("POST", meeting_path + "/extract", {})
        assert status == 202
        wait_until(lambda: completed(extraction["job_id"]))
        assert browser.request("GET", meeting_path)[1]["tasks"]
        other = Browser(published())
        assert other.request("POST", "/api/demo/start", {})[0] == 201
        assert other.request("GET", meeting_path)[0] == 404
        assert (
            browser.request(
                "POST",
                root + "/index",
                {
                    "meeting_id": "custom-denied",
                    "transcript": "Action: Synthetic unauthorized custom upload.",
                },
            )[0]
            == 403
        )
        print(
            "Hosted acceptance: non-root, headers/static, secure cookie attributes, real queue and visitor isolation passed",
            flush=True,
        )
        privacy = browser.request("GET", "/privacy.html")
        assert privacy[0] == 200 and privacy[2]["Content-Type"].startswith("text/html")
        if args.private:
            operator = Browser(published())
            status, signed_in, _ = operator.request(
                "POST",
                "/api/auth/login",
                {"email": operator_email, "password": operator_password},
            )
            assert status == 200
            operator.csrf = signed_in["csrf_token"]
            me = operator.request("GET", "/api/me")[1]
            assert not me["is_visitor"] and not me["capabilities"]["demo_mode"]
            owned = operator.request("GET", "/api/workspaces")[1]
            assert len(owned) == 3
            jira = operator.request("GET", "/api/workspaces/" + owned[0]["id"] + "/integrations/jira")[1]
            assert jira["configured"] and jira["can_manage"]
            # The visitor on the same site still has no provider access.
            visitor = browser.request("GET", root + "/integrations/jira")[1]
            assert not visitor["configured"] and not visitor["can_manage"]
            print(
                "Hosted acceptance: private owner signs in with providers; visitors stay without",
                flush=True,
            )

        for _ in range(10):
            assert (
                browser.request(
                    "POST",
                    "/api/auth/recovery/request",
                    {"email": "absent@example.test"},
                )[0]
                == 202
            )
        status, value, fields = browser.request(
            "POST",
            "/api/auth/recovery/request",
            {"email": "absent@example.test"},
            headers={"CF-Connecting-IP": "203.0.113.99"},
        )
        assert status == 429 and int(fields["Retry-After"]) == value["retry_after"]
        assert ready()
        # Only this labelled container's worker receives SIGSTOP.
        pause = (
            "import os,signal; from pathlib import Path; "
            "pids=[int(p.name) for p in Path('/proc').iterdir() if p.name.isdigit() "
            "and b'app.worker' in (p/'cmdline').read_bytes().split(b'\\0')]; "
            "assert len(pids)==1; os.kill(pids[0],signal.SIGSTOP)"
        )
        docker("exec", web, "python", "-c", pause)
        wait_until(
            lambda: docker("inspect", "--format", "{{.State.Running}}", web) == "false",
            seconds=45,
        )
        assert int(docker("inspect", "--format", "{{.State.ExitCode}}", web)) != 0
        print(
            "Hosted acceptance: a stopped worker caused bounded supervisor failure",
            flush=True,
        )
        docker("start", web)
        browser.base = published()
        wait_until(ready)
        assert browser.request("GET", meeting_path)[0] == 200
        docker("stop", "--time", "15", web)
        assert docker("inspect", "--format", "{{.State.ExitCode}}", web) == "0"
        docker("start", web)
        browser.base = published()
        wait_until(ready)
        assert browser.request("GET", meeting_path)[0] == 200
        print(
            "Hosted acceptance: clean SIGTERM/restart retained synthetic PostgreSQL data",
            flush=True,
        )
        return 0
    finally:
        for container in reversed(containers):
            actual = docker(
                "inspect",
                "--format",
                '{{index .Config.Labels "' + LABEL + '"}}',
                container,
                check=False,
            )
            if actual != owner:
                raise RuntimeError("Refusing cleanup without the exact acceptance ownership label")
            docker("rm", "--force", "--volumes", container)
        if created_network:
            actual = docker(
                "network",
                "inspect",
                "--format",
                '{{index .Labels "' + LABEL + '"}}',
                network,
            )
            if actual != owner:
                raise RuntimeError("Refusing network cleanup without ownership")
            docker("network", "rm", network)


if __name__ == "__main__":
    raise SystemExit(main())
