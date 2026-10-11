"""Use the interpreter containing this release's installed dependencies."""

import subprocess
import sys


def main() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pyright", "app", "--pythonpath", sys.executable], check=False
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
