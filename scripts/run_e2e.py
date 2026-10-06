"""Run browser tests using the ignored synthetic account without printing credentials."""

import json
import os
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    account = json.loads((root / ".runtime" / "demo-account.json").read_text())
    environment = dict(os.environ, MTT_E2E_EMAIL=account["email"], MTT_E2E_PASSWORD=account["password"])
    command = "npm.cmd" if os.name == "nt" else "npm"
    result = subprocess.run([command, "run", "test:e2e"], cwd=root / "frontend", env=environment, check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
