"""Make the hosted site's owner password hash and provider encryption key, locally.

Run from backend: python -m scripts.hosted_secrets
Paste the two printed lines into the host's private environment settings (Render:
Environment). The password is read without echo and never leaves this machine; only its
Argon2 hash does. Keep the encryption key private: it protects stored provider tokens,
and changing it later disconnects every provider.
"""

import base64
import getpass
import secrets

from app.auth import hasher


def main() -> int:
    password = getpass.getpass("Owner password for the hosted site (12 to 256 characters): ")
    if not 12 <= len(password) <= 256:
        print("Use a password of 12 to 256 characters.")
        return 2
    if getpass.getpass("Repeat it: ") != password:
        print("The two entries differ.")
        return 2
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    print("OWNER_PASSWORD_HASH=" + hasher.hash(password))
    print("PROVIDER_ENCRYPTION_KEY=" + key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
