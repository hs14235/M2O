import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_project_codex_config_points_to_mcp_server_with_write_approval():
    config = tomllib.loads((PROJECT_ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
    server = config["mcp_servers"]["meeting_to_tasks"]
    # The virtualenv is a local, untracked artifact, so check the configured
    # location rather than requiring it to exist on CI or a fresh clone.
    assert (PROJECT_ROOT / server["cwd"] / "app" / "mcp_server.py").is_file()
    assert server["command"] == ".venv/Scripts/python.exe"
    assert server["args"] == ["-m", "app.mcp_server"]
    assert server["default_tools_approval_mode"] == "writes"
    assert server["tools"]["create_github_issues"]["approval_mode"] == "prompt"
