"""Back up the isolated local Compose database; optionally verify a separate restore."""

import argparse
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def docker(args, **options):
    return subprocess.run(["docker", "compose", "exec", "-T", "db", *args], cwd=ROOT, check=True, **options)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-restore", action="store_true")
    args = parser.parse_args()
    folder = ROOT / ".runtime" / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8] + ".dump")
    with target.open("xb") as output:
        docker(
            ["sh", "-c", 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],
            stdout=output,
            stderr=subprocess.PIPE,
        )
    print("Local backup saved under .runtime/backups.")
    if args.verify_restore:
        destination = "mtt_restore_" + uuid4().hex
        if not re.fullmatch(r"mtt_restore_[a-f0-9]{32}", destination):
            raise ValueError("Restore target validation failed")
        docker(
            ["sh", "-c", 'exec createdb -U "$POSTGRES_USER" "$1"', "restore", destination],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        with target.open("rb") as source:
            docker(
                [
                    "sh",
                    "-c",
                    'exec pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --exit-on-error',
                    "restore",
                    destination,
                ],
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        check = docker(
            [
                "sh",
                "-c",
                'exec psql -U "$POSTGRES_USER" -d "$1" -Atc "SELECT version_num FROM alembic_version; SELECT count(*) FROM work_items;"',
                "restore",
                destination,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        print(
            "Restore verified in separate database "
            + destination
            + ": "
            + check.stdout.decode().strip().replace("\n", ", ")
        )
        # Keep the restored database for inspection. Never drop or overwrite an
        # existing target as part of a backup verification command.


if __name__ == "__main__":
    main()
