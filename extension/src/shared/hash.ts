/**
 * SHA-256 hash of normalized question identity. Must match the Python
 * implementation in `backend/src/moodle/hashing.py` byte-for-byte.
 *
 * Algorithm (see docs/specs/question-model.md):
 *   normalized_text = casefold(collapse_whitespace(text))
 *   sorted_options  = sorted(casefold(collapse_whitespace(o)) for o in options)
 *   payload = normalized_text + "\n" + type + "\n" + "|".join(sorted_options)
 *   hash = sha256(payload).hexdigest()
 */

import type { QuestionType } from "./types.js";

const ENCODER = new TextEncoder();

function normalizeWhitespace(s: string): string {
  // Python: " ".join(s.split()).casefold()
  // JS:     trimmed runs of whitespace, then lowercase (casefold is close
  //         enough to toLowerCase for the Cyrillic/Latin we expect here).
  return s.split(/\s+/).filter(Boolean).join(" ").toLowerCase();
}

export async function computeQuestionHash(
  text: string,
  qType: QuestionType,
  optionTexts: string[],
): Promise<string> {
  const normalizedText = normalizeWhitespace(text);
  const sorted = optionTexts.map(normalizeWhitespace).sort();
  const payload = `${normalizedText}\n${qType}\n${sorted.join("|")}`;

  const buf = await crypto.subtle.digest("SHA-256", ENCODER.encode(payload));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
