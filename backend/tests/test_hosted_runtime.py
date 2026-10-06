import subprocess
import sys
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.hosted import HostedApplication
from scripts.serve_demo import demo_environment, stop_children, supervise


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
    }


def test_demo_environment_normalizes_render_database_without_mutating_input():
    source = demo_config()
    env = demo_environment(source)
    assert env["DATABASE_URL"].startswith("postgresql+psycopg://")
    assert source["DATABASE_URL"].startswith("postgresql://")
    assert env["COOKIE_SECURE"] == "true" and env["APP_ENVIRONMENT"] == "production"
    assert env["PORT"] == "10000"


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


def test_root_build_context_excludes_private_runtime_and_render_is_manual():
    root = Path(__file__).resolve().parents[2]
    ignore = (root / ".dockerignore").read_text()
    assert "**/.env" in ignore and ".runtime" in ignore and "**/node_modules" in ignore
    blueprint = (root / "render.yaml").read_text()
    assert 'autoDeployTrigger: "off"' in blueprint
    assert "plan: free" in blueprint and "sync: false" in blueprint
