"""Configure local Jira credentials through private terminal prompts."""

import base64
import getpass
import os
import re
import tempfile
from pathlib import Path


def update_configuration(path: Path, client_id: str, client_secret: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", client_id) or not re.fullmatch(
        r"[A-Za-z0-9_.~-]{1,1000}", client_secret
    ):
        raise ValueError(
            "Use the client ID and secret from the app settings; unexpected characters were rejected"
        )
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = re.search(r"^PROVIDER_ENCRYPTION_KEY=(.*)$", text, re.MULTILINE)
    existing_key = existing.group(1).strip().strip("\"'") if existing else ""
    if existing_key:
        try:
            decoded = base64.b64decode(existing_key, altchars=b"-_", validate=True)
        except ValueError as exc:
            raise ValueError("Existing provider key is invalid; it was not replaced") from exc
        if len(decoded) != 32:
            raise ValueError("Existing provider key must encode 32 bytes; it was not replaced")
        updates = {"JIRA_CLIENT_ID": client_id, "JIRA_CLIENT_SECRET": client_secret}
    else:
        updates = {
            "JIRA_CLIENT_ID": client_id,
            "JIRA_CLIENT_SECRET": client_secret,
            "PROVIDER_ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        }
    for name, value in updates.items():
        line = name + "=" + value
        if re.search(r"^" + name + r"=.*$", text, re.MULTILINE):
            text = re.sub(
                r"^" + name + r"=.*$", lambda _, replacement=line: replacement, text, flags=re.MULTILINE
            )
        else:
            text = text.rstrip("\n") + "\n" + line + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".env.jira.", delete=False
    ) as temporary:
        temporary.write(text)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    client_id = input("Jira application client ID: ").strip()
    client_secret = getpass.getpass("Jira client secret (hidden): ").strip()
    update_configuration(path, client_id, client_secret)
    print(
        "Private Compose configuration saved. No credentials were displayed. Recreate the API and worker to load the settings."
    )


if __name__ == "__main__":
    main()
