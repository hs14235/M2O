import re
from pathlib import Path

from app.settings import Settings

NGINX = Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf"


def megabytes(value: str) -> float:
    number, unit = re.fullmatch(r"(\d+)([km])", value).groups()  # type: ignore[union-attr]
    return int(number) / (1024 if unit == "k" else 1)


def test_only_the_transcription_route_accepts_large_uploads():
    config = NGINX.read_text(encoding="utf-8")
    default = re.search(r"^    client_max_body_size (\S+);", config, re.M)
    route = re.search(r"location ~ \^/api/workspaces/\[\^/\]\+/transcribe\$ \{(.*?)\}", config, re.S)
    assert default and route
    assert megabytes(default.group(1)) < 2
    limit = re.search(r"client_max_body_size (\S+);", route.group(1))
    assert limit is not None
    # nginx would answer 413 before the API's own size check could run.
    assert megabytes(limit.group(1)) * 1024 * 1024 > Settings(_env_file=None).transcription_max_bytes
