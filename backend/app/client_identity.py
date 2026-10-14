"""Explicit network identity for budgets; forwarding never changes auth or URLs."""

from functools import lru_cache
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network

from fastapi import Request

from .services.errors import ServiceError
from .settings import settings


def canonical_ip(value: str) -> IPv4Address | IPv6Address:
    if not value or len(value) > 64 or value != value.strip() or "%" in value:
        raise ValueError("A single IP literal is required")
    address = ip_address(value)
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def budget_address(address: IPv4Address | IPv6Address) -> str:
    # One IPv6 subscriber usually holds a whole /64; per-address keys would let it rotate budgets.
    if isinstance(address, IPv6Address):
        return str(ip_network((address, 64), strict=False))
    return str(address)


# Shared mode pools every visitor into one network key, so a per-client limit
# would let a handful of requests lock everyone out. The site-wide ceiling is
# this many times higher; per-account budgets stay the real brute-force guard.
SHARED_BUDGET_FACTOR = 10


def budget_limit(per_client: int, shared: int | None = None) -> int:
    """The network budget for one client, or the site-wide ceiling in shared mode."""
    if settings.client_identity_mode != "shared":
        return per_client
    return shared if shared is not None else per_client * SHARED_BUDGET_FACTOR


@lru_cache(maxsize=16)
def trusted_networks(value: str):
    return tuple(ip_network(part) for part in value.split(",") if part)


def budget_key(request: Request, family: str) -> str:
    prefix = family + "-ip" if family in {"login", "visitor"} else family
    if settings.client_identity_mode == "shared":
        return family + ":shared"
    try:
        peer = canonical_ip(request.client.host if request.client else "")
    except ValueError:
        peer = None
    if settings.client_identity_mode == "direct":
        return prefix + ":" + (budget_address(peer) if peer is not None else "unknown")
    if peer is None or not any(peer in network for network in trusted_networks(settings.trusted_proxy_cidrs)):
        raise ServiceError(
            status_code=400,
            error="Request arrived through an untrusted route",
            where="client",
            extra={"code": "untrusted_client_route"},
        )
    values = request.headers.getlist(settings.client_ip_header)
    try:
        if len(values) != 1:
            raise ValueError("Exactly one client identity header is required")
        client = canonical_ip(values[0])
    except ValueError as exc:
        raise ServiceError(
            status_code=400,
            error="Client identity is missing or invalid",
            where="client",
            extra={"code": "invalid_client_identity"},
        ) from exc
    return prefix + ":" + budget_address(client)
