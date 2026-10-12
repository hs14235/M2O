"""Measure local transcription accuracy (word error rate) and speed on a known recording.

Usage, from backend/ with requirements-ai.txt installed:
    python -m scripts.evaluate_transcription AUDIO REFERENCE.txt [--model small] [--compute int8]

WER = (substitutions + deletions + insertions) / reference words, after lowercasing and
removing punctuation. The real-time factor is processing time divided by audio duration
(below 1.0 means faster than real time). The first run also includes the model download.
"""

import argparse
import re
import time
from pathlib import Path

from app import transcription as speech


def words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]+", " ", text.lower()).split()


def word_error_rate(reference: list[str], hypothesis: list[str]) -> float:
    # Levenshtein distance over words, one row at a time.
    previous = list(range(len(hypothesis) + 1))
    for i, ref_word in enumerate(reference, 1):
        current = [i]
        for j, hyp_word in enumerate(hypothesis, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ref_word != hyp_word)))
        previous = current
    return previous[-1] / max(1, len(reference))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("audio", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--compute", default="int8")
    args = parser.parse_args()
    started = time.perf_counter()
    speech.load_model(args.model, args.compute)
    loaded = time.perf_counter()
    result = speech.transcribe(
        args.audio.read_bytes(), model_name=args.model, compute_type=args.compute, max_seconds=4 * 3600
    )
    finished = time.perf_counter()
    reference = words(args.reference.read_text(encoding="utf-8"))
    hypothesis = words(result.text)
    elapsed = finished - loaded
    print(f"model: {args.model} ({args.compute}), language: {result.language}")
    print(f"audio: {result.duration_seconds:.1f} s; model load: {loaded - started:.1f} s")
    print(f"transcription: {elapsed:.1f} s; real-time factor: {elapsed / result.duration_seconds:.2f}")
    print(f"WER: {word_error_rate(reference, hypothesis):.3f} ({len(reference)} reference words)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
