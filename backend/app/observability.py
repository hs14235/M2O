import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record):
        value = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for field in ("request_id", "method", "path", "status", "duration_ms", "job_id", "error_code"):
            if hasattr(record, field):
                value[field] = getattr(record, field)
        return json.dumps(value)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("meeting")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # Third-party HTTP logs can contain OAuth query parameters.
    logging.getLogger("httpx").setLevel(logging.WARNING)
