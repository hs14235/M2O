"""Authenticated encryption bound to the provider account, never browser-visible."""

import base64
import json
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .models import ProviderConnection
from .services.errors import ServiceError
from .settings import settings


def cipher() -> AESGCM:
    try:
        key = base64.b64decode(
            settings.provider_encryption_key.get_secret_value(), altchars=b"-_", validate=True
        )
        return AESGCM(key)
    except (ValueError, TypeError) as exc:
        raise ServiceError(
            status_code=503, error="Provider credential storage requires configuration", where="provider"
        ) from exc


def associated_data(connection: ProviderConnection) -> bytes:
    return f"m2o:v1:{connection.provider}:{connection.id}:{connection.user_id}".encode()


def seal(connection: ProviderConnection, credentials: dict) -> str:
    nonce = secrets.token_bytes(12)
    value = json.dumps(credentials, separators=(",", ":")).encode()
    return (
        "v1:"
        + base64.urlsafe_b64encode(
            nonce + cipher().encrypt(nonce, value, associated_data(connection))
        ).decode()
    )


def unseal(connection: ProviderConnection) -> dict:
    try:
        if not connection.encrypted_credentials.startswith("v1:"):
            raise ValueError("Unknown credential version")
        data = base64.b64decode(connection.encrypted_credentials[3:], altchars=b"-_", validate=True)
        return json.loads(cipher().decrypt(data[:12], data[12:], associated_data(connection)))
    except (InvalidTag, ValueError, TypeError) as exc:
        raise ServiceError(
            status_code=503,
            error="Provider credentials cannot be opened; contact the operator",
            where="provider",
        ) from exc
