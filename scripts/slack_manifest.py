"""Generate a Slack manifest using an explicitly supplied application origin."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


def manifest(origin: str, *, interactions: bool = False) -> dict:
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Supply the exact HTTP(S) application origin without paths or credentials")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Public Slack callbacks require HTTPS")
    if interactions and (parsed.scheme != "https" or parsed.hostname in {"localhost", "127.0.0.1"}):
        raise ValueError("Slack interactions require a publicly reachable HTTPS origin")
    origin = origin.rstrip("/")
    result = json.loads(
        (Path(__file__).resolve().parents[1] / "integrations" / "slack" / "manifest.json").read_text()
    )
    result["oauth_config"]["redirect_urls"] = [origin + "/api/integrations/slack/callback"]
    if interactions:
        result["features"]["slash_commands"] = [
            {
                "command": "/m2o",
                "description": "Capture meetings and update your M2O plan",
                "usage_hint": "help | link CODE | meeting | plan [YYYY-MM-DD]",
                "url": origin + "/api/integrations/slack/commands",
                "should_escape": False,
            }
        ]
        result["features"]["shortcuts"] = [
            {
                "name": "Capture a meeting in M2O",
                "type": kind,
                "callback_id": "m2o_capture_meeting" if kind == "global" else "m2o_capture_message",
                "description": "Save notes privately for participant confirmation and outcome review",
            }
            for kind in ("global", "message")
        ]
        result["settings"]["interactivity"] = {
            "is_enabled": True,
            "request_url": origin + "/api/integrations/slack/interactions",
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument(
        "--interactions",
        action="store_true",
        help="Include command and shortcut callbacks; requires an awake public HTTPS endpoint",
    )
    options = parser.parse_args()
    print(json.dumps(manifest(options.origin, interactions=options.interactions), indent=2))


if __name__ == "__main__":
    main()
