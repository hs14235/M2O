"""Evaluate lexical retrieval on a synthetic, deterministic corpus without application writes."""

import json
from pathlib import Path
from time import perf_counter

import numpy as np

from app.embeddings import embed_texts_hash

CORPUS = [
    "Action: Alex to finalize the launch checklist deadline by Friday.",
    "Action: Morgan to add retrieval evaluation coverage for meeting context.",
    "Decision: GitHub issue approval policy requires review before publishing.",
    "Blocker: Taylor cannot finish onboarding product review without access.",
]


def main():
    cases = json.loads((Path(__file__).parents[1] / "evals" / "retrieval_cases.json").read_text())
    vectors = np.asarray(embed_texts_hash(CORPUS, "hash"))
    rows, elapsed = [], []
    for case in cases:
        started = perf_counter()
        query = np.asarray(embed_texts_hash([case["query"]], "hash")[0])
        actual = int(np.argmax(vectors @ query))
        elapsed.append((perf_counter() - started) * 1000)
        rows.append(
            {
                "query": case["query"],
                "expected": case["expected_chunk"],
                "actual": actual,
                "hit": actual == case["expected_chunk"],
            }
        )
    print(
        json.dumps(
            {
                "strategy": "lexical-hash",
                "synthetic_cases": len(rows),
                "recall_at_1": sum(row["hit"] for row in rows) / len(rows),
                "mean_ms": round(sum(elapsed) / len(elapsed), 2),
                "results": rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
