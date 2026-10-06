"""Users retain control of their own grant after workspace authority changes."""

from datetime import timedelta

import pytest
from sqlalchemy import delete
from test_linkedin_publishing import configured as configured
from test_linkedin_publishing import connected

from app.auth import Principal
from app.models import LinkedInProfile, Membership, ProviderConnection, now
from app.services.errors import ServiceError
from app.services.linkedin_publishing import LinkedInPublishingService
from app.settings import settings


@pytest.mark.parametrize("role", ["editor", "viewer"])
def test_demoted_member_can_disconnect_own_grant_without_publishing_authority(
    session, seeded, configured, role
):
    connected(session, configured)
    session.add(
        LinkedInProfile(
            user_id=configured.user_id,
            subject="synthetic-subject",
            profile={"name": "Synthetic"},
            scopes=["openid", "profile"],
        )
    )
    other = ProviderConnection(
        user_id=seeded["other"].id,
        provider="linkedin",
        encrypted_credentials="synthetic-other-ciphertext",
        scopes=["w_member_social"],
        expires_at=now() + timedelta(hours=1),
    )
    session.add(other)
    session.get(Membership, (configured.workspace_id, configured.user_id)).role = role
    session.commit()
    principal = Principal(
        configured.user_id,
        configured.workspace_id,
        role,
        session_hash=configured.session_hash,
        auth_version=seeded["user"].auth_version,
    )
    service = LinkedInPublishingService(session, principal)
    assert not service.status()["can_publish"] and not service.status()["can_connect"]
    with pytest.raises(ServiceError) as denied:
        service.begin()
    assert denied.value.status_code == 403
    session.rollback()
    assert service.disconnect() == {"connected": False}
    session.commit()
    assert service.connection().state == "reauthorization_required"
    grant_retained = bool(service.connection().encrypted_credentials)
    assert not grant_retained
    assert session.get(ProviderConnection, other.id).state == "connected"
    assert session.get(LinkedInProfile, configured.user_id) is not None


def test_removed_member_can_disconnect_own_account_grant(session, seeded, configured):
    connected(session, configured)
    session.add(Membership(user_id=seeded["other"].id, workspace_id=configured.workspace_id, role="owner"))
    session.execute(
        delete(Membership).where(
            Membership.workspace_id == configured.workspace_id, Membership.user_id == configured.user_id
        )
    )
    session.commit()
    with pytest.raises(ServiceError):
        LinkedInPublishingService(session, configured).disconnect()
    session.rollback()
    account = Principal(
        configured.user_id, session_hash=configured.session_hash, auth_version=seeded["user"].auth_version
    )
    service = LinkedInPublishingService(session, account)
    assert service.disconnect_account() == {"connected": False}
    session.commit()
    assert service.connection().state == "reauthorization_required"


def test_another_account_cannot_select_the_owner_grant(session, seeded, configured):
    connected(session, configured)
    owner = LinkedInPublishingService(session, configured).connection()
    other = Principal(seeded["other"].id, auth_version=seeded["other"].auth_version)
    assert LinkedInPublishingService(session, other).disconnect_account() == {"connected": False}
    session.commit()
    assert owner.state == "connected"


@pytest.mark.parametrize("revoke", ["visitor", "auth_version", "inactive"])
def test_visitor_or_revoked_account_cannot_disconnect_saved_grant(session, seeded, configured, revoke):
    connected(session, configured)
    principal = Principal(configured.user_id, auth_version=seeded["user"].auth_version)
    if revoke == "visitor":
        seeded["user"].is_visitor, seeded["user"].visitor_expires_at = True, now() + timedelta(hours=1)
    elif revoke == "auth_version":
        seeded["user"].auth_version += 1
    else:
        seeded["user"].active = False
    session.commit()
    service = LinkedInPublishingService(session, principal)
    with pytest.raises(ServiceError) as denied:
        service.disconnect_account()
    assert denied.value.status_code == (403 if revoke == "visitor" else 401)
    session.rollback()
    assert service.connection().state == "connected"


def test_global_http_disconnect_requires_browser_and_ignores_another_actor(
    client, auth, session, seeded, configured
):
    connected(session, configured)
    owner = LinkedInPublishingService(session, configured).connection()
    other = ProviderConnection(
        user_id=seeded["other"].id,
        provider="linkedin",
        encrypted_credentials="synthetic-other-ciphertext",
        scopes=["w_member_social"],
        expires_at=now() + timedelta(hours=1),
    )
    session.add(other)
    session.commit()
    path = "/api/integrations/linkedin/publishing"
    assert client.delete(path).status_code == 401
    assert client.delete(path, headers=auth).status_code == 403
    signed_in = client.post(
        "/api/auth/login",
        headers={"Origin": settings.app_origin},
        json={"email": "owner@example.test", "password": "synthetic-test-password"},
    )
    assert signed_in.status_code == 200
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": signed_in.json()["csrf_token"]}
    result = client.delete(path + "?user_id=" + seeded["other"].id, headers=headers)
    assert result.status_code == 200 and result.json() == {"connected": False}
    session.expire_all()
    assert session.get(ProviderConnection, owner.id).state == "reauthorization_required"
    assert session.get(ProviderConnection, other.id).state == "connected"


def test_global_http_disconnect_denies_a_visitor_browser(client, session, seeded, configured):
    connected(session, configured)
    owner = LinkedInPublishingService(session, configured).connection()
    signed_in = client.post(
        "/api/auth/login",
        headers={"Origin": settings.app_origin},
        json={"email": "owner@example.test", "password": "synthetic-test-password"},
    )
    assert signed_in.status_code == 200
    seeded["user"].is_visitor, seeded["user"].visitor_expires_at = True, now() + timedelta(hours=1)
    session.commit()
    result = client.delete(
        "/api/integrations/linkedin/publishing",
        headers={"Origin": settings.app_origin, "X-CSRF-Token": signed_in.json()["csrf_token"]},
    )
    assert result.status_code == 403
    session.expire_all()
    assert session.get(ProviderConnection, owner.id).state == "connected"
