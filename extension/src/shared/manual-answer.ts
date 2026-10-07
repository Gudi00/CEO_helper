/**
 * Manual mode: the user copies a ready-made prompt into any chat model and
 * pastes the reply back. No backend, no API key.
 */

import type { NormalizedQuestion } from "./types.js";

export function buildManualPrompt(q: NormalizedQuestion): string {
  const task =
    q.type === "single_choice"
      ? "Выбери ОДИН правильный вариант."
      : "Выбери ОДИН ИЛИ НЕСКОЛЬКО правильных вариантов.";
  const options = q.options.map((o) => `${o.index + 1}) ${o.text}`).join("\n");
  return (
    `${task}\n\nВопрос:\n${q.text}\n\nВарианты:\n${options}\n\n` +
    "Кратко объясни выбор, а последней строкой напиши строго в таком виде:\n" +
    "Ответ: <номера вариантов через запятую>"
  );
}

const LETTERS = "абвгдежзик";
const LATIN = "abcdefghij";

function normalize(s: string): string {
  return s.toLowerCase().replace(/ё/g, "е").replace(/\s+/g, " ").trim();
}

function fromNumbers(raw: string, optionCount: number): number[] | null {
  const nums = raw.match(/\d+/g)?.map((n) => parseInt(n, 10) - 1) ?? [];
  if (nums.length === 0) return null;
  if (nums.some((i) => i < 0 || i >= optionCount)) return null;
  return [...new Set(nums)].sort((a, b) => a - b);
}

function fromLetters(raw: string, optionCount: number): number[] | null {
  const tokens = normalize(raw)
    .split(/[\s,;.)]+/)
    .filter(Boolean);
  if (tokens.length === 0 || tokens.some((t) => t.length !== 1)) return null;
  const idx = tokens.map((t) => {
    const i = LETTERS.indexOf(t);
    return i >= 0 ? i : LATIN.indexOf(t);
  });
  if (idx.some((i) => i < 0 || i >= optionCount)) return null;
  return [...new Set(idx)].sort((a, b) => a - b);
}

/**
 * Extract 0-based option indices from a pasted model reply. Understands an
 * "Ответ: 1, 3" line, bare numbers, bare letters, and an option quoted
 * verbatim. Returns null when the reply can't be read unambiguously.
 */
export function parseManualAnswer(
  reply: string,
  q: NormalizedQuestion,
): number[] | null {
  const text = reply.trim();
  if (!text) return null;
  const n = q.options.length;

  const marked = [...text.matchAll(/(?:ответ|answer)\s*[:—-]\s*([^\n]+)/gi)].pop();
  const candidate = (marked?.[1] ?? text).trim();

  let found =
    (/^[\d\s,;.и]+$/i.test(candidate) ? fromNumbers(candidate, n) : null) ??
    fromLetters(candidate, n);

  if (!found && marked) found = fromNumbers(candidate, n);

  if (!found) {
    const hay = normalize(candidate);
    const byText = q.options
      .filter((o) => hay.includes(normalize(o.text)))
      .map((o) => o.index);
    if (byText.length > 0) found = byText;
  }

  if (!found || found.length === 0) return null;
  if (q.type === "single_choice" && found.length !== 1) return null;
  return found;
}
