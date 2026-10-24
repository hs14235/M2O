"""Back up the live site's database to this machine.

Run from the repository root:  python scripts/backup_hosted.py
Paste the database's direct connection string when asked (Neon: Connection details,
pooled connection off). It is read without echo and passed to a temporary PostgreSQL 17
container through an environment variable, so it never appears in a command line, a file
or this repository. The dump is a dated pg_dump custom-format file in ~/M2O-backups;
keep that folder private, since it holds the live site's data.
"""

import argparse
import getpass
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

IMAGE = "postgres:17-alpine"


def database_url(value: str) -> str:
    """A direct PostgreSQL URL for pg_dump; the SQLAlchemy driver suffix is dropped."""
    value = value.strip().replace("postgresql+psycopg://", "postgresql://", 1)
    if value.startswith("postgres://"):
        value = "postgresql://" + value.removeprefix("postgres://")
    parts = urlsplit(value)
    if parts.scheme != "postgresql" or not parts.hostname or not parts.path.strip("/"):
        raise ValueError("Paste the full postgresql:// connection string, including the database name")
    # Neon marks pooled hosts "-pooler"; a transaction pooler can break pg_dump's snapshot.
    if "-pooler." in parts.hostname:
        raise ValueError("Use the direct connection string, not the pooled one")
    return value


def run(args: list[str], env: dict[str, str], **options) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "run", "--rm", "-i", "-e", "M2O_BACKUP_URL", IMAGE, *args],
        env=env,
        **options,
    )


def backup(url: str, folder: Path) -> tuple[Path, int]:
    """Dumps the database into folder and reads the archive back; returns it and its table count."""
    env = {**os.environ, "M2O_BACKUP_URL": url}
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ("m2o-live-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".dump")
    with target.open("xb") as output:
        dump = run(
            ["sh", "-c", 'exec pg_dump --format=custom --no-owner "$M2O_BACKUP_URL"'],
            env,
            stdout=output,
            stderr=subprocess.PIPE,
        )
    if dump.returncode:
        target.unlink(missing_ok=True)
        # pg_dump's own message names the problem (password, host, SSL) without the URL.
        lines = dump.stderr.decode(errors="replace").strip().splitlines() or ["pg_dump failed"]
        raise RuntimeError("Backup failed: " + lines[-1])
    # Read the archive back: it must list the schema version and the data of every table.
    with target.open("rb") as source:
        listing = subprocess.run(
            ["docker", "run", "--rm", "-i", IMAGE, "pg_restore", "--list"],
            stdin=source,
            capture_output=True,
        )
    entries = listing.stdout.decode(errors="replace")
    tables = entries.count(" TABLE DATA ")
    if listing.returncode or "alembic_version" not in entries or not tables:
        raise RuntimeError("The dump was written but could not be read back; keep it and try again.")
    return target, tables


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--folder", type=Path, default=Path.home() / "M2O-backups")
    args = parser.parse_args()
    try:
        url = database_url(getpass.getpass("Live database connection string (not shown): "))
        target, tables = backup(url, args.folder)
    except (ValueError, RuntimeError) as exc:
        print(exc)
        return 1
    size = target.stat().st_size / 1_000_000
    print(f"Backup saved: {target} ({size:.1f} MB, {tables} tables). Keep this folder private.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
