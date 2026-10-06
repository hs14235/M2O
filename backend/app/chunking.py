import re
from typing import Any

CHUNKING_VERSION = "bounded-turns-v3"
SPEAKER_PATTERN = re.compile(
    r"^(?:\[(?P<timestamp>\d{1,2}:\d{2}(?::\d{2})?)\]\s*)?(?P<speaker>[^:\[\]\n]{1,120}):\s+"
)
OUTCOME_LABELS = {
    "action",
    "todo",
    "task",
    "ai",
    "decision",
    "blocker",
    "risk",
    "status",
    "owner",
    "follow-up",
    "follow up",
}


def _pieces(text: str, maximum: int) -> list[str]:
    pieces, current, size = [], [], 0
    for character in text:
        amount = len(character.encode("utf-8"))
        if size + amount > maximum:
            pieces.append("".join(current))
            current, size = [], 0
        current.append(character)
        size += amount
    if current:
        pieces.append("".join(current))
    return pieces


def to_chunk_records(text: str, approx_tokens: int = 180, overlap_lines: int = 1) -> list[dict[str, Any]]:
    maximum = min(1200, max(128, approx_tokens * 4))
    records, pending = [], []

    def append(lines, speaker=None, timestamp=None):
        records.append(
            {
                "i": len(records),
                "text": "\n".join(line for _, line in lines),
                "speaker": speaker,
                "timestamp": timestamp,
                "start_line": lines[0][0],
            }
        )

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        match = SPEAKER_PATTERN.match(line)
        speaker = match.group("speaker").strip() if match else None
        if speaker and speaker.casefold() in OUTCOME_LABELS:
            speaker = None
        if speaker and match:
            if pending:
                append(pending)
                pending = []
            for piece in _pieces(line, maximum):
                append([(number, piece)], speaker, match.group("timestamp"))
            continue
        for piece in _pieces(line, maximum):
            if pending and (
                sum(len(value.encode("utf-8")) + 1 for _, value in pending) + len(piece.encode("utf-8"))
                > maximum
                or sum(len(value.split()) for _, value in pending) >= approx_tokens
            ):
                append(pending)
                overlap = pending[-overlap_lines:] if overlap_lines else []
                pending = (
                    overlap
                    if sum(len(value.encode("utf-8")) + 1 for _, value in overlap)
                    + len(piece.encode("utf-8"))
                    <= maximum
                    else []
                )
            pending.append((number, piece))
    if pending:
        append(pending)
    return records


def to_chunks(text: str, approx_tokens: int = 180) -> list[str]:
    return [record["text"] for record in to_chunk_records(text, approx_tokens)]
