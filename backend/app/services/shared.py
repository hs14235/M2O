"""Strict legacy citation conversion used only by the data importer."""

from .errors import ServiceError


def normalize_source_i(value, retrieved_idxs):
    if isinstance(value, bool) or not isinstance(value, int) or value not in retrieved_idxs:
        raise ServiceError(
            status_code=422, error="Citation is not a persisted transcript chunk", where="client"
        )
    return value
