import asyncio
from uuid import uuid4

import httpx
from test_meeting_lifecycle import indexed

from app.models import Job
from app.services.extraction import ExtractionService
from app.settings import settings
from app.tasks import extract_tasks_ollama
from app.worker import claim, run_once


def mock_model(monkeypatch, response):
    original = httpx.AsyncClient

    def respond(request):
        import json

        payload = json.loads(request.content)
        assert payload["stream"] is False
        assert payload["format"]["properties"]["tasks"]
        assert "untrusted evidence" in payload["messages"][0]["content"]
        return httpx.Response(200, json=response)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond))
    )
    monkeypatch.setattr(settings, "ollama_model", "synthetic-local-model")


def test_ollama_supported_citations_only(monkeypatch):
    source, invented = str(uuid4()), str(uuid4())
    mock_model(
        monkeypatch,
        {
            "message": {
                "content": '{"tasks":[{"kind":"action","title":"Unsupported","source_ids":["'
                + invented
                + '"]}]}'
            }
        },
    )
    tasks, warning = asyncio.run(extract_tasks_ollama([{"id": source, "text": "Status only"}]))
    assert tasks == [] and warning == "unsupported_evidence_rejected"


def test_ollama_valid_structured_output(monkeypatch):
    source = str(uuid4())
    mock_model(
        monkeypatch,
        {
            "message": {
                "content": '{"tasks":[{"kind":"decision","title":"Use local inference","source_ids":["'
                + source
                + '"]}]}'
            }
        },
    )
    tasks, warning = asyncio.run(
        extract_tasks_ollama([{"id": source, "text": "Decision: Use local inference"}])
    )
    assert tasks[0]["source_ids"] == [source] and warning is None


def test_truncated_output_falls_back(monkeypatch):
    mock_model(monkeypatch, {"done_reason": "length", "message": {"content": "{}"}})
    result = asyncio.run(
        ExtractionService(None).generate_records(
            [{"id": str(uuid4()), "i": 0, "text": "Action: Alex to test fallback.", "speaker": None}]
        )
    )
    assert result["mode"] == "rules" and len(result["tasks"]) == 1
    assert result["coverage"]["warnings"] == ["model_output_truncated"]


def test_explicit_outcomes_survive_model_omissions_and_misclassification(monkeypatch):
    source, decision = str(uuid4()), str(uuid4())
    mock_model(
        monkeypatch,
        {
            "message": {
                "content": '{"tasks":[{"kind":"action","title":"Model paraphrase","source_ids":["'
                + source
                + '"]}]}'
            }
        },
    )
    result = asyncio.run(
        ExtractionService(None).generate_records(
            [
                {"id": source, "i": 0, "text": "Blocker: Synthetic access is pending.", "speaker": None},
                {"id": decision, "i": 1, "text": "Decision: Preserve literal evidence.", "speaker": None},
            ]
        )
    )
    assert result["mode"] == "mixed"
    assert {task["kind"] for task in result["tasks"]} == {"blocker", "decision"}
    assert all(task["title"] != "Model paraphrase" for task in result["tasks"])


def test_extraction_covers_tail_of_long_meeting():
    records = [
        {"id": str(uuid4()), "i": i, "text": "Status: " + "Discussion " * 50, "speaker": None}
        for i in range(50)
    ]
    records.append(
        {"id": str(uuid4()), "i": 50, "text": "Action: Alex to review the final control.", "speaker": "Alex"}
    )
    result = asyncio.run(ExtractionService(None).generate_records(records))
    assert result["coverage"]["processed_chunks"] == 51
    assert result["tasks"][0]["source_ids"] == [records[-1]["id"]]


def test_revoked_worker_authorization_fails_safely(session, seeded):
    indexed(session, seeded)
    from app.models import Membership
    from app.services.meetings import MeetingService

    job = MeetingService(session, seeded["principal"]).enqueue_extraction("weekly")
    session.get(Membership, (seeded["workspace"].id, seeded["user"].id)).role = "viewer"
    session.commit()
    assert asyncio.run(run_once())
    session.expire_all()
    assert session.get(Job, job["job_id"]).state == "failed"
    assert session.get(Job, job["job_id"]).error_code == "service_403"


def test_claim_does_not_take_an_active_lease(session, seeded):
    from app.schemas import IndexInput
    from app.services.meetings import MeetingService

    MeetingService(session, seeded["principal"]).index(
        IndexInput(meeting_id="lease", transcript="Action: Test lease")
    )
    session.commit()
    first = claim()
    assert first and claim() is None
