"""Score outcome extraction against gold-labelled synthetic transcripts.

The evaluation calls the same code path the worker uses for extraction
(``chunking.to_chunk_records`` followed by ``ExtractionService.generate_records``)
without a database, provider writes or network access in ``rules`` mode.

``--mode ollama`` uses the configured local Ollama server and model (``OLLAMA_URL`` and
``OLLAMA_MODEL``, or ``--model``). It refuses non-loopback URLs, never pulls models and
exits with a clear "skipped" report when the server or model is unavailable.

Matching rule: a predicted outcome matches a gold outcome when the kinds are equal and the
Jaccard similarity of their normalized token sets (see ``tokens``) is at least the threshold
(default ``0.5``). Each gold and predicted outcome is used at most once; candidate pairs are
assigned greedily from the highest similarity down.
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

CASES_PATH = Path(__file__).parents[1] / "evals" / "extraction_cases.json"
KINDS = ("action", "decision", "blocker", "follow_up", "risk")
DEFAULT_THRESHOLD = 0.5
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
STOPWORDS = frozenset(
    "a an the to for of on in at by with and or is are was be been being will would shall "
    "we i you he she they it its this that these those our your their us me my from into "
    "as so then also please has have had do does did ll s re ve d".split()
)
CONTRACTIONS = {"won't": "will not", "can't": "can not", "cannot": "can not", "n't": " not"}


def tokens(text: str) -> set[str]:
    """Lowercase, expand negating contractions, split on non-alphanumerics, drop stopwords.

    Negation words ("not", "no", "never") are intentionally kept so "ship the beta" and
    "not ship the beta" do not score as identical.
    """
    value = text.casefold().replace("’", "'")
    for source, target in CONTRACTIONS.items():
        value = value.replace(source, target)
    return {word for word in re.findall(r"[a-z0-9]+", value) if word not in STOPWORDS}


def similarity(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def match_outcomes(gold: list[dict], predicted: list[dict], threshold: float = DEFAULT_THRESHOLD):
    """Return ``(pairs, missed, false_positives)``.

    ``gold`` items carry ``kind`` and ``key``; ``predicted`` items carry ``kind`` and ``title``.
    ``pairs`` is a list of ``(gold_item, predicted_item, score)``.
    """
    candidates = []
    for gi, expected in enumerate(gold):
        for pi, actual in enumerate(predicted):
            if expected["kind"] != actual["kind"]:
                continue
            score = similarity(expected["key"], actual.get("title") or actual.get("body") or "")
            if score >= threshold:
                candidates.append((score, gi, pi))
    candidates.sort(key=lambda value: (-value[0], value[1], value[2]))
    used_gold, used_pred, pairs = set(), set(), []
    for score, gi, pi in candidates:
        if gi in used_gold or pi in used_pred:
            continue
        used_gold.add(gi)
        used_pred.add(pi)
        pairs.append((gold[gi], predicted[pi], score))
    missed = [item for i, item in enumerate(gold) if i not in used_gold]
    false_positives = [item for i, item in enumerate(predicted) if i not in used_pred]
    return pairs, missed, false_positives


def prf(tp: int, predicted: int, gold: int) -> dict:
    """Precision/recall/F1 with an explicit empty-set convention.

    With no predictions, precision is 1.0 when there is also no gold outcome, else 0.0.
    With no gold outcomes, recall is 1.0 when there is also no prediction, else 0.0.
    """
    precision = tp / predicted if predicted else (1.0 if gold == 0 else 0.0)
    recall = tp / gold if gold else (1.0 if predicted == 0 else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "predicted": predicted,
        "gold": gold,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def case_records(case: dict) -> list[dict]:
    from app.chunking import to_chunk_records

    records = to_chunk_records(case["transcript"])
    return [
        {
            "id": str(uuid5(NAMESPACE_URL, f"m2o-extraction-eval:{case['id']}:{record['i']}")),
            "i": record["i"],
            "text": record["text"],
            "speaker": record["speaker"],
        }
        for record in records
    ]


async def predict(case: dict, *, use_model: bool) -> dict:
    from app.services.extraction import ExtractionService

    return await ExtractionService(None).generate_records(case_records(case), use_model=use_model)


def score_cases(cases: list[dict], results: dict[str, dict], threshold: float) -> dict:
    totals = {kind: {"tp": 0, "predicted": 0, "gold": 0} for kind in KINDS}
    owner_checked = owner_correct = 0
    per_case, misses, false_positives = [], [], []
    for case in cases:
        predicted = results[case["id"]]["tasks"]
        pairs, missed, extra = match_outcomes(case["expected"], predicted, threshold)
        for kind in KINDS:
            totals[kind]["gold"] += sum(item["kind"] == kind for item in case["expected"])
            totals[kind]["predicted"] += sum(item["kind"] == kind for item in predicted)
            totals[kind]["tp"] += sum(expected["kind"] == kind for expected, _, _ in pairs)
        for expected, actual, _ in pairs:
            if expected.get("owner"):
                owner_checked += 1
                owner_correct += (actual.get("assignee_hint") or "").casefold() == expected[
                    "owner"
                ].casefold()
        misses += [{"case": case["id"], "kind": item["kind"], "key": item["key"]} for item in missed]
        false_positives += [
            {
                "case": case["id"],
                "kind": item["kind"],
                "title": item["title"],
                "owner": item.get("assignee_hint"),
            }
            for item in extra
        ]
        per_case.append(
            {
                "case": case["id"],
                "department": case["department"],
                "mode": results[case["id"]]["mode"],
                "warnings": results[case["id"]]["coverage"]["warnings"],
                **prf(len(pairs), len(predicted), len(case["expected"])),
            }
        )
    per_kind = {kind: prf(**totals[kind]) for kind in KINDS}
    overall = prf(
        sum(value["tp"] for value in totals.values()),
        sum(value["predicted"] for value in totals.values()),
        sum(value["gold"] for value in totals.values()),
    )
    return {
        "overall": overall,
        "per_kind": per_kind,
        "owner_accuracy": {
            "correct": owner_correct,
            "checked": owner_checked,
            "accuracy": round(owner_correct / owner_checked, 4) if owner_checked else None,
        },
        "per_case": per_case,
        "misses": misses,
        "false_positives": false_positives,
    }


def ollama_unavailable_reason(url: str, model: str) -> str | None:
    """Return why local Ollama cannot be used, or ``None`` when the model is present."""
    import httpx

    if not model:
        return "No model configured: set OLLAMA_MODEL or pass --model."
    if urlsplit(url).hostname not in LOOPBACK_HOSTS:
        return f"Refusing non-loopback Ollama URL {url!r}; only local inference is evaluated."
    try:
        with httpx.Client(timeout=5, trust_env=False) as client:
            response = client.get(f"{url}/api/tags")
            response.raise_for_status()
            names = {item.get("name") for item in response.json().get("models", [])}
    except (httpx.HTTPError, ValueError) as error:
        return f"Ollama is not reachable at {url} ({type(error).__name__})."
    if model not in names and f"{model}:latest" not in names:
        available = ", ".join(sorted(name for name in names if name)) or "none"
        return f"Model {model!r} is not installed locally (available: {available}). Not pulling it."
    return None


def evaluate(
    cases: list[dict], *, mode: str = "rules", threshold: float = DEFAULT_THRESHOLD, model: str = ""
) -> dict:
    from app.settings import settings

    report = {
        "mode": mode,
        "date": datetime.now(UTC).date().isoformat(),
        "threshold": threshold,
        "cases": len(cases),
        "departments": sorted({case["department"] for case in cases}),
    }
    if mode == "ollama":
        if model:
            settings.ollama_model = model
        report["model"] = settings.ollama_model or None
        report["ollama_url"] = settings.ollama_url
        reason = ollama_unavailable_reason(settings.ollama_url, settings.ollama_model)
        if reason:
            return {**report, "skipped": True, "reason": reason}

    async def run_all():
        return {case["id"]: await predict(case, use_model=mode == "ollama") for case in cases}

    results = asyncio.run(run_all())
    report.update(score_cases(cases, results, threshold))
    report["result_modes"] = {
        name: sum(row["mode"] == name for row in report["per_case"]) for name in ("ollama", "mixed", "rules")
    }
    report["elapsed_ms"] = round(sum(value["timings"]["total_ms"] for value in results.values()), 2)
    return report


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def render_markdown(report: dict) -> str:
    header = f"### Extraction evaluation: {report['mode']} mode ({report['date']})"
    if report.get("skipped"):
        return f"{header}\n\nSkipped: {report['reason']}\n"
    lines = [
        header,
        "",
        f"Cases: {report['cases']} ({', '.join(report['departments'])}); "
        f"Jaccard threshold: {report['threshold']}"
        + (f"; model: `{report['model']}`" if report.get("model") else "")
        + f"; result modes: {report['result_modes']}",
        "",
        "| Kind | Gold | Predicted | TP | Precision | Recall | F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    rows = [*report["per_kind"].items(), ("**overall**", report["overall"])]
    for kind, value in rows:
        lines.append(
            f"| {kind} | {value['gold']} | {value['predicted']} | {value['tp']} | "
            f"{_fmt(value['precision'])} | {_fmt(value['recall'])} | {_fmt(value['f1'])} |"
        )
    owner = report["owner_accuracy"]
    if owner["checked"]:
        lines += [
            "",
            f"Owner accuracy on matched outcomes with a gold owner: {owner['correct']}/{owner['checked']}",
        ]
    lines += ["", f"Misses ({len(report['misses'])}):", ""]
    lines += [f"- `{row['case']}` {row['kind']}: {row['key']}" for row in report["misses"]] or ["- none"]
    lines += ["", f"False positives ({len(report['false_positives'])}):", ""]
    lines += [
        f"- `{row['case']}` {row['kind']}: {row['title']} (owner: {row['owner']})"
        for row in report["false_positives"]
    ] or ["- none"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("rules", "ollama"), default="rules")
    parser.add_argument("--model", default="", help="Local Ollama model name (overrides OLLAMA_MODEL)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--markdown", action="store_true", help="Print a Markdown summary instead of JSON")
    args = parser.parse_args(argv)
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    report = evaluate(cases, mode=args.mode, threshold=args.threshold, model=args.model)
    if report.get("skipped"):
        print(f"Ollama evaluation skipped: {report['reason']}", file=sys.stderr)
    print(render_markdown(report) if args.markdown else json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
