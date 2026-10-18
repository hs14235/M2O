import { afterEach, expect, it, vi } from "vitest";
import type { Evidence, Outcome } from "../../types";
import {
  canAnimate,
  evidenceLines,
  markMomentSeen,
  momentName,
  momentSeen,
  pairNames,
  transcriptLines,
} from "./signatureMoment";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  delete document.documentElement.dataset.motion;
  Reflect.deleteProperty(document, "startViewTransition");
});

const chunk = (start_line: number, text: string): Evidence => ({
  id: "e" + start_line,
  i: 0,
  text,
  speaker: null,
  start_line,
});
const outcome = (id: string, ...evidence: Evidence[]) => ({ id, evidence }) as Outcome;

it("numbers lines the way the backend does, across line-break styles", () => {
  expect(transcriptLines("one\r\ntwo\nthree\rfour")).toEqual(["one", "two", "three", "four"]);
  expect(transcriptLines("one" + String.fromCharCode(0x2028) + "two")).toEqual(["one", "two"]);
});

it("maps a chunk onto the non-blank lines it spans, skipping blank lines", () => {
  const lines = transcriptLines("Alex: Ship it\n\nnotes one\n   \nnotes two\nnotes three\n");
  expect(evidenceLines(lines, chunk(1, "Alex: Ship it"))).toEqual([1]);
  expect(evidenceLines(lines, chunk(3, "notes one\nnotes two"))).toEqual([3, 5]);
  // A chunk that starts on a blank line still finds the text after it.
  expect(evidenceLines(lines, chunk(2, "notes one"))).toEqual([3]);
  // Never past the end of the transcript.
  expect(evidenceLines(lines, chunk(6, "notes three\nmissing"))).toEqual([6]);
});

it("keeps the pieces of one long line on that line", () => {
  // The backend cuts a long line into pieces and joins them with "\n" inside one chunk.
  const long = "Alex: " + "x".repeat(700) + "y".repeat(700);
  const lines = transcriptLines("Intro\n" + long + "\nNext line");
  const pieces = [long.slice(0, 720), long.slice(720)];
  expect(evidenceLines(lines, chunk(2, pieces.join("\n")))).toEqual([2]);
  expect(evidenceLines(lines, chunk(2, pieces[1] + "\nNext line"))).toEqual([2, 3]);
});

it("gives each outcome its own visible line, up to the limit", () => {
  const lines = transcriptLines("a\nb\nc\nd");
  const shared = chunk(1, "a\nb");
  const all = new Set([1, 2, 3, 4]);
  // Both outcomes cite lines 1-2: the second takes the next unclaimed line.
  expect(pairNames([outcome("x", shared), outcome("y", shared)], lines, all)).toEqual(
    new Map([
      [1, momentName("x")],
      [2, momentName("y")],
    ]),
  );
  // Off-screen lines are never paired; an outcome with none left stays unpaired.
  expect(pairNames([outcome("x", shared), outcome("y", chunk(1, "a"))], lines, new Set([1, 3]))).toEqual(
    new Map([[1, momentName("x")]]),
  );
  expect(pairNames([outcome("x", chunk(1, "a")), outcome("y", chunk(3, "c"))], lines, all, 1)?.size).toBe(1);
});

it("refuses the whole transition when two outcomes would share a name", () => {
  const lines = transcriptLines("a\nb");
  expect(momentName("a.b")).toBe(momentName("a_b"));
  expect(
    pairNames([outcome("a.b", chunk(1, "a")), outcome("a_b", chunk(2, "b"))], lines, new Set([1, 2])),
  ).toBe(null);
});

it("remembers played revisions, newest 50, and falls back to memory when storage throws", () => {
  for (let n = 0; n < 55; n++) markMomentSeen("meeting:" + n);
  expect(momentSeen("meeting:54")).toBe(true);
  expect(momentSeen("meeting:4")).toBe(false);
  expect(JSON.parse(localStorage.getItem("m2o-moment")!)).toHaveLength(50);
  localStorage.setItem("m2o-moment", "not json");
  expect(momentSeen("meeting:54")).toBe(false);

  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(momentSeen("private:1")).toBe(false);
  markMomentSeen("private:1");
  expect(momentSeen("private:1")).toBe(true);
});

it("animates only with the View Transitions API and motion allowed", () => {
  expect(canAnimate()).toBe(false);
  Object.defineProperty(document, "startViewTransition", { value: vi.fn(), configurable: true });
  expect(canAnimate()).toBe(true);
  document.documentElement.dataset.motion = "calm";
  expect(canAnimate()).toBe(false);
});
