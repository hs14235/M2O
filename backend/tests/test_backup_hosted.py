import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
database_url = runpy.run_path(str(ROOT / "scripts" / "backup_hosted.py"))["database_url"]


@pytest.mark.parametrize(
    "pasted,expected",
    [
        ("postgresql://u:p@ep-synthetic.us-east-1.aws.neon.tech/db?sslmode=require", None),
        ("  postgres://u:p@db.example.test/db \n", "postgresql://u:p@db.example.test/db"),
        ("postgresql+psycopg://u:p@db.example.test/db", "postgresql://u:p@db.example.test/db"),
    ],
)
def test_backup_accepts_direct_connection_strings(pasted, expected):
    assert database_url(pasted) == (expected or pasted)


@pytest.mark.parametrize(
    "pasted",
    [
        "postgresql://u:p@ep-synthetic-pooler.us-east-1.aws.neon.tech/db",
        "postgresql://u:p@db.example.test",
        "mysql://u:p@db.example.test/db",
        "not a connection string",
    ],
)
def test_backup_refuses_pooled_or_incomplete_connection_strings(pasted):
    with pytest.raises(ValueError):
        database_url(pasted)
