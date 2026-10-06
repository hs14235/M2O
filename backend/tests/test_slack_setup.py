import base64
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_slack_manifest_uses_actual_origin_and_keeps_interactions_explicit():
    manifest = runpy.run_path(str(ROOT / "scripts" / "slack_manifest.py"))["manifest"]
    local = manifest("http://localhost:8080")
    assert local["oauth_config"]["redirect_urls"] == ["http://localhost:8080/api/integrations/slack/callback"]
    assert set(local["oauth_config"]["scopes"]["bot"]) == {
        "chat:write",
        "channels:read",
        "channels:history",
        "commands",
    }
    assert "slash_commands" not in local["features"]
    public = manifest("https://synthetic.example.test", interactions=True)
    assert (
        public["settings"]["interactivity"]["request_url"]
        == "https://synthetic.example.test/api/integrations/slack/interactions"
    )
    assert {shortcut["type"] for shortcut in public["features"]["shortcuts"]} == {"global", "message"}
    assert len({shortcut["callback_id"] for shortcut in public["features"]["shortcuts"]}) == 2
    assert json.loads(json.dumps(public)) == public
    for origin in [
        "https://synthetic.example.test/path",
        "https://user:password@synthetic.example.test",
        "http://synthetic.example.test",
        "https://synthetic.example.test?query=1",
    ]:
        with pytest.raises(ValueError):
            manifest(origin)
    with pytest.raises(ValueError):
        manifest("http://localhost:8080", interactions=True)


def test_configuration_preserves_existing_provider_key_and_other_settings(tmp_path):
    update = runpy.run_path(str(ROOT / "scripts" / "configure_slack.py"))["update_configuration"]
    key = base64.urlsafe_b64encode(b"a" * 32).decode()
    path = tmp_path / ".env"
    path.write_text(
        "JIRA_CLIENT_SECRET=synthetic-other\nPROVIDER_ENCRYPTION_KEY="
        + key
        + "\nPUBLIC_DEMO_MODE=true\nSLACK_INTERACTIONS_ENABLED=false\n"
    )
    update(path, "123.456", "synthetic-private", "a" * 32, "A00000001")
    result = path.read_text()
    assert "PROVIDER_ENCRYPTION_KEY=" + key in result and "JIRA_CLIENT_SECRET=synthetic-other" in result
    assert "SLACK_CLIENT_ID=123.456" in result and "SLACK_APP_ID=A00000001" in result
    assert "PUBLIC_DEMO_MODE=true" in result and "SLACK_INTERACTIONS_ENABLED=false" in result
    assert not list(tmp_path.glob(".env.slack.*"))
    before = path.read_bytes()
    with pytest.raises(ValueError):
        update(path, "123.456\nINJECTION=true", "synthetic-private", "a" * 32, "A00000001")
    assert path.read_bytes() == before


def test_configuration_does_not_replace_malformed_existing_key(tmp_path):
    update = runpy.run_path(str(ROOT / "scripts" / "configure_slack.py"))["update_configuration"]
    path = tmp_path / ".env"
    path.write_text("PROVIDER_ENCRYPTION_KEY=invalid\n")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="not replaced"):
        update(path, "123.456", "synthetic-private", "a" * 32, "A00000001")
    assert path.read_bytes() == before
