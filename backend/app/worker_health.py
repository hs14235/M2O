"""Local supervisor-owned health signal; no job payload or credentials."""

import json
import math
import os
import time
from pathlib import Path
from uuid import uuid4

from .services.errors import ServiceError
from .settings import settings


def worker_available(path: str, timeout: int, deadline: int, *, at: float | None = None) -> bool:
    if not path:
        return True  # Separate/native workers are monitored by their operator.
    current = time.monotonic() if at is None else at
    try:
        with Path(path).open(encoding="utf-8") as source:
            raw = source.read(513)
        if len(raw) > 512:
            return False
        value = json.loads(raw)
        seen, started = value["seen_at"], value["started_at"]
        if type(seen) not in {int, float} or not math.isfinite(seen) or not 0 <= current - seen <= timeout:
            return False
        if started is not None and (
            type(started) not in {int, float}
            or not math.isfinite(started)
            or not 0 <= seen - started
            or not 0 <= current - started <= deadline
        ):
            return False
        return True
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return False


def wake_stamp(path: str) -> tuple[int, int] | None:
    if not path:
        return None
    try:
        status = os.stat(path)
    except OSError:
        return None
    return status.st_ino, status.st_mtime_ns


def signal_wake(path: str) -> None:
    """Ring an idle worker after a job commits; the empty file carries no job data."""
    if not path:
        return
    # A fresh inode per signal, so two signals within one timestamp tick still differ.
    temporary = f"{path}.{uuid4().hex}.tmp"
    os.close(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    os.replace(temporary, path)


def require_worker() -> None:
    if not worker_available(
        settings.worker_heartbeat_file, settings.worker_heartbeat_timeout, settings.worker_job_deadline
    ):
        raise ServiceError(
            status_code=503,
            error="Worker is temporarily unavailable",
            extra={"code": "worker_unavailable"},
        )


class WorkerPulse:
    def __init__(self, path: str):
        self.path = path
        self.started_at: float | None = None

    def idle(self) -> None:
        self.started_at = None
        self.write()

    def busy(self) -> None:
        self.started_at = time.monotonic()
        self.write()

    def write(self) -> None:
        if not self.path:
            return
        value = {"seen_at": time.monotonic(), "started_at": self.started_at}
        temporary = self.path + ".tmp"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                json.dump(value, target, allow_nan=False)
            os.replace(temporary, self.path)
        except OSError:
            raise RuntimeError("Worker health signaling failed") from None
