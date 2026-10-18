import { prefersMotion } from "../../motion";
import type { Evidence, Outcome } from "../../types";

/*
 * The signature moment: when a live extraction finishes on People, the transcript
 * lines an outcome came from become its draft card (a shared view transition).
 * These helpers map evidence onto lines, pick which lines morph, and remember
 * which meeting revisions have already played it.
 */

// Python splitlines boundaries; U+2028 and U+2029 are built from char codes because
// they cannot appear literally in a JavaScript regular expression.
const lineBreak = new RegExp("\r\n|[\n\r\v\f\x1c-\x1e\x85" + String.fromCharCode(0x2028, 0x2029) + "]");

/** A transcript split the way the backend numbers lines (Python splitlines, 1-based). */
export function transcriptLines(raw: string): string[] {
  return raw.split(lineBreak);
}

/**
 * Line numbers an evidence chunk covers. The backend (app/chunking.py) strips each
 * non-blank line, cuts a long one into pieces, and joins a chunk's pieces with "\n"
 * from start_line on. So each piece is matched where the previous one ended: on the
 * same line while it continues it, otherwise on a following line.
 */
export function evidenceLines(lines: readonly string[], evidence: Evidence): number[] {
  const found: number[] = [];
  let n = Math.max(1, evidence.start_line),
    offset = 0;
  for (const piece of evidence.text.split("\n")) {
    while (n <= lines.length) {
      const line = lines[n - 1].trim();
      // The first piece may be the overlap tail of a long line, so it may start mid-line.
      const at = !piece
        ? -1
        : found.length
          ? line.startsWith(piece, offset)
            ? offset
            : -1
          : line.indexOf(piece);
      if (at >= 0) {
        offset = at;
        break;
      }
      n += 1;
      offset = 0;
    }
    if (n > lines.length) break;
    if (found.at(-1) !== n) found.push(n);
    offset += piece.length;
  }
  return found;
}

/** The view-transition-name shared by an outcome's source line and its draft card. */
export function momentName(id: string): string {
  return "m2o-o-" + id.replace(/[^\w-]/g, "_");
}

/**
 * Pairs outcomes with the on-screen line each one morphs from: every outcome claims
 * its first unclaimed visible evidence line, up to `limit` pairs. Returns line → name,
 * or null when two outcomes would share a name; a duplicate view-transition-name makes
 * the browser abort the whole transition, so the caller then skips it.
 */
export function pairNames(
  outcomes: readonly Outcome[],
  lines: readonly string[],
  visible: ReadonlySet<number>,
  limit = 8,
): Map<number, string> | null {
  const pairs = new Map<number, string>(),
    names = new Set<string>();
  for (const outcome of outcomes) {
    const name = momentName(outcome.id);
    if (names.has(name)) return null;
    names.add(name);
    if (pairs.size >= limit) continue;
    const line = outcome.evidence
      .flatMap((evidence) => evidenceLines(lines, evidence))
      .find((n) => visible.has(n) && !pairs.has(n));
    if (line !== undefined) pairs.set(line, name);
  }
  return pairs;
}

/** Line numbers of the rows ([data-line]) currently visible inside `container` and the viewport. */
export function visibleLines(container: HTMLElement | null): Set<number> {
  const found = new Set<number>();
  if (!container) return found;
  const box = container.getBoundingClientRect(),
    top = Math.max(0, box.top),
    bottom = Math.min(window.innerHeight, box.bottom);
  for (const row of container.querySelectorAll<HTMLElement>("[data-line]")) {
    const rect = row.getBoundingClientRect();
    if (rect.height > 0 && rect.bottom > top && rect.top < bottom) found.add(Number(row.dataset.line));
  }
  return found;
}

// "meetingId:revision" keys, newest last. Storage can be missing or throw (private
// windows, blocked site data); this session's memory then stands in for it.
const storageKey = "m2o-moment",
  storageLimit = 50,
  remembered = new Set<string>();

function storedKeys(): string[] {
  const value: unknown = JSON.parse(localStorage.getItem(storageKey) || "[]");
  return Array.isArray(value) ? value.filter((key): key is string => typeof key === "string") : [];
}

/** True when this browser already played the moment for `key` ("meetingId:revision"). */
export function momentSeen(key: string): boolean {
  try {
    return storedKeys().includes(key);
  } catch {
    return remembered.has(key);
  }
}

export function markMomentSeen(key: string) {
  try {
    const keys = [...storedKeys().filter((value) => value !== key), key].slice(-storageLimit);
    localStorage.setItem(storageKey, JSON.stringify(keys));
  } catch {
    remembered.add(key);
  }
}

/** The moment animates only with the View Transitions API and with motion allowed. */
export function canAnimate(): boolean {
  return typeof document.startViewTransition === "function" && prefersMotion();
}
