"""Run a live local inference check using synthetic meeting evidence."""

import asyncio
import json
from uuid import uuid4

from app.services.extraction import ExtractionService
from app.settings import settings


async def verify():
    if not settings.ollama_model:
        raise ValueError("Configure OLLAMA_MODEL and a local OLLAMA_URL first")
    lines = [
        ("Alex", "Alex: Action: Review the synthetic close checklist by Friday."),
        ("Morgan", "Morgan: Decision: Require a reviewer before publication."),
        ("Taylor", "Taylor: Blocker: The sample invoice has no confirmed approver."),
    ]
    records = [
        {"id": str(uuid4()), "i": i, "speaker": speaker, "text": text}
        for i, (speaker, text) in enumerate(lines)
    ]
    result = await ExtractionService(None).generate_records(records)
    report = {
        "model": settings.ollama_model,
        "mode": result["mode"],
        "count": len(result["tasks"]),
        "kinds": [task["kind"] for task in result["tasks"]],
        "coverage": result["coverage"],
        "timings": result["timings"],
    }
    print(json.dumps(report, indent=2))
    if result["mode"] not in {"ollama", "mixed"} or {task["kind"] for task in result["tasks"]} != {
        "action",
        "decision",
        "blocker",
    }:
        raise ValueError("Live model check used fallback or produced no accepted outcomes")


if __name__ == "__main__":
    asyncio.run(verify())
