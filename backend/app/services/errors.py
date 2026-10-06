from typing import Any


class ServiceError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        error: str,
        where: str = "server",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error)
        detail: dict[str, Any] = {"where": where, "error": error}
        if extra:
            detail.update(extra)

        self.status_code = status_code
        self.detail = detail
