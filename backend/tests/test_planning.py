from datetime import date

import pytest
from test_delivery import reviewed

from app.auth import Principal
from app.models import Meeting, Membership, WorkItem
from app.schemas import IndexInput, ItemPatch, PlanInput, PlanPatch
from app.services.errors import ServiceError
from app.services.meetings import MeetingService
from app.services.planning import PlanningService
from app.services.review import ReviewService

DAY = date(2026, 10, 3)


def test_plan_progress_is_persistent_and_independent_of_review(session, seeded):
    item = reviewed(session, seeded)
    service = PlanningService(session, seeded["principal"])
    entry = service.add("weekly", item["id"], PlanInput(expected_item_version=2, planned_on=DAY))
    service.patch(
        "weekly",
        item["id"],
        PlanPatch(expected_item_version=2, expected_version=1, planned_on=DAY, state="done"),
    )
    session.commit()
    session.expire_all()
    result = service.list(DAY)
    assert result["entries"][0]["state"] == "done"
    assert result["entries"][0]["stale"] is False
    assert session.get(WorkItem, item["id"]).status == "approved"
    assert entry["version"] == 1
    assert item["id"] not in [row["item_id"] for row in result["candidates"]]
    with pytest.raises(ServiceError, match="already"):
        service.add("weekly", item["id"], PlanInput(expected_item_version=2, planned_on=DAY))
    with pytest.raises(ServiceError, match="plan changed"):
        service.patch(
            "weekly",
            item["id"],
            PlanPatch(expected_item_version=2, expected_version=1, planned_on=DAY, state="planned"),
        )


def test_plan_is_personal_and_cannot_expose_other_workspace(session, seeded):
    item = reviewed(session, seeded)
    service = PlanningService(session, seeded["principal"])
    service.add("weekly", item["id"], PlanInput(expected_item_version=2, planned_on=DAY))
    session.add(Membership(user_id=seeded["other"].id, workspace_id=seeded["workspace"].id, role="editor"))
    session.commit()
    other = PlanningService(session, Principal(seeded["other"].id, seeded["workspace"].id, "editor"))
    assert other.list(DAY)["entries"] == []
    with pytest.raises(ServiceError, match="not found"):
        other.remove("weekly", item["id"])
    isolated = PlanningService(session, Principal(seeded["other"].id, seeded["isolated"].id, "owner"))
    assert isolated.list(DAY)["candidates"] == []
    with pytest.raises(ServiceError, match="Meeting not found"):
        isolated.add("weekly", item["id"], PlanInput(expected_item_version=2, planned_on=DAY))


def test_changed_outcome_requires_reconfirmation_and_old_transcript_cannot_resume(session, seeded):
    item = reviewed(session, seeded)
    service = PlanningService(session, seeded["principal"])
    service.add("weekly", item["id"], PlanInput(expected_item_version=2, planned_on=DAY))
    ReviewService(session, seeded["principal"]).patch(
        "weekly",
        item["id"],
        ItemPatch(expected_version=2, title="Corrected reviewed action", status="approved"),
    )
    session.commit()
    assert service.list(DAY)["entries"][0]["stale"]
    with pytest.raises(ServiceError, match="Reconfirm"):
        service.patch(
            "weekly",
            item["id"],
            PlanPatch(expected_item_version=3, expected_version=1, planned_on=DAY, state="done"),
        )
    assert not service.patch(
        "weekly",
        item["id"],
        PlanPatch(expected_item_version=3, expected_version=1, planned_on=DAY, state="planned"),
    )["stale"]
    meetings = MeetingService(session, seeded["principal"])
    meetings.index(
        IndexInput(
            meeting_id="weekly",
            title="Weekly",
            transcript="Action: Prepare a different reviewed checklist.",
            expected_version=meetings.get("weekly")["version"],
        )
    )
    session.commit()
    assert service.list(DAY)["entries"][0]["stale"]
    with pytest.raises(ServiceError, match="current approved"):
        service.patch(
            "weekly",
            item["id"],
            PlanPatch(expected_item_version=3, expected_version=2, planned_on=DAY, state="done"),
        )
    assert service.remove("weekly", item["id"])["ok"]


def test_plan_routes_validate_dates_versions_and_viewer_authority(client, auth, session, seeded):
    item = reviewed(session, seeded)
    root = f"/api/workspaces/{seeded['workspace'].id}"
    path = root + f"/meetings/weekly/outcomes/{item['id']}/plan"
    assert client.get(root + "/plan?day=2026-10-03").status_code == 401
    assert client.get(root + "/plan?day=invalid", headers=auth).status_code == 422
    body = {"expected_item_version": 2, "planned_on": "2026-10-03"}
    assert client.post(path, headers=auth, json={**body, "priority": True}).status_code == 422
    assert client.post(path, headers=auth, json={**body, "expected_item_version": 1}).status_code == 409
    assert client.post(path, headers=auth, json=body).status_code == 201
    assert len(client.get(root + "/plan?day=2026-10-03", headers=auth).json()["entries"]) == 1
    membership = session.get(Membership, (seeded["workspace"].id, seeded["user"].id))
    membership.role = "viewer"
    session.commit()
    assert client.delete(path, headers=auth).status_code == 403


def test_plan_hides_restricted_and_archived_meetings(session, seeded):
    item = reviewed(session, seeded)
    owner = PlanningService(session, seeded["principal"])
    owner.add("weekly", item["id"], PlanInput(expected_item_version=2, planned_on=DAY))
    meeting = MeetingService(session, seeded["principal"])
    record = session.query(Meeting).filter_by(slug="weekly", workspace_id=seeded["workspace"].id).one()
    record.visibility = "restricted"
    session.commit()
    viewer = PlanningService(session, Principal(seeded["other"].id, seeded["workspace"].id, "viewer"))
    assert viewer.list(DAY)["candidates"] == []
    meeting.delete("weekly")
    session.commit()
    assert owner.list(DAY)["entries"] == []
