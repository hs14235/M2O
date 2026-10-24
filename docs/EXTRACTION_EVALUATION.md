# Extraction evaluation

This harness measures how well M2O turns a transcript into outcomes (action, decision, blocker, follow-up, risk) against gold labels. It exists so any change to extraction, including a new local model default, is judged on M2O's own synthetic cases rather than general benchmarks (see `AGENTS.md`).

## How to run

From `backend`, using the configured virtual environment:

```
python -m scripts.evaluate_extraction                 # rules mode, JSON report
python -m scripts.evaluate_extraction --markdown      # rules mode, Markdown tables
python -m scripts.evaluate_extraction --mode ollama --markdown               # uses OLLAMA_URL / OLLAMA_MODEL
python -m scripts.evaluate_extraction --mode ollama --model <local-model> --markdown
python -m scripts.evaluate_extraction --threshold 0.4 --markdown            # matching sensitivity
```

Rules mode is deterministic and offline: no database, network, model, or provider calls. Ollama mode only talks to a loopback Ollama URL (`127.0.0.1`, `localhost`, `::1`). It checks `/api/tags` first and never pulls a model. If the server is unreachable, no model is configured, or the model is not installed, it prints `Skipped: <reason>` and exits 0 without reporting any numbers. Unit tests are in `backend/tests/test_extraction_eval.py`.

## Method

- **Code under test.** Each transcript is chunked with `app.chunking.to_chunk_records`, given deterministic UUIDv5 chunk ids, and passed to `ExtractionService(None).generate_records(records, use_model=...)`. That is the call the worker makes for extract jobs, so the batching, explicit-label preservation, de-duplication and `max_outcomes` cap all apply. Rules mode passes `use_model=False`; Ollama mode passes `use_model=True`. In Ollama mode the service still re-applies the rules extractor to chunks with explicit labels (result mode `mixed`), and the report shows each case's result mode and warnings so a silent fallback to rules is visible.
- **Matching.** A predicted outcome matches a gold outcome when the **kinds are equal** and the **Jaccard similarity** of their normalized token sets is **at least 0.5** (the default threshold). The prediction's `title` is compared with the gold `key`. Normalization works in four steps: casefold; expand `won't`, `can't`, `cannot` and `n't` to `not` forms; split on non-alphanumerics; drop a small stopword list. Negation words are kept. Matching is one-to-one: candidate pairs are assigned greedily from the highest similarity down.
- **Metrics.** Precision = TP / predicted and recall = TP / gold, computed per kind and overall (micro-averaged across all cases), plus F1. With no predictions, precision is 1.0 only if there is also no gold outcome. With no gold outcomes, recall is 1.0 only if there is also no prediction. **Owner accuracy** is the share of matched pairs with a gold `owner` whose `assignee_hint` equals it (case-insensitive). The report also lists every miss and false positive.

## Dataset

`backend/evals/extraction_cases.json` holds 17 synthetic transcripts with 52 gold outcomes: 19 action, 11 decision, 7 blocker, 7 follow-up and 8 risk. The cases cover Engineering (8), People Operations (4) and Finance (5). All names and facts are invented. The four demo fixtures from `app/demo_fixtures.py` are included unchanged. The other cases add these hard cases:

- implicit actions with no labels, with and without `[hh:mm]` timestamps (`eng-implicit-*`, `fin-budget-implicit`, `hr-policy-implicit`)
- decisions phrased as "we agreed to…" or "the decision is…" next to real actions (`eng-decision-vs-action`)
- risks phrased as worries ("I'm worried…", "My concern is…", "There's a chance…") and blockers or follow-ups without labels
- negations ("We will NOT ship", "We are not renewing", "Do not approve", "won't need") and completed work (`- [x]`, "Already completed")
- relative dates (tomorrow, next Tuesday, EOW, first of next month)
- multiple speakers assigning work to each other, an `owner:` field, an open checkbox, and labels in the middle of a line
- two conversations with no outcomes, one containing a distractor ("Taylor will love the cake photos")
- an instruction embedded in the transcript that must not be followed

Gold keys are short normalized phrases. `owner` is labelled only where the transcript names one explicitly.

## Results

Measured on **2026-10-11** on Windows 11 with Python 3.13.1 (the project `.venv`), with `APP_ENVIRONMENT=test PUBLIC_DEMO_MODE=true EMBED_PROVIDER=hash`. The extraction code is from `origin/main` at the time the branch `feat/extraction-eval` was created.

### Rules mode (threshold 0.5)

| Kind        | Gold | Predicted |  TP | Precision | Recall |   F1 |
| ----------- | ---: | --------: | --: | --------: | -----: | ---: |
| action      |   19 |        15 |  11 |      0.73 |   0.58 | 0.65 |
| decision    |   11 |         7 |   7 |      1.00 |   0.64 | 0.78 |
| blocker     |    7 |         5 |   5 |      1.00 |   0.71 | 0.83 |
| follow_up   |    7 |         6 |   6 |      1.00 |   0.86 | 0.92 |
| risk        |    8 |         4 |   4 |      1.00 |   0.50 | 0.67 |
| **overall** |   52 |        37 |  33 |      0.89 |   0.63 | 0.74 |

Owner accuracy on matched outcomes with a gold owner: 7/10. All 17 cases ran in rules mode. Total in-process extraction time was about 2.6 ms.

**Threshold sensitivity.** At 0.6 the results are identical. At 0.4, one more action matches (`Reconcile the Q3 vendor accruals, owner: Riley, due Oct 31`). That raises overall precision, recall and F1 to 0.92, 0.65 and 0.76, and owner accuracy to 8/11.

**What the rules extractor misses (19).** It misses every unlabelled decision, risk, blocker and follow-up. It also misses implicit actions phrased as "I'll…", "I can…", "please…", or "X will…" on a line that starts with `Speaker:` and has no timestamp. The rules pattern only strips a speaker prefix when it follows a `[timestamp]`.

**False positives (4).**

- "We agreed to keep the v1 endpoint…" was extracted as an action with owner "We agreed", where the gold label is a decision.
- "Taylor will love the cake photos" was extracted as an action.
- `Action: We won't need to migrate the legacy logs after all` was extracted as an action. The negation sits in the owner phrase, which the owner pattern splits off before the negation check runs on the body, so the check never sees it. This was a real bug in `app/tasks.py`, fixed on 2026-10-14 (see below).
- The `owner:`/`due` line above, which the matcher missed at 0.5 because the title includes the owner and due clauses. This is a matcher artifact, not an extraction error.

Owner errors include "Sure. And Sam" and "Got it. Riley". These come from the 1–3 word owner capture in `PERSON_PATTERN`.

### Rules extractor fixes (2026-10-14)

The baseline above guided four changes to `app/tasks.py`, each covered by a unit test in `tests/test_rules.py`:

1. **Negation is checked before the owner is split off**, so `Action: We won't need to…` is dropped.
2. **Owners must look like names**: capitalized words that are not pronouns or words like "someone" and "nothing". "We agreed", "We won't need" and "Someone needs" no longer become owners.
3. **Speaker prefixes are stripped with or without a timestamp**, leading filler ("Okay, so", "Sure. And", "Then") is removed, and each sentence is checked on its own. First-person commitments ("I'll…", "I can also…") are assigned to the speaker, and "Name, please…" to the named person. A commitment whose only object is a pronoun ("I'll have it done") is skipped, since it points at an earlier line.
4. **`owner:` and `due` fields are removed from the title**; they are still read into the owner and due hints.

| Rules mode, threshold 0.5              | Precision |   Recall |       F1 | Owner accuracy |
| -------------------------------------- | --------: | -------: | -------: | -------------: |
| 17 development cases, before           |      0.89 |     0.63 |     0.74 |           7/10 |
| 17 development cases, after            |  **0.98** | **0.77** | **0.86** |      **17/17** |
| 3 held-out cases (10 outcomes), before |      0.83 |     0.50 |     0.62 |            0/2 |
| 3 held-out cases (10 outcomes), after  |  **0.90** | **0.90** | **0.90** |        **6/6** |

**Read the development numbers with care.** The fixes were written while looking at those 17 cases, so their improvement is optimistic. The three held-out cases in `backend/evals/extraction_heldout.json` were written after the change and never tuned on, but by the same author who knew the new rules, so they are a sanity check rather than an independent test. Run them with `--cases evals/extraction_heldout.json`. Before the next extractor change, write new held-out cases first.

What still fails: every unlabelled decision, risk, blocker and follow-up (recognizing those needs a model, not more patterns), "Taylor will love the cake photos" (a name followed by "will" is not always a commitment), and "Someone should ask legal… / Yes, I'll handle it", where the owner is in a later line.

### Ollama mode: Qwen2.5 1.5B (2026-10-23)

Measured on Hamza's Windows 11 laptop, CPU only, against `qwen2.5:1.5b` in the Compose `ollama` service (Ollama 0.35.0, port 11435), with `--mode ollama --model qwen2.5:1.5b --markdown`. Rules mode was rerun on the same day for comparison.

| Cases                              | Rules: P / R / F1      | Qwen2.5 1.5B: P / R / F1 | Qwen wall time |
| ---------------------------------- | ---------------------- | ------------------------ | -------------- |
| 17 development cases (52 outcomes) | 0.98 / 0.77 / **0.86** | 0.70 / 0.75 / 0.72       | 300 s          |
| 3 held-out cases (10 outcomes)     | 0.90 / 0.90 / **0.90** | 0.38 / 0.30 / 0.33       | 63 s           |

On the held-out set, `result_modes` were 1 `ollama` and 2 `mixed`, the latter with the warning `explicit_outcomes_preserved`, meaning labelled lines were kept by the rules. A repeat run scored F1 0.32: the model's output varies slightly between runs.

**The 1.5B model is worse than the rules on M2O's own cases, so the default stays rules.** Its main error is the kind of outcome rather than the outcome itself. On the held-out engineering case it returned "Update the changelog", "Run smoke tests on staging" and "Check alert thresholds" as decisions, when all three are actions, and it dropped actions the rules find.

The recorded candidates are `qwen3:4b` (Q4_K_M, about 2.5 GB) and `qwen3.5:4b` (about 3.4 GB); see `docs/M2O_IMPLEMENTATION_CONTRACT.md`. Score either the same way before changing the default.

## Limitations

- **Small synthetic set.** 52 gold outcomes is too few for fine-grained comparisons: one outcome moves a per-kind score by 5–14 points. The transcripts are short, clean and English-only, so they do not represent real meetings, ASR errors or long contexts.
- **Phrase matching is lexical.** Token Jaccard penalizes long but correct titles (see the `owner:` example) and can reward wrong titles that share vocabulary. It cannot judge paraphrases, which matters more for model output than for the rules extractor. Use `--threshold` to check sensitivity before reading small differences.
- **Single annotator.** The gold labels were written by one annotator (the harness author). Some labels are judgement calls: "I can also look at the flaky checkout test" is labelled as an action, and "keep the v1 endpoint alive" as a decision.
- **Partial scoring.** Only `kind`, the title phrase and the owner are scored. Due hints, evidence citations (`source_ids`), confidence and labels are not.
- **Rules results are a baseline, not a quality claim.** The labelled demo fixtures score perfectly, but recall on unlabelled speech is low. A model run must show improvement on this set, without new false positives on the negation, distractor and injection cases, before it can justify a change to the default.
