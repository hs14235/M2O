"""Account-wide local grant revocation is independent of workspace publishing rights."""

from datetime import timedelta

from app.models import Membership, ProviderConnection, now
from app.settings import settings


def test_removed_member_can_disconnect_own_grant_in_browser_with_csrf(client, session, seeded, auth):
    owner_grant = ProviderConnection(
        user_id=seeded["user"].id,
        provider="linkedin",
        encrypted_credentials="synthetic-owner-ciphertext",
        scopes=["w_member_social"],
        expires_at=now() + timedelta(hours=1),
    )
    other_grant = ProviderConnection(
        user_id=seeded["other"].id,
        provider="linkedin",
        encrypted_credentials="synthetic-other-ciphertext",
        scopes=["w_member_social"],
        expires_at=now() + timedelta(hours=1),
    )
    session.add_all([owner_grant, other_grant])
    session.commit()
    response = client.post(
        "/api/auth/login",
        json={"email": seeded["user"].email, "password": "synthetic-test-password"},
        headers={"Origin": settings.app_origin},
    )
    assert response.status_code == 200
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": response.json()["csrf_token"]}
    session.delete(session.get(Membership, (seeded["workspace"].id, seeded["user"].id)))
    session.commit()
    path = "/api/integrations/linkedin/publishing"
    assert client.delete(path, headers=auth).status_code == 403
    assert client.delete(path, headers={"Origin": settings.app_origin}).status_code == 403
    result = client.delete(path, headers=headers)
    assert result.status_code == 200 and result.json() == {"connected": False}
    session.expire_all()
    assert session.get(ProviderConnection, owner_grant.id).encrypted_credentials == ""
    assert (
        session.get(ProviderConnection, other_grant.id).encrypted_credentials == "synthetic-other-ciphertext"
    )


def test_global_grant_disconnect_denies_visitor_and_unauthenticated_access(client):
    path = "/api/integrations/linkedin/publishing"
    assert client.delete(path).status_code == 401
    visitor = client.post("/api/demo/start", headers={"Origin": settings.app_origin})
    assert visitor.status_code == 201
    headers = {"Origin": settings.app_origin, "X-CSRF-Token": visitor.json()["csrf_token"]}
    assert client.delete(path, headers=headers).status_code == 403
