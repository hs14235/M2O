"""Save Slack application credentials from private terminal prompts without altering feature gates."""

import base64
import getpass
import os
import re
import tempfile
from pathlib import Path


def update_configuration(
    path: Path, client_id: str, client_secret: str, signing_secret: str, app_id: str
) -> None:
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", client_id)
        or not re.fullmatch(r"[A-Za-z0-9_.~-]{1,1000}", client_secret)
        or not re.fullmatch(r"[a-fA-F0-9]{32}", signing_secret)
        or not re.fullmatch(r"A[A-Z0-9]{7,63}", app_id)
    ):
        raise ValueError(
            "Use Slack's client ID, client secret and 32-character signing secret from app settings"
        )
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    values = {
        "SLACK_APP_ID": app_id,
        "SLACK_CLIENT_ID": client_id,
        "SLACK_CLIENT_SECRET": client_secret,
        "SLACK_SIGNING_SECRET": signing_secret,
    }
    existing = re.search(r"^PROVIDER_ENCRYPTION_KEY=(.*)$", content, re.MULTILINE)
    key = existing.group(1).strip().strip("\"'") if existing else ""
    if key:
        try:
            raw = base64.b64decode(key, altchars=b"-_", validate=True)
        except ValueError as exc:
            raise ValueError("Existing provider key is invalid; it was not replaced") from exc
        if len(raw) != 32:
            raise ValueError("Existing provider key is invalid; it was not replaced")
    else:
        values["PROVIDER_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
    for name, value in values.items():
        replacement = name + "=" + value
        if re.search(r"^" + name + r"=.*$", content, re.MULTILINE):
            content = re.sub(
                r"^" + name + r"=.*$", lambda _, line=replacement: line, content, flags=re.MULTILINE
            )
        else:
            content = content.rstrip("\n") + "\n" + replacement + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".env.slack.", delete=False
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main():
    path = Path(__file__).resolve().parents[1] / ".env"
    client_id = input("Slack application client ID: ").strip()
    client_secret = getpass.getpass("Slack client secret (hidden): ").strip()
    signing_secret = getpass.getpass("Slack signing secret (hidden): ").strip()
    app_id = input("Slack app ID (starts with A): ").strip()
    update_configuration(path, client_id, client_secret, signing_secret, app_id)
    print(
        "Private Compose credentials saved without displaying values. Feature gates and the current runtime were not changed."
    )


if __name__ == "__main__":
    main()
