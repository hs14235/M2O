"""Run browser checks only against the coordinator's disposable local runtime."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--suite", choices=("workflow", "private", "visitor", "experience"), required=True)
    parser.add_argument("--case", choices=("guided",))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    path = Path(args.fixture).resolve()
    experience_runtime = path.name.startswith("experience-v2-browser-")
    expected_prefix = "experience-v2-browser-" if experience_runtime else "lifecycle-private-browser-"
    if path.parent != (root / "backend" / ".runtime").resolve() or not path.name.startswith(expected_prefix):
        raise RuntimeError("Use the designated ignored lifecycle fixture.")
    fixture = json.loads(path.read_text(encoding="utf-8"))
    expected_url = "http://127.0.0.1:19082" if experience_runtime else "http://127.0.0.1:19080"
    if fixture.get("url") != expected_url or not re.fullmatch(r"m2o_browser_[a-f0-9]{32}", fixture.get("schema", "")):
        raise RuntimeError("Browser tests require the designated disposable local runtime.")
    environment = dict(os.environ)
    for key in ("MTT_E2E_EMAIL", "MTT_E2E_PASSWORD", "MTT_LIFECYCLE_FIXTURE"):
        environment.pop(key, None)
    environment.update(MTT_E2E_URL=fixture["url"], MTT_BROWSER_CHANNEL="msedge")
    if args.suite in ("workflow", "experience"):
        environment.update(MTT_E2E_EMAIL=fixture["email"], MTT_E2E_PASSWORD=fixture["password"])
    if args.suite == "private":
        environment.update(MTT_LIFECYCLE_FIXTURE=str(path), PLAYWRIGHT_NO_COPY_PROMPT="1")
    private = [fixture.get("email"), fixture.get("password")]
    private.extend(fixture.get("recovery", {}).get(key) for key in ("email", "password", "url"))
    private.extend(("Synthetic-invitation-pass-123!", "Synthetic-recovered-password-123!"))
    values = sorted((value for value in private if value), key=len, reverse=True)
    spec = {"workflow": "workflow.spec.ts", "private": "private-lifecycle.spec.ts", "visitor": "visitor.spec.ts", "experience": "experience-v2.spec.ts"}[args.suite]
    command = ["npm.cmd", "run", "test:e2e", "--", "e2e/" + spec]
    if args.case:
        if args.suite != "workflow":
            raise RuntimeError("This focused case belongs to the workflow suite.")
        command.extend(("--grep", "guided department flows"))
    process = subprocess.Popen(
        command,
        cwd=root / "frontend", env=environment, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        for value in values:
            line = line.replace(value, "[private value]")
        line = re.sub(r"(?i)#token=[A-Za-z0-9_-]+", "#token=[private value]", line)
        line = re.sub(r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[private identity]", line)
        sys.stdout.write(line)
        sys.stdout.flush()
    return process.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        raise SystemExit(f"Lifecycle browser launcher failed ({type(exc).__name__}); fixture values withheld.") from None
