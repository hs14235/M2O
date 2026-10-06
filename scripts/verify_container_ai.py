"""Exercise browser-session API, PostgreSQL, worker and Ollama with synthetic data."""

import json
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    account = json.loads((ROOT / ".runtime" / "demo-account.json").read_text())
    with httpx.Client(
        base_url="http://localhost:8080",
        timeout=15,
        trust_env=False,
        headers={"Origin": "http://localhost:8080"},
    ) as client:
        signed = client.post(
            "/api/auth/login", json={"email": account["email"], "password": account["password"]}
        )
        signed.raise_for_status()
        client.headers["X-CSRF-Token"] = signed.json()["csrf_token"]
        capabilities = client.get("/api/me").json()["capabilities"]
        if not capabilities["demo_mode"] or not capabilities["ollama_model"]:
            raise ValueError("This verification requires local demo mode and configured Ollama")
        spaces = client.get("/api/workspaces").json()
        workspace = next(row for row in spaces if row["department"] == "engineering")
        root = "/api/workspaces/" + workspace["id"]
        slug = "local-ai-" + uuid4().hex[:10]

        def poll(job_id):
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                response = client.get(root + "/jobs/" + job_id)
                response.raise_for_status()
                result = response.json()
                if result["state"] == "completed":
                    return result["result"]
                if result["state"] in {"failed", "cancelled"}:
                    raise ValueError("Synthetic job failed: " + str(result["error_code"]))
                time.sleep(1)
            raise TimeoutError("Synthetic worker verification exceeded its time budget")

        indexed = client.post(
            root + "/index",
            json={
                "meeting_id": slug,
                "title": "Synthetic local AI verification",
                "transcript": "Alex: Action: Review the synthetic release checklist by Friday.\nMorgan: Decision: Require review before publication.\nTaylor: Blocker: The sample access request is pending.",
            },
        )
        indexed.raise_for_status()
        poll(indexed.json()["job_id"])
        extracted = client.post(root + "/meetings/" + slug + "/extract")
        extracted.raise_for_status()
        result = poll(extracted.json()["job_id"])
        meeting = client.get(root + "/meetings/" + slug).json()
        kinds = {task["kind"] for task in meeting["tasks"]}
        if result["mode"] not in {"ollama", "mixed"} or kinds != {"action", "decision", "blocker"}:
            raise ValueError("The real worker did not preserve the required outcomes")
        print(
            json.dumps(
                {
                    "meeting_id": slug,
                    "model": capabilities["ollama_model"],
                    "mode": result["mode"],
                    "outcomes": len(meeting["tasks"]),
                    "kinds": sorted(kinds),
                    "coverage": result["coverage"],
                    "timings": result["timings"],
                    "external_writes": 0,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
