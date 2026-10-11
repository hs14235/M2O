import json

import pytest

from scripts.evaluate_extraction import (
    CASES_PATH,
    KINDS,
    evaluate,
    main,
    match_outcomes,
    ollama_unavailable_reason,
    prf,
    render_markdown,
    similarity,
    tokens,
)


def test_tokens_drop_stopwords_and_keep_negations():
    assert tokens("We will NOT ship the beta") == {"not", "ship", "beta"}
    assert tokens("limits haven't been raised") == {"limits", "not", "raised"}
    assert similarity("ship the beta", "not ship the beta") < 1.0


def test_perfect_match():
    gold = [{"kind": "action", "key": "add regression test stale approvals"}]
    predicted = [{"kind": "action", "title": "add a regression test for stale approvals"}]
    pairs, missed, extra = match_outcomes(gold, predicted)
    assert len(pairs) == 1 and pairs[0][2] == 1.0
    assert missed == [] and extra == []
    assert prf(len(pairs), len(predicted), len(gold))["f1"] == 1.0


def test_partial_match_uses_threshold():
    gold = [{"kind": "risk", "key": "vendor sdk upgrade break older android clients"}]
    predicted = [{"kind": "risk", "title": "vendor sdk upgrade risk"}]
    score = similarity(gold[0]["key"], predicted[0]["title"])
    assert 0 < score < 0.5
    assert match_outcomes(gold, predicted, threshold=0.5)[0] == []
    assert len(match_outcomes(gold, predicted, threshold=0.3)[0]) == 1


def test_partial_set_scores_precision_and_recall():
    gold = [
        {"kind": "action", "key": "draft api deprecation notice"},
        {"kind": "decision", "key": "use postgresql source of truth"},
    ]
    predicted = [
        {"kind": "action", "title": "Draft the API deprecation notice"},
        {"kind": "blocker", "title": "Staging OAuth app not approved"},
        {"kind": "action", "title": "Love the cake photos"},
    ]
    pairs, missed, extra = match_outcomes(gold, predicted)
    assert [pair[0]["key"] for pair in pairs] == ["draft api deprecation notice"]
    assert missed == [gold[1]] and len(extra) == 2
    metrics = prf(len(pairs), len(predicted), len(gold))
    assert metrics["precision"] == pytest.approx(1 / 3, abs=1e-4)
    assert metrics["recall"] == 0.5


def test_kind_mismatch_is_not_a_match():
    gold = [{"kind": "decision", "key": "keep v1 endpoint alive until march cutover"}]
    predicted = [{"kind": "action", "title": "keep the v1 endpoint alive until the March cutover"}]
    pairs, missed, extra = match_outcomes(gold, predicted)
    assert pairs == [] and missed == gold and extra == predicted


def test_each_prediction_matches_at_most_one_gold_outcome():
    gold = [
        {"kind": "action", "key": "update incident runbook"},
        {"kind": "action", "key": "update incident runbook"},
    ]
    predicted = [{"kind": "action", "title": "Update the incident runbook"}]
    pairs, missed, extra = match_outcomes(gold, predicted)
    assert len(pairs) == 1 and len(missed) == 1 and extra == []


def test_empty_sets():
    assert match_outcomes([], []) == ([], [], [])
    assert prf(0, 0, 0) == {"tp": 0, "predicted": 0, "gold": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert prf(0, 2, 0)["precision"] == 0.0 and prf(0, 2, 0)["recall"] == 0.0
    assert prf(0, 0, 3)["precision"] == 0.0 and prf(0, 0, 3)["recall"] == 0.0


def test_cases_are_synthetic_and_well_formed():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert 12 <= len(cases) <= 20
    assert {case["department"] for case in cases} == {"Engineering", "People Operations", "Finance"}
    assert len({case["id"] for case in cases}) == len(cases)
    assert any(not case["expected"] for case in cases)
    for case in cases:
        for item in case["expected"]:
            assert item["kind"] in KINDS and tokens(item["key"])


def test_rules_evaluation_runs_deterministically_over_cases():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    first = evaluate(cases, mode="rules")
    second = evaluate(cases, mode="rules")
    assert first["result_modes"] == {"ollama": 0, "mixed": 0, "rules": len(cases)}
    for metrics in [first["overall"], *first["per_kind"].values(), *first["per_case"]]:
        for name in ("precision", "recall", "f1"):
            assert 0.0 <= metrics[name] <= 1.0
    assert first["overall"]["gold"] == sum(len(case["expected"]) for case in cases)
    keys = ("overall", "per_kind", "owner_accuracy", "misses", "false_positives")
    assert {key: first[key] for key in keys} == {key: second[key] for key in keys}
    assert "| **overall** |" in render_markdown(first)


def test_ollama_mode_skips_without_a_local_model(capsys):
    assert ollama_unavailable_reason("http://127.0.0.1:11434", "").startswith("No model configured")
    assert "non-loopback" in ollama_unavailable_reason("https://inference.example.com", "some-model")
    assert main(["--mode", "ollama", "--markdown"]) == 0
    captured = capsys.readouterr()
    assert "Skipped:" in captured.out and "skipped" in captured.err
