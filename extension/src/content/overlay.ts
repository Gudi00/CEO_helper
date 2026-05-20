/**
 * In-page UI for the assist/step-by-step modes.
 *
 *  - `highlight(label, result)` puts a non-intrusive green ring on the
 *    correct variant (assist mode).
 *  - `showStepPrompt(...)` puts a small modal anchored to the question
 *    that resolves on user confirm/reject.
 *  - `injectStylesOnce()` adds the global CSS once per document.
 *
 * Stealth notes (ADR 0007):
 *   - We never write `.checked = true`; clicks are dispatched as native
 *     MouseEvents from `dispatchClick` (called only after user confirms).
 *   - Styles are scoped to `data-lms-tool="1"` selectors so we don't
 *     collide with Moodle's own classes.
 */

import type { AnswerResult } from "@/shared/types.js";
import { findOptionInput, findOptionLabel } from "./moodle-parser.js";

const STYLE_ID = "lms-tool-styles";

const CSS = `
  [data-lms-tool="suggested"] {
    outline: 2px solid #2ecc71 !important;
    outline-offset: 2px !important;
    background-color: rgba(46, 204, 113, 0.08) !important;
    transition: background-color 200ms;
  }
  [data-lms-tool="suggested-low"] {
    outline-color: #f39c12 !important;
    background-color: rgba(243, 156, 18, 0.08) !important;
  }
  .lms-tool-tooltip {
    position: absolute;
    z-index: 2147483647;
    background: #1f2937;
    color: #fff;
    padding: 6px 10px;
    border-radius: 6px;
    font: 12px/1.4 system-ui, sans-serif;
    pointer-events: none;
    max-width: 280px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
  }
  .lms-tool-step {
    position: fixed;
    z-index: 2147483647;
    right: 20px;
    bottom: 20px;
    width: 320px;
    background: #fff;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    box-shadow: 0 12px 32px rgba(0,0,0,0.18);
    font: 13px/1.4 system-ui, sans-serif;
    color: #111827;
    overflow: hidden;
  }
  .lms-tool-step__hdr {
    background: #2ecc71;
    color: #fff;
    padding: 8px 12px;
    font-weight: 600;
  }
  .lms-tool-step__body { padding: 12px; }
  .lms-tool-step__reason { color: #4b5563; font-size: 12px; margin-top: 4px; }
  .lms-tool-step__btns {
    display: flex; gap: 8px; margin-top: 12px; justify-content: flex-end;
  }
  .lms-tool-step__btn {
    padding: 6px 12px; border: 1px solid #d1d5db;
    background: #f9fafb; cursor: pointer; border-radius: 4px;
    font: inherit;
  }
  .lms-tool-step__btn--primary {
    background: #2ecc71; color: #fff; border-color: #2ecc71;
  }
  .lms-tool-toast {
    position: fixed;
    z-index: 2147483647;
    left: 50%;
    top: 20px;
    transform: translateX(-50%);
    background: #1f2937;
    color: #fff;
    padding: 10px 16px;
    border-radius: 8px;
    font: 13px/1.4 system-ui, sans-serif;
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    max-width: 480px;
  }
  .lms-tool-toast--info { background: #1f2937; }
  .lms-tool-toast--warn { background: #b45309; }
  .lms-tool-toast--err  { background: #b91c1c; }
  .lms-tool-badge {
    display: block;
    margin: 8px 0;
    padding: 10px 14px;
    background: #064e3b;
    color: #d1fae5;
    border-left: 4px solid #10b981;
    border-radius: 6px;
    font: 600 14px/1.4 system-ui, sans-serif;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  }
  .lms-tool-badge--low {
    background: #78350f;
    color: #fef3c7;
    border-left-color: #f59e0b;
  }
  .lms-tool-badge__pick {
    font-size: 18px;
    background: #10b981;
    color: #fff;
    padding: 2px 10px;
    border-radius: 4px;
    margin-right: 8px;
    display: inline-block;
  }
  .lms-tool-badge--low .lms-tool-badge__pick { background: #f59e0b; }
  .lms-tool-badge__meta { font-size: 11px; opacity: 0.85; font-weight: 400; }
  .lms-tool-badge__reason {
    display: block;
    margin-top: 6px;
    font-size: 12px;
    font-weight: 400;
    opacity: 0.9;
  }
`;

export function injectStylesOnce(doc: Document = document): void {
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = CSS;
  doc.head.appendChild(style);
}

/**
 * Assist mode: visually mark the AI's chosen options + drop a big visible
 * badge under the question text so it's obvious even when the host site
 * overrides our outline/background CSS. Returns a cleanup function.
 */
export function highlight(
  questionContainer: HTMLElement,
  result: AnswerResult,
): () => void {
  injectStylesOnce(questionContainer.ownerDocument);
  const variant =
    result.confidence < 0.6 ? "suggested-low" : "suggested";
  const marked: HTMLElement[] = [];
  for (const idx of result.answer_indices) {
    const target = findOptionLabel(questionContainer, idx);
    if (target) {
      target.setAttribute("data-lms-tool", variant);
      target.title =
        `AI (${result.provider}): ${(result.confidence * 100).toFixed(0)}%` +
        (result.reasoning ? ` — ${result.reasoning}` : "");
      marked.push(target);
    }
  }
  const removeBadge = showInlineBadge(questionContainer, result);
  return () => {
    for (const el of marked) {
      el.removeAttribute("data-lms-tool");
      el.removeAttribute("title");
    }
    removeBadge();
  };
}

/**
 * Inserts a "AI: вариант N" block directly under the question's `.qtext`.
 * This is the user-facing primary signal because Moodle themes routinely
 * override our outline styles. The block uses inline `style` attributes
 * with `!important` for the most important rules to survive themes.
 */
export function showInlineBadge(
  questionContainer: HTMLElement,
  result: AnswerResult,
): () => void {
  injectStylesOnce(questionContainer.ownerDocument);
  const doc = questionContainer.ownerDocument;
  // Anchor right under the question text. If .qtext missing, fall back
  // to inserting at the top of .content or the container itself.
  const anchor =
    questionContainer.querySelector(".qtext") ??
    questionContainer.querySelector(".content") ??
    questionContainer;

  // Remove any previous badge from earlier processing of this same .que.
  const existing = questionContainer.querySelector(".lms-tool-badge");
  if (existing) existing.remove();

  const badge = doc.createElement("div");
  badge.className =
    "lms-tool-badge" + (result.confidence < 0.6 ? " lms-tool-badge--low" : "");
  // 1-based picks for human reading ("вариант 1" not "вариант 0").
  const picks = result.answer_indices.map((i) => i + 1).join(", ");
  const cachedSuffix = result.from_cache ? " · из кеша" : "";
  badge.innerHTML =
    `<span class="lms-tool-badge__pick">${escapeHtml(picks)}</span>` +
    `AI: вариант ${escapeHtml(picks)}` +
    ` <span class="lms-tool-badge__meta">` +
    `${(result.confidence * 100).toFixed(0)}% · ${escapeHtml(result.provider)}` +
    `${cachedSuffix}</span>` +
    (result.reasoning
      ? `<span class="lms-tool-badge__reason">${escapeHtml(result.reasoning)}</span>`
      : "");

  anchor.insertAdjacentElement("afterend", badge);
  return () => badge.remove();
}

export type StepDecision = "confirm" | "reject";

/**
 * Step-by-step mode prompt. Returns a promise that resolves once the
 * user decides. `cleanup` is fired afterward to remove the modal.
 */
export function showStepPrompt(
  questionContainer: HTMLElement,
  result: AnswerResult,
): Promise<StepDecision> {
  injectStylesOnce(questionContainer.ownerDocument);
  const doc = questionContainer.ownerDocument;
  const modal = doc.createElement("div");
  modal.className = "lms-tool-step";
  modal.setAttribute("data-lms-tool-modal", "1");

  const picks = result.answer_indices.map((i) => i + 1).join(", ");
  modal.innerHTML = `
    <div class="lms-tool-step__hdr">AI вариант ${picks} (${(result.confidence * 100).toFixed(0)}%)</div>
    <div class="lms-tool-step__body">
      ${result.reasoning ? `<div class="lms-tool-step__reason">${escapeHtml(result.reasoning)}</div>` : ""}
      <div class="lms-tool-step__btns">
        <button class="lms-tool-step__btn" data-act="reject" type="button">Отменить (Esc)</button>
        <button class="lms-tool-step__btn lms-tool-step__btn--primary" data-act="confirm" type="button">Применить (Enter)</button>
      </div>
    </div>
  `;
  doc.body.appendChild(modal);

  return new Promise<StepDecision>((resolve) => {
    const cleanup = (decision: StepDecision) => {
      doc.removeEventListener("keydown", onKey);
      modal.remove();
      resolve(decision);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter") cleanup("confirm");
      else if (e.key === "Escape") cleanup("reject");
    };
    modal.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      const act = target.dataset?.act;
      if (act === "confirm" || act === "reject") cleanup(act);
    });
    doc.addEventListener("keydown", onKey);
  });
}

/**
 * Imitate a click on the option's <input> using native events (no
 * `.checked = true` writes — see ADR 0007).
 */
export function dispatchClick(
  questionContainer: HTMLElement,
  optionIndex: number,
): boolean {
  const input = findOptionInput(questionContainer, optionIndex);
  if (!input) return false;
  input.scrollIntoView({ behavior: "smooth", block: "center" });
  const rect = input.getBoundingClientRect();
  const opts: MouseEventInit = {
    bubbles: true,
    cancelable: true,
    view: input.ownerDocument.defaultView ?? undefined,
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2,
    button: 0,
  };
  input.dispatchEvent(new MouseEvent("mousedown", opts));
  input.dispatchEvent(new MouseEvent("mouseup", opts));
  input.dispatchEvent(new MouseEvent("click", opts));
  return true;
}

export type ToastKind = "info" | "warn" | "err";

/**
 * Floating notification at the top of the page. Used by the content
 * script to surface backend errors / state changes so the user does
 * not have to open DevTools to see what is going on.
 *
 * Returns a function that dismisses the toast.
 */
export function showToast(
  text: string,
  kind: ToastKind = "info",
  durationMs = 5_000,
  doc: Document = document,
): () => void {
  injectStylesOnce(doc);
  const el = doc.createElement("div");
  el.className = `lms-tool-toast lms-tool-toast--${kind}`;
  el.setAttribute("data-lms-tool-toast", "1");
  el.textContent = text;
  doc.body.appendChild(el);
  let removed = false;
  const remove = () => {
    if (removed) return;
    removed = true;
    el.remove();
  };
  if (durationMs > 0) {
    setTimeout(remove, durationMs);
  }
  el.addEventListener("click", remove);
  return remove;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
