"""A browser that signed in before keeps its own sign-in budget (OWASP "device cookies"),
so someone guessing at an account's password cannot lock its owner out."""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.auth import digest
from app.main import app
from app.models import TrustedDevice, now
from app.services.retention import RetentionService

ORIGIN = {"Origin": "http://localhost:5173"}


def login(browser, email, password="synthetic-test-password"):
    return browser.post("/api/auth/login", headers=ORIGIN, json={"email": email, "password": password})


def guess_until_locked(browser, email):
    """Wrong passwords until the account's untrusted budget runs out."""
    codes = [login(browser, email, "wrong password guess").status_code for _ in range(11)]
    assert set(codes) == {401, 429} and codes[-1] == 429


def test_a_trusted_browser_signs_in_while_the_account_is_locked_for_others(client, seeded):
    email = seeded["user"].email
    with TestClient(app) as owner:
        assert login(owner, email).status_code == 200
        assert owner.cookies.get("mtt_device")
        guess_until_locked(client, email)
        assert login(client, email).status_code == 429  # Untrusted browsers wait.
        assert login(owner, email).status_code == 200  # The owner's browser does not.


def test_a_device_cookie_from_another_account_earns_no_trust(client, seeded):
    with TestClient(app) as attacker:
        assert login(attacker, seeded["other"].email).status_code == 200
        for _ in range(10):
            assert login(attacker, seeded["user"].email, "wrong password guess").status_code == 401
        assert login(attacker, seeded["user"].email).status_code == 429


def test_a_trusted_browser_still_has_its_own_limit(client, seeded):
    email = seeded["user"].email
    assert login(client, email).status_code == 200
    for _ in range(10):
        assert login(client, email, "wrong password guess").status_code == 401
    assert login(client, email).status_code == 429


def test_expired_devices_are_untrusted_and_purged(client, session, seeded):
    email = seeded["user"].email
    assert login(client, email).status_code == 200
    device = session.get(TrustedDevice, digest(client.cookies.get("mtt_device")))
    device.expires_at = now() - timedelta(seconds=1)
    session.commit()
    with TestClient(app) as other:
        guess_until_locked(other, email)
    assert login(client, email).status_code == 429
    assert RetentionService(session).run(apply=True)["temporary_records"]["trusted_devices"]["removed"] == 1
