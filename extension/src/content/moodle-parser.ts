/**
 * DOM parser for Moodle 4.x quiz pages. The Python engine (backend) has
 * its own copy in `backend/src/moodle/parser.py`; both must produce
 * identical NormalizedQuestion objects from the same HTML — verified by
 * cross-language fixture tests.
 *
 * See ADR 0008 for selectors and the rationale.
 */

import type {
  NormalizedQuestion,
  Option,
  QuestionType,
} from "@/shared/types.js";
import { computeQuestionHash } from "@/shared/hash.js";

const QUESTION_ID_RE = /^question-(\d+)-(\d+)$/;
// Only strip leading "1. " / "a. " enumerators that Moodle injects via
// <span class="answernumber">. Do NOT strip "1)" — BSUIR matrix questions
// like "1) нет 2) да" legitimately contain that pattern as content.
const ANSWERNUMBER_PREFIX_RE = /^[\dа-яa-z]+\.\s+/i;

export class MoodleParseError extends Error {}

export interface ParseContext {
  cmid: string;
  pageNumber?: number;
  root?: ParentNode;
}

/** Find every `.que` question block in `root` (default: document). */
export async function parseQuestions(
  ctx: ParseContext,
): Promise<NormalizedQuestion[]> {
  const root = ctx.root ?? document;
  const containers = Array.from(
    root.querySelectorAll<HTMLElement>('div.que[id^="question-"]'),
  );
  const out: NormalizedQuestion[] = [];
  for (const container of containers) {
    out.push(
      await parseOne(container, {
        cmid: ctx.cmid,
        pageNumber: ctx.pageNumber ?? 0,
      }),
    );
  }
  return out;
}

interface OneCtx {
  cmid: string;
  pageNumber: number;
}

export async function parseOne(
  container: HTMLElement,
  ctx: OneCtx,
): Promise<NormalizedQuestion> {
  const idAttr = container.id || "";
  const match = QUESTION_ID_RE.exec(idAttr);
  if (!match) {
    throw new MoodleParseError(`Bad question id: ${idAttr || "(empty)"}`);
  }
  const attemptId = match[1]!;
  const qNum = match[2]!;

  const qtext = container.querySelector(".qtext");
  if (!qtext) {
    throw new MoodleParseError(`No .qtext in question ${idAttr}`);
  }
  const text = cleanText(readableText(qtext));
  if (!text) {
    throw new MoodleParseError(`Empty .qtext in question ${idAttr}`);
  }

  const hasImages = Boolean(
    container.querySelector(".qtext img, .answer img"),
  );

  const inputs = container.querySelectorAll<HTMLInputElement>(
    '.answer input[type="radio"], .answer input[type="checkbox"]',
  );
  if (inputs.length === 0) {
    throw new MoodleParseError(`No answer inputs in ${idAttr}`);
  }
  const isMulti = inputs[0]!.type === "checkbox";
  const options = extractOptions(container);
  if (options.length < 2) {
    throw new MoodleParseError(
      `Question ${idAttr} has ${options.length} options, expected >=2`,
    );
  }

  const qType: QuestionType = isMulti ? "multiple_choice" : "single_choice";
  return {
    id: `q${attemptId}:${qNum}`,
    hash: await computeQuestionHash(
      text,
      qType,
      options.map((o) => o.text),
    ),
    type: qType,
    text,
    options,
    metadata: {
      page_number: ctx.pageNumber,
      attempt_id: attemptId,
      cmid: ctx.cmid,
      has_images: hasImages,
    },
  };
}

function extractOptions(container: HTMLElement): Option[] {
  const rows = container.querySelectorAll<HTMLElement>(
    '.answer > div[class^="r"]',
  );
  const out: Option[] = [];
  rows.forEach((row, idx) => {
    const input = row.querySelector<HTMLInputElement>(
      'input[type="radio"], input[type="checkbox"]',
    );
    if (!input) return;
    const label = row.querySelector("label");
    const raw = readableText(label ?? row);
    const text = stripAnswernumber(cleanText(raw));
    if (!text) return;
    out.push({
      index: idx,
      value: input.value ?? "",
      text,
    });
  });
  return out;
}

const MATH_RENDER_SELECTOR =
  ".MathJax, .MathJax_Preview, .MathJax_Display, .MJX_Assistive_MathML, mjx-container";

/**
 * Text of a node with formulas kept as source instead of rendering debris:
 * a TeX-filter image becomes `[alt]`, a MathJax `<script type="math/tex">`
 * becomes `$tex$`, and MathJax's rendered spans are dropped.
 * Must stay in step with `_readable_text` in backend/src/moodle/parser.py.
 */
export function readableText(node: Element): string {
  const clone = node.cloneNode(true) as Element;
  const doc = node.ownerDocument;
  clone.querySelectorAll("mjx-container").forEach((el) => {
    const tex = el.querySelector('annotation[encoding="application/x-tex"]');
    if (tex?.textContent) el.before(doc.createTextNode(` $${tex.textContent.trim()}$ `));
  });
  clone.querySelectorAll(MATH_RENDER_SELECTOR).forEach((el) => el.remove());
  clone.querySelectorAll('script[type^="math/tex"]').forEach((el) => {
    el.replaceWith(doc.createTextNode(` $${(el.textContent ?? "").trim()}$ `));
  });
  clone.querySelectorAll("script, style").forEach((el) => el.remove());
  clone.querySelectorAll("img").forEach((img) => {
    const alt = (img.getAttribute("alt") ?? "").trim();
    img.replaceWith(doc.createTextNode(alt ? ` [${alt}] ` : " "));
  });
  return clone.textContent ?? "";
}

function cleanText(s: string): string {
  return s.split(/\s+/).filter(Boolean).join(" ");
}

function stripAnswernumber(s: string): string {
  return s.replace(ANSWERNUMBER_PREFIX_RE, "").trim();
}

/**
 * Locate a paintable element for option `index` inside the question
 * container. Prefers <label> (semantic, works on fixture HTML) but falls
 * back to the row div itself for sites that omit labels (real BSUIR
 * Moodle places the answer text directly under .r0/.r1 with no <label>).
 *
 * Used by overlay/highlight code to add a CSS attribute we can paint.
 */
export function findOptionLabel(
  container: HTMLElement,
  optionIndex: number,
): HTMLElement | null {
  const row = container.querySelectorAll<HTMLElement>(
    '.answer > div[class^="r"]',
  )[optionIndex];
  if (!row) return null;
  return row.querySelector<HTMLLabelElement>("label") ?? row;
}

/**
 * Same as findOptionLabel but returns the radio/checkbox input — needed
 * to dispatch native click events without setting `.checked` directly
 * (see ADR 0007 stealth).
 */
export function findOptionInput(
  container: HTMLElement,
  optionIndex: number,
): HTMLInputElement | null {
  const row = container.querySelectorAll<HTMLElement>(
    '.answer > div[class^="r"]',
  )[optionIndex];
  return (
    row?.querySelector<HTMLInputElement>(
      'input[type="radio"], input[type="checkbox"]',
    ) ?? null
  );
}
