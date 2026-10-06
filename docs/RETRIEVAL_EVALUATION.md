# Retrieval evaluation

Run `python -m scripts.evaluate_retrieval` from `backend` using the configured virtual environment.

The evaluation uses four synthetic chunks and four queries in `backend/evals/retrieval_cases.json`. It creates no application records and makes no model or provider requests. The current run on 2026-10-01 reported:

| Metric | Observed value |
| --- | --- |
| Provider | lexical-hash |
| Synthetic cases | 4 |
| Recall@1 | 1.00 (4/4) |
| Mean query/score time in this run | 1.72 ms |

The corpus covers a launch checklist, retrieval tests, publication approval, and an onboarding blocker. Its queries contain obvious vocabulary shared with the expected chunks. This is a deterministic smoke baseline, not evidence of semantic understanding or representative accuracy. Its timing measures a tiny in-process corpus, not HTTP latency or PostgreSQL throughput.

The production application service loads authorized current-revision vectors from PostgreSQL, uses the revision's saved provider/model, and rejects incomplete/malformed vectors. Integration tests verify isolation and retrieval after a new database session. FAISS and ephemeral fallback objects remain standalone compatibility modules; the application does not use them for durable workspace retrieval.

Extraction and retrieval have different responsibilities. Search ranks relevant context for a user's query. Extraction processes every bounded transcript chunk, with explicit coverage, so an action near the end of a long meeting is not excluded simply because it was outside top-k search.

Before a semantic-provider claim, install the optional dependencies, cache the model locally, and evaluate representative synthetic paraphrases, ambiguous names, long meetings, distractors, negations, completed work, multilingual text and retrieval thresholds. That provider was not exercised during this revamp. A larger labeled corpus and outcome-level precision/recall are needed before reporting AI quality beyond these bounded checks.
