# Synthetic forward-test input

Use only for behavioral evaluation of this skill, not as product data or an API specification.

## Request

Design a vivid, lunar workspace calendar for the records below. The user wants reviewed meeting outcomes to become tangible, clickable day points, with a simpler header/sidebar and Google Meet source capture. Give a concise implementation plan and verification plan against the available data; do not change files or call providers. The application already uses React with separate URL-addressable pages, server sessions and role checks. It has not adopted SSR.

## Raw records

```json
{
  "actor": {"id":"user-a","role":"editor","is_visitor":false},
  "meetings": [
    {"id":"meeting-a","title":"Release readiness","current_revision":3,"created_at":"2026-10-05T09:00:00Z"},
    {"id":"meeting-b","title":"Release readiness","current_revision":1,"created_at":"2026-10-05T10:00:00Z"}
  ],
  "outcomes": [
    {"id":"a1","meeting_id":"meeting-a","revision":3,"kind":"decision","status":"approved","due_date":null,"due_hint":"by Friday","owner_name":"Alex","owner_confirmed":false},
    {"id":"a2","meeting_id":"meeting-a","revision":3,"kind":"risk","status":"approved","due_date":"2026-10-08","due_hint":null,"owner_name":"Morgan","owner_confirmed":true,"personal_plan":{"user_id":"user-a","planned_on":"2026-10-06","state":"done"}},
    {"id":"a3","meeting_id":"meeting-a","revision":2,"kind":"action","status":"approved","due_date":"2026-10-07","owner_name":"Alex","owner_confirmed":true},
    {"id":"b1","meeting_id":"meeting-b","revision":1,"kind":"action","status":"draft","due_date":"2026-10-09","owner_name":null,"owner_confirmed":false}
  ],
  "google": {"configured":false,"state":"disconnected","can_import":false,"transcription_required":true},
  "latest_conference": {"id":"conference-latest","transcripts":[]},
  "previous_conference": {"id":"conference-previous","transcripts":["transcript-old"]}
}
```

There is no Google Cloud OAuth app or generated transcript for the latest meeting. No account change, file upload, publication or deployment has been authorized. The native public artwork is present in the checkout; no container serving result has been collected.
