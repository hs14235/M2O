import multiprocessing
from datetime import timedelta

import pytest
from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import select, text

from app.auth import digest
from app.client_identity import budget_key, budget_limit
from app.models import RateBucket, now
from app.services.errors import ServiceError
from app.settings import Settings, settings


def request(peer="192.0.2.10", headers=()):
    return Request(
        {
            "type": "http",
            "client": (peer, 12345),
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers],
        }
    )


def proxy(monkeypatch):
    monkeypatch.setattr(settings, "client_identity_mode", "trusted_proxy")
    monkeypatch.setattr(settings, "client_ip_header", "cf-connecting-ip")
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "192.0.2.10/32,192.0.2.11/32")


def test_direct_and_shared_modes_ignore_all_forwarding_headers(monkeypatch):
    forged = [("cf-connecting-ip", "203.0.113.99"), ("x-forwarded-for", "203.0.113.88")]
    assert budget_key(request("198.51.100.1", forged), "login") == "login-ip:198.51.100.1"
    monkeypatch.setattr(settings, "client_identity_mode", "shared")
    assert budget_key(request("198.51.100.1", forged), "login") == "login:shared"
    assert budget_key(request("198.51.100.2"), "login") == "login:shared"


def test_client_budget_survives_proxy_changes_and_keeps_distinct_clients(monkeypatch):
    proxy(monkeypatch)
    first = budget_key(request(headers=[("cf-connecting-ip", "203.0.113.1")]), "visitor")
    assert first == budget_key(
        request("192.0.2.11", [("cf-connecting-ip", "203.0.113.1"), ("x-forwarded-for", "fake")]), "visitor"
    )
    assert first != budget_key(request(headers=[("cf-connecting-ip", "203.0.113.2")]), "visitor")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "unknown",
        "203.0.113.1, 203.0.113.2",
        "203.0.113.1:80",
        "[2001:db8::1]",
        "fe80::1%eth0",
        " 203.0.113.1",
        "203.0.113.1 ",
        "a" * 65,
    ],
)
def test_invalid_trusted_identity_cannot_create_a_budget(monkeypatch, value):
    proxy(monkeypatch)
    with pytest.raises(ServiceError) as result:
        budget_key(request(headers=[("cf-connecting-ip", value)]), "visitor")
    assert result.value.status_code == 400
    assert result.value.detail["code"] == "invalid_client_identity"


def test_missing_duplicate_or_untrusted_identity_is_rejected(monkeypatch):
    proxy(monkeypatch)
    for headers in ([], [("CF-Connecting-IP", "203.0.113.1"), ("cf-connecting-ip", "203.0.113.2")]):
        with pytest.raises(ServiceError):
            budget_key(request(headers=headers), "login")
    with pytest.raises(ServiceError) as result:
        budget_key(request("198.51.100.10", [("cf-connecting-ip", "203.0.113.1")]), "login")
    assert result.value.detail["code"] == "untrusted_client_route"


@pytest.mark.parametrize(
    "left,right",
    [
        ("2001:db8:0:0:0:0:0:1", "2001:db8::1"),
        ("::ffff:203.0.113.1", "203.0.113.1"),
    ],
)
def test_equivalent_addresses_and_shared_nat_keep_one_key(monkeypatch, left, right):
    proxy(monkeypatch)
    assert budget_key(request(headers=[("cf-connecting-ip", left)]), "login") == budget_key(
        request(headers=[("cf-connecting-ip", right)]), "login"
    )


@pytest.mark.parametrize("mode", ["trusted_proxy", "direct"])
def test_ipv6_rotation_within_one_64_keeps_one_budget(monkeypatch, mode):
    proxy(monkeypatch)
    monkeypatch.setattr(settings, "client_identity_mode", mode)

    def key(address):
        if mode == "direct":
            return budget_key(request(address), "visitor")
        return budget_key(request(headers=[("cf-connecting-ip", address)]), "visitor")

    first = key("2001:db8:1:2::1")
    assert first == "visitor-ip:2001:db8:1:2::/64"
    assert key("2001:db8:1:2:ffff:abcd:1234:9") == first
    assert key("2001:db8:1:3::1") != first
    # IPv4 clients are unaffected by the IPv6 grouping.
    assert key("203.0.113.1") == "visitor-ip:203.0.113.1"


def test_shared_mode_uses_site_wide_visitor_limit(monkeypatch):
    monkeypatch.setattr(settings, "visitor_start_limit", 10)
    monkeypatch.setattr(settings, "shared_visitor_start_limit", 150)
    monkeypatch.setattr(settings, "client_identity_mode", "shared")
    assert budget_limit(settings.visitor_start_limit, settings.shared_visitor_start_limit) == 150
    monkeypatch.setattr(settings, "client_identity_mode", "direct")
    assert budget_limit(settings.visitor_start_limit, settings.shared_visitor_start_limit) == 10


@pytest.mark.parametrize("cidrs", ["*", "0.0.0.0/0", "::/0", "192.0.2.1/24", "192.0.2.1,,192.0.2.2"])
def test_configuration_rejects_wildcard_and_ambiguous_peers(cidrs):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, client_identity_mode="trusted_proxy", trusted_proxy_cidrs=cidrs)


def test_settings_require_explicit_trust_and_only_supported_single_headers():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, client_identity_mode="trusted_proxy")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            client_identity_mode="trusted_proxy",
            trusted_proxy_cidrs="192.0.2.10",
            client_ip_header="x-forwarded-for",
        )


def test_http_budgets_independent_of_other_clients_and_proxy_peers(engine, seeded, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    proxy(monkeypatch)
    origin = {"Origin": settings.app_origin}
    body = {"email": "absent@example.test"}
    with TestClient(app, client=("192.0.2.10", 10000)) as client:
        headers = {**origin, "CF-Connecting-IP": "203.0.113.1"}
        for _ in range(10):
            assert client.post("/api/auth/recovery/request", headers=headers, json=body).status_code == 202
        assert client.post("/api/auth/recovery/request", headers=headers, json=body).status_code == 429
        assert (
            client.post(
                "/api/auth/recovery/request",
                headers={**origin, "CF-Connecting-IP": "203.0.113.2", "X-Forwarded-For": "203.0.113.1"},
                json=body,
            ).status_code
            == 202
        )
        assert (
            client.post(
                "/api/auth/login",
                headers={"CF-Connecting-IP": "203.0.113.2"},
                json={"email": "absent@example.test", "password": "bad"},
            ).status_code
            == 403
        )
    with TestClient(app, client=("192.0.2.11", 10001)) as other_peer:
        assert other_peer.post("/api/auth/recovery/request", headers=headers, json=body).status_code == 429
        assert other_peer.get("/healthz").status_code == 200


def process_budget(dsn, schema, barrier, result):
    from sqlalchemy import create_engine

    from app import database
    from app.limits import consume

    connection_engine = create_engine(
        dsn, hide_parameters=True, connect_args={"options": "-csearch_path=" + schema}
    )
    database.get_engine = lambda: connection_engine
    try:
        barrier.wait(timeout=20)
        try:
            consume("phase8-process-budget", 1)
            result.put(200)
        except ServiceError as error:
            result.put(error.status_code)
    finally:
        connection_engine.dispose()


def test_two_processes_share_first_insert_exhaustion_and_rollover(engine, session):
    if engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL process/row-lock regression")
    with engine.connect() as connection:
        schema = connection.execute(text("SELECT current_schema()")).scalar_one()
    context = multiprocessing.get_context("spawn")
    dsn = engine.url.render_as_string(hide_password=False)

    def race():
        barrier, result = context.Barrier(2), context.Queue()
        children = [
            context.Process(target=process_budget, args=(dsn, schema, barrier, result)) for _ in range(2)
        ]
        try:
            for child in children:
                child.start()
            values = [result.get(timeout=30) for _ in children]
            for child in children:
                child.join(timeout=10)
                assert child.exitcode == 0
            assert sorted(values) == [200, 429]
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join(timeout=10)
            result.close()

    race()
    row = session.scalar(select(RateBucket).where(RateBucket.key == digest("phase8-process-budget")))
    assert row.count == 1
    row.expires_at = now() - timedelta(seconds=1)
    session.commit()
    race()
    session.expire_all()
    assert session.get(RateBucket, row.key).count == 1
