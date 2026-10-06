from datetime import date

import pytest
from test_delivery import reviewed

from app.auth import Principal
from app.models import Meeting, Membership, Participant, WorkItem
from app.schemas import IndexInput, PlanInput, PlanPatch
from app.services.calendar import CalendarService
from app.services.errors import ServiceError
from app.services.meetings import MeetingService
from app.services.planning import PlanningService

DAY = date(2026, 10, 5)


def test_calendar_all_kinds_dates_and_personal_state_are_separate(session, seeded):
    item = reviewed(session, seeded)
    original = session.get(WorkItem, item["id"])
    original.due_hint = "after budget approval"
    person = Participant(
        workspace_id=seeded["workspace"].id, name="Confirmed colleague", confirmed_by=seeded["user"].id
    )
    session.add(person)
    session.flush()
    original.owner_id = person.id
    for index, kind in enumerate(("decision", "risk", "blocker", "follow_up")):
        session.add(
            WorkItem(
                workspace_id=original.workspace_id,
                meeting_id=original.meeting_id,
                revision_id=original.revision_id,
                fingerprint=f"calendar-{index}",
                kind=kind,
                title=f"Reviewed {kind}",
                body="Synthetic outcome",
                status="approved",
                due_date=DAY.isoformat(),
            )
        )
    session.commit()
    planner = PlanningService(session, seeded["principal"])
    plan = planner.add(
        "weekly", original.id, PlanInput(expected_item_version=original.version, planned_on=DAY)
    )
    planner.patch(
        "weekly",
        original.id,
        PlanPatch(
            expected_item_version=original.version,
            expected_version=plan["version"],
            state="done",
            planned_on=DAY,
        ),
    )
    session.commit()
    result = CalendarService(session, seeded["principal"]).list(DAY, DAY)
    assert {entry["kind"] for entry in result["entries"]} == {
        "action",
        "decision",
        "risk",
        "blocker",
        "follow_up",
    }
    action = next(entry for entry in result["entries"] if entry["item_id"] == original.id)
    assert action["due_date"] is None and not action["scheduled"]
    assert action["due_hint"] == "after budget approval"
    assert action["owner_name"] == person.name and action["owner_confirmed"]
    assert action["personal_plan"]["state"] == "done" and action["review_status"] == "approved"
    assert (
        len(
            CalendarService(session, seeded["principal"]).list(DAY, DAY, include_unscheduled=False)["entries"]
        )
        == 4
    )
    original.version += 1
    session.commit()
    assert next(
        row
        for row in CalendarService(session, seeded["principal"]).list(DAY, DAY)["entries"]
        if row["item_id"] == original.id
    )["personal_plan"]["stale"]


def test_calendar_revision_visibility_and_pagination(session, seeded):
    item = reviewed(session, seeded)
    meeting = session.get(Meeting, session.get(WorkItem, item["id"]).meeting_id)
    meeting.visibility = "restricted"
    session.add(Membership(workspace_id=meeting.workspace_id, user_id=seeded["other"].id, role="editor"))
    session.commit()
    editor = Principal(seeded["other"].id, meeting.workspace_id, "editor")
    assert CalendarService(session, editor).list(DAY, DAY)["entries"] == []
    with pytest.raises(ServiceError) as error:
        CalendarService(session, editor).list(DAY, DAY, meeting_id="weekly")
    assert error.value.status_code == 404
    owner = CalendarService(session, seeded["principal"])
    first = owner.list(DAY, DAY, limit=1)
    assert first["entries"][0]["owner_name"] == "Unassigned"
    assert first["next_offset"] is None
    assert owner.list(DAY, DAY, offset=1)["entries"] == []
    MeetingService(session, seeded["principal"]).index(
        IndexInput(meeting_id="weekly", transcript="Action: replace source", expected_version=meeting.version)
    )
    session.commit()
    assert owner.list(DAY, DAY)["entries"] == []


def test_calendar_http_bounds_and_literal_meeting_search(client, session, seeded, auth):
    item = reviewed(session, seeded)
    path = f"/api/workspaces/{seeded['workspace'].id}"
    response = client.get(
        path + "/calendar", params={"start": DAY.isoformat(), "end": DAY.isoformat()}, headers=auth
    )
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["entries"][0]["item_id"] == item["id"]
    for params in (
        {"start": "2026-01-01", "end": "2026-12-31"},
        {"start": "2026-10-06", "end": "2026-10-05"},
        {"start": "bad", "end": "2026-10-05"},
    ):
        assert client.get(path + "/calendar", params=params, headers=auth).status_code == 422
    assert client.get(path + "/meetings?q=%25", headers=auth).json()["meetings"] == []
    meetings = client.get(path + "/meetings?q=week", headers=auth).json()["meetings"]
    assert len(meetings) == 1 and meetings[0]["created_at"]
    assert (
        client.get(
            f"/api/workspaces/{seeded['isolated'].id}/calendar",
            params={"start": DAY.isoformat(), "end": DAY.isoformat()},
            headers=auth,
        ).status_code
        == 404
    )
