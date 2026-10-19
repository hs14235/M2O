import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.hosted import HostedApplication
from scripts.serve_demo import PRIVATE_CREDENTIAL_KEYS, demo_environment, stop_children, supervise


@pytest.fixture
def hosted(tmp_path):
    (tmp_path / "index.html").write_text("<html>M2O shell</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log('synthetic');", encoding="utf-8")

    async def api(request):
        return JSONResponse({"path": request.url.path}, headers={"Cache-Control": "no-store"})

    app = Starlette(routes=[Route("/api/status", api), Route("/readyz", api)])
    return TestClient(HostedApplication(app, tmp_path, "https://demo.example.test"))


def test_deep_links_and_api_routing_keep_security_boundaries(hosted):
    page = hosted.get("/workspaces/synthetic/meetings/demo/review", headers={"Accept": "text/html"})
    assert page.status_code == 200 and "M2O shell" in page.text
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]
    assert page.headers["Cache-Control"] == "no-cache"
    api = hosted.get("/api/status")
    assert api.json() == {"path": "/api/status"} and api.headers["Cache-Control"] == "no-store"
    assert hosted.get("/api/unknown", headers={"Accept": "text/html"}).status_code == 404
    assert hosted.get("/readyz").json()["path"] == "/readyz"


def test_missing_assets_unsafe_paths_and_non_navigation_requests_never_receive_shell(hosted):
    for path in ("/assets/missing.js", "/media/missing", "/favicon.ico", "/%2e%2e/private.txt"):
        assert hosted.get(path, headers={"Accept": "text/html"}).status_code == 404
    assert hosted.get("/missing", headers={"Accept": "application/json"}).status_code == 404
    assert hosted.post("/workspaces/synthetic").status_code == 405
    assert hosted.get("/", headers={"Host": "attacker.example.test"}).status_code == 400
    assert hosted.head("/", headers={"Accept": "text/html"}).content == b""


@pytest.mark.parametrize("accept", ["", "*/*", "application/json"])
def test_site_root_serves_the_shell_regardless_of_accept_header(hosted, accept):
    # Monitors, link previews and CLI clients fetch "/" without asking for HTML.
    page = hosted.get("/", headers={"Accept": accept})
    assert page.status_code == 200 and "M2O shell" in page.text
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]


def test_root_level_pages_are_served_as_files_with_security_headers(hosted, tmp_path):
    # The style guide is a second Vite entry (styleguide.html), not a route of the SPA shell.
    (tmp_path / "styleguide.html").write_text("<html>M2O style guide</html>", encoding="utf-8")
    page = hosted.get("/styleguide.html", headers={"Accept": "text/html"})
    assert page.status_code == 200 and "M2O style guide" in page.text
    assert "script-src 'self'; style-src 'self'" in page.headers["Content-Security-Policy"]
    assert page.headers["X-Content-Type-Options"] == "nosniff"
    assert page.headers["Cache-Control"] == "no-cache"


def test_assets_are_immutable_and_build_is_required(hosted, tmp_path):
    response = hosted.get("/assets/app-abc123.js")
    assert response.status_code == 200 and "immutable" in response.headers["Cache-Control"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    with pytest.raises(RuntimeError, match="Build the frontend"):
        HostedApplication(Starlette(), tmp_path / "missing", "https://demo.example.test")


def demo_config():
    return {
        "PUBLIC_DEMO_MODE": "true",
        "DATABASE_URL": "postgresql://synthetic:synthetic@localhost/demo",
        "APP_ORIGIN": "https://demo.example.test",
        "CLIENT_IDENTITY_MODE": "shared",
    }


def test_demo_environment_normalizes_render_database_without_mutating_input():
    source = demo_config()
    env = demo_environment(source)
    assert env["DATABASE_URL"].startswith("postgresql+psycopg://")
    assert source["DATABASE_URL"].startswith("postgresql://")
    assert env["COOKIE_SECURE"] == "true" and env["APP_ENVIRONMENT"] == "production"
    assert env["PORT"] == "10000"


def test_demo_origin_falls_back_to_render_url_and_drops_trailing_slash():
    config = {**demo_config(), "APP_ORIGIN": ""}
    rendered = demo_environment({**config, "RENDER_EXTERNAL_URL": "https://m2o-demo-x1y2.onrender.com/"})
    assert rendered["APP_ORIGIN"] == "https://m2o-demo-x1y2.onrender.com"
    explicit = demo_environment({**demo_config(), "RENDER_EXTERNAL_URL": "https://ignored.onrender.com"})
    assert explicit["APP_ORIGIN"] == "https://demo.example.test"
    with pytest.raises(ValueError, match="APP_ORIGIN"):
        demo_environment(config)


def test_production_settings_import_uses_render_url_without_app_origin(tmp_path):
    # Reproduces the first Render deploy: importing app.settings builds the global settings
    # from the raw environment, before the launcher's own fallback runs.
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"APP_ORIGIN", "DATABASE_URL", "APP_ENVIRONMENT", "COOKIE_SECURE"}
    }
    env.update(
        APP_ENVIRONMENT="production",
        COOKIE_SECURE="true",
        RENDER_EXTERNAL_URL="https://m2o-demo-x1y2.onrender.com/",
        DATABASE_URL="postgresql://synthetic:synthetic@localhost/demo",
    )
    result = subprocess.run(
        [sys.executable, "-c", "from app.settings import settings; print(settings.app_origin)"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[-500:]
    assert result.stdout.strip() == "https://m2o-demo-x1y2.onrender.com"


def test_settings_errors_never_echo_configuration_values():
    from pydantic import ValidationError

    from app.settings import Settings

    with pytest.raises(ValidationError) as failure:
        Settings(
            _env_file=None,
            app_environment="production",
            cookie_secure=False,
            database_url="postgresql://synthetic:leaked-canary@localhost/demo",
        )
    assert "leaked-canary" not in str(failure.value)


@pytest.mark.parametrize(
    "key,value",
    [
        ("PUBLIC_DEMO_MODE", "false"),
        ("OLLAMA_MODEL", "local-model"),
        ("EMBED_PROVIDER", "sentence-transformers"),
        ("GITHUB_TOKEN", "synthetic-only"),
        ("SLACK_SIGNING_SECRET", "synthetic-only"),
        ("DATABASE_URL", "sqlite:///demo.db"),
        ("PORT", "0"),
        ("PORT", "not-a-port"),
        ("APP_ORIGIN", "http://localhost:8080"),
        ("APP_ORIGIN", "https://demo.example.test/path"),
        ("APP_ORIGIN", "https://user:synthetic@demo.example.test"),
        ("DATABASE_URL", "postgresql://u:p@ep-synthetic-1-pooler.us-west-2.aws.neon.tech/demo"),
    ],
)
def test_demo_rejects_private_credentials_inference_and_invalid_configuration(key, value):
    with pytest.raises(ValueError):
        demo_environment({**demo_config(), key: value})


def test_worker_exit_causes_supervisor_failure_and_stops_remaining_children(tmp_path):
    import os

    # An actual child process verifies lifecycle behavior, not a mocked poll loop.
    pid_file = tmp_path / "pid.txt"
    sleeper = [
        sys.executable,
        "-c",
        "import os, pathlib, time; pathlib.Path(os.environ['TEST_PID_FILE']).write_text(str(os.getpid())); time.sleep(60)",
    ]
    exit_command = [sys.executable, "-c", "import time; time.sleep(0.5); raise SystemExit(7)"]
    result = supervise([sleeper, exit_command], {**os.environ, "TEST_PID_FILE": str(pid_file)})
    assert result == 7 and pid_file.is_file()


def test_child_shutdown_reaps_a_running_process():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    stop_children([child], timeout=2)
    assert child.poll() is not None


def test_root_build_context_excludes_private_runtime_and_render_deploys_only_after_checks():
    root = Path(__file__).resolve().parents[2]
    ignore = (root / ".dockerignore").read_text()
    assert "**/.env" in ignore and ".runtime" in ignore and "**/node_modules" in ignore
    blueprint = yaml.safe_load((root / "render.yaml").read_text())
    (web,) = blueprint["services"]
    # Deploy only commits whose CI passed; never on every push.
    assert web["autoDeployTrigger"] == "checksPass"
    # Free web service; the database is external (Neon), so the Blueprint creates none.
    assert web["plan"] == "free" and "databases" not in blueprint
    # Liveness only: a database health probe would keep Neon from ever scaling to zero.
    assert web["healthCheckPath"] == "/healthz"
    env = {item["key"]: item for item in web["envVars"]}
    # The connection string is entered privately in Render, never written in source.
    assert env["DATABASE_URL"] == {"key": "DATABASE_URL", "sync": False}
    assert env["CLIENT_IDENTITY_MODE"]["value"] == "shared"
    assert not set(env) & set(PRIVATE_CREDENTIAL_KEYS)
