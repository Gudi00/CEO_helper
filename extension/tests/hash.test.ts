/**
 * Cross-language hash compatibility: the TS implementation MUST match
 * the Python implementation byte-for-byte. Goldens below were generated
 * by `backend/src/moodle/hashing.py:compute_question_hash` and pinned;
 * if either side drifts the cache key diverges and the assist-route
 * cache would silently miss.
 *
 * Regenerate after intentional changes:
 *   cd backend && .venv/bin/python -c "from src.moodle.hashing \
 *     import compute_question_hash as h; print(h('Что такое HTTP?', \
 *     'single_choice', ['Протокол','Язык','ОС']))"
 */

import { describe, expect, it } from "vitest";
import { computeQuestionHash } from "@/shared/hash.js";

describe("computeQuestionHash", () => {
  it("returns 64 lowercase hex chars", async () => {
    const h = await computeQuestionHash("foo?", "single_choice", ["a", "b"]);
    expect(h).toHaveLength(64);
    expect(h).toMatch(/^[0-9a-f]{64}$/);
  });

  it("is stable across option order", async () => {
    const a = await computeQuestionHash("Q", "single_choice", ["A", "B", "C"]);
    const b = await computeQuestionHash("Q", "single_choice", ["C", "A", "B"]);
    expect(a).toBe(b);
  });

  it("ignores whitespace and case", async () => {
    const a = await computeQuestionHash("Hello World", "single_choice", ["a", "b"]);
    const b = await computeQuestionHash("  hello   WORLD  ", "single_choice", ["A", "B"]);
    expect(a).toBe(b);
  });

  it("differs by question type", async () => {
    const a = await computeQuestionHash("Q", "single_choice", ["A", "B"]);
    const b = await computeQuestionHash("Q", "multiple_choice", ["A", "B"]);
    expect(a).not.toBe(b);
  });

  it("differs by text", async () => {
    const a = await computeQuestionHash("Q1", "single_choice", ["A", "B"]);
    const b = await computeQuestionHash("Q2", "single_choice", ["A", "B"]);
    expect(a).not.toBe(b);
  });

  it("matches Python golden for cyrillic text", async () => {
    const h = await computeQuestionHash(
      "Что такое HTTP?",
      "single_choice",
      ["Протокол", "Язык", "ОС"],
    );
    expect(h).toBe(
      "600be5babee5ad5bbd484b33ba927ebea7120b7e1d23cd5fa83969b35b386fd9",
    );
  });

  it("matches Python golden for ascii text", async () => {
    const h = await computeQuestionHash(
      "What year was BSUIR founded?",
      "single_choice",
      ["1964", "1967", "1971"],
    );
    expect(h).toBe(
      "52eea7883d18a86d816de5524d30c2848a02139855b9d4631e6d2e3f3c18fc71",
    );
  });

  it("matches Python golden for multi_choice", async () => {
    const h = await computeQuestionHash(
      "Mark interpreted languages",
      "multiple_choice",
      ["Python", "C++", "JS", "Rust"],
    );
    expect(h).toBe(
      "4029c31a27338952d099cd99efdbe87f1370bd418522d6ddbd7ab71f737fb5fd",
    );
  });
});
