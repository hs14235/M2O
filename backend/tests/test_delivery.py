import json
from datetime import date

import pytest
from pydantic import SecretStr
from test_meeting_lifecycle import extracted

from app.auth import Principal
from app.models import Membership
from app.schemas import ExportInput, IndexInput, ItemPatch, ParticipantInput
from app.services.delivery import export_outcomes, integration_catalog
from app.services.errors import ServiceError
from app.services.issues import IssueService
from app.services.meetings import MeetingService
from app.services.review import ReviewService
from app.settings import settings


def reviewed(session, seeded):
    details = extracted(session, seeded)
    item = details["tasks"][0]
    ReviewService(session, seeded["principal"]).patch(
        "weekly", item["id"], ItemPatch(expected_version=1, status="approved")
    )
    session.commit()
    return item


def test_catalog_exposes_capabilities_without_credentials(session, seeded, monkeypatch):
    monkeypatch.setattr(settings, "slack_client_id", "")
    monkeypatch.setattr(settings, "slack_client_secret", SecretStr(""))
    monkeypatch.setattr(settings, "github_token", SecretStr("synthetic-private-token"))
    monkeypatch.setattr(settings, "github_allowed_repos", "synthetic/demo")
    catalog = integration_catalog(session, seeded["principal"])
    assert "synthetic-private-token" not in json.dumps(catalog)
    assert next(p for p in catalog if p["id"] == "github")["can_publish"] is False
    slack = next(p for p in catalog if p["id"] == "slack")
    assert slack["status"] == "needs_configuration"
    assert not slack["can_preview"] and not slack["can_publish"]
    jira = next(p for p in catalog if p["id"] == "jira")
    assert jira["status"] == "needs_configuration"
    assert not jira["can_preview"] and not jira["can_publish"]
    monkeypatch.setattr(settings, "public_demo_mode", False)
    assert not next(p for p in integration_catalog(session, seeded["principal"]) if p["id"] == "github")[
        "can_publish"
    ]
    IssueService(session, seeded["principal"]).bind("synthetic/demo", 0)
    assert next(p for p in integration_catalog(session, seeded["principal"]) if p["id"] == "github")[
        "can_publish"
    ]
    viewer = Principal(seeded["user"].id, seeded["workspace"].id, "viewer")
    session.get(Membership, (seeded["workspace"].id, seeded["user"].id)).role = "viewer"
    session.commit()
    assert not next(p for p in integration_catalog(session, viewer) if p["id"] == "github")["can_publish"]


@pytest.mark.parametrize("format", ["json", "markdown"])
def test_export_is_provider_independent_and_evidence_is_opt_in(session, seeded, format):
    item = reviewed(session, seeded)
    payload = ExportInput(format=format, expected_revision=1, versions={item["id"]: 2})
    artifact = export_outcomes(session, seeded["principal"], "weekly", payload)
    assert artifact["filename"].startswith("weekly-reviewed-outcomes.")
    assert item["title"] in artifact["content"]
    assert "Alex: Action:" not in artifact["content"]
    assert "github" not in artifact["content"].lower()
    if format == "json":
        data = json.loads(artifact["content"])
        assert data["schema_version"] == 1 and data["meeting"]["revision"] == 1
        assert "text" not in data["outcomes"][0]["evidence"][0]
    included = export_outcomes(
        session, seeded["principal"], "weekly", payload.model_copy(update={"include_evidence": True})
    )
    assert "Alex: Action:" in included["content"]
    assert artifact["snapshot_hash"] != included["snapshot_hash"]


def test_export_rejects_drafts_and_stale_review_versions(session, seeded):
    item = extracted(session, seeded)["tasks"][0]
    payload = ExportInput(format="json", expected_revision=1, versions={item["id"]: 1})
    with pytest.raises(ServiceError, match="changed"):
        export_outcomes(session, seeded["principal"], "weekly", payload)
    ReviewService(session, seeded["principal"]).patch(
        "weekly", item["id"], ItemPatch(expected_version=1, status="approved")
    )
    with pytest.raises(ServiceError, match="changed"):
        export_outcomes(session, seeded["principal"], "weekly", payload)


def test_export_rejects_replaced_transcript(session, seeded):
    item = reviewed(session, seeded)
    service = MeetingService(session, seeded["principal"])
    service.index(
        IndexInput(
            meeting_id="weekly",
            title="Weekly",
            transcript="Decision: Use the updated checklist.",
            expected_version=service.get("weekly")["version"],
        )
    )
    session.commit()
    with pytest.raises(ServiceError, match="Transcript changed"):
        export_outcomes(
            session,
            seeded["principal"],
            "weekly",
            ExportInput(format="json", expected_revision=1, versions={item["id"]: 2}),
        )


def test_delivery_routes_enforce_auth_scope_and_validation(client, auth, session, seeded):
    item = reviewed(session, seeded)
    root = f"/api/workspaces/{seeded['workspace'].id}"
    assert client.get(root + "/integrations").status_code == 401
    assert client.get(root + "/integrations", headers=auth).status_code == 200
    assert (
        client.get(f"/api/workspaces/{seeded['isolated'].id}/integrations", headers=auth).status_code == 404
    )
    payload = {"format": "json", "expected_revision": 1, "versions": {item["id"]: 2}}
    assert client.post(root + "/meetings/weekly/export", headers=auth, json=payload).status_code == 200
    assert (
        client.post(
            root + "/meetings/weekly/export", headers=auth, json={**payload, "token": "synthetic"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            root + "/meetings/weekly/export", headers=auth, json={**payload, "versions": {}}
        ).status_code
        == 422
    )


def test_export_cannot_read_another_workspace_meeting(session, seeded):
    item = reviewed(session, seeded)
    other = Principal(seeded["other"].id, seeded["isolated"].id, "owner")
    with pytest.raises(ServiceError) as error:
        export_outcomes(
            session,
            other,
            "weekly",
            ExportInput(format="markdown", expected_revision=1, versions={item["id"]: 2}),
        )
    assert error.value.status_code == 404


def test_export_preserves_calendar_date_and_confirmed_owner(session, seeded):
    item = reviewed(session, seeded)
    service = ReviewService(session, seeded["principal"])
    owner = service.add_participant(ParticipantInput(name="Synthetic Owner", role="People lead"))
    service.patch(
        "weekly",
        item["id"],
        ItemPatch(expected_version=2, owner_id=owner["id"], due_date=date(2026, 10, 5), status="approved"),
    )
    session.commit()
    payload = ExportInput(format="json", expected_revision=1, versions={item["id"]: 3})
    artifact = export_outcomes(session, seeded["principal"], "weekly", payload)
    exported = json.loads(artifact["content"])["outcomes"][0]
    assert exported["due_date"] == "2026-10-05"
    assert exported["owner"]["name"] == "Synthetic Owner"
    markdown = export_outcomes(
        session, seeded["principal"], "weekly", payload.model_copy(update={"format": "markdown"})
    )
    assert "Owner: Synthetic Owner (People lead)" in markdown["content"]
    assert "Due date: 2026-10-05" in markdown["content"]
