import pytest

from scripts.lifecycle_browser_runtime import validate_binding


@pytest.mark.parametrize(
    "host", ["8.8.8.8", "0.0.0.0", "127.0.0.1", "169.254.1.1", "224.0.0.1", "::1", "example.com"]
)
def test_phone_preview_rejects_public_unspecified_loopback_and_non_ipv4_hosts(host):
    with pytest.raises(ValueError):
        validate_binding(host, True)


def test_private_acceptance_credentials_cannot_be_exposed_to_lan():
    with pytest.raises(ValueError):
        validate_binding("192.168.0.116", False)
    assert validate_binding("127.0.0.1", False) == "127.0.0.1"


def test_phone_preview_accepts_explicit_private_address():
    assert validate_binding("192.168.0.116", True) == "192.168.0.116"
