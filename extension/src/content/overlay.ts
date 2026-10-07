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

import { LOW_CONFIDENCE, type AnswerResult } from "@/shared/types.js";
import { findOptionInput, findOptionLabel } from "./moodle-parser.js";

const STYLE_ID = "lms-tool-styles";

const CSS = `
  /* One token set for everything we draw on the page, mirroring the popup:
     light by default, dark when the system asks for it. */
  .lms-tool-badge, .lms-tool-step, .lms-tool-toast, .lms-tool-tooltip {
    --lt-accent: #15803d;
    --lt-on-accent: #ffffff;
    --lt-warn: #b45309;
    --lt-danger: #b91c1c;
    --lt-surface: #ffffff;
    --lt-text: #111827;
    --lt-muted: #4b5563;
    --lt-border: #d1d5db;
    --lt-ok-bg: #ecfdf5;
    --lt-ok-text: #064e3b;
    --lt-low-bg: #fffbeb;
    --lt-low-text: #78350f;
    --lt-status-bg: #f3f4f6;
    --lt-status-text: #111827;
    --lt-status-edge: #6b7280;
    --lt-err-bg: #fef2f2;
    --lt-err-text: #7f1d1d;
    --lt-control-bg: #ffffff;
  }
  @media (prefers-color-scheme: dark) {
    .lms-tool-badge, .lms-tool-step, .lms-tool-toast, .lms-tool-tooltip {
      --lt-accent: #16a34a;
      --lt-warn: #d97706;
      --lt-danger: #dc2626;
      --lt-surface: #1f2937;
      --lt-text: #f3f4f6;
      --lt-muted: #9ca3af;
      --lt-border: #4b5563;
      --lt-ok-bg: #064e3b;
      --lt-ok-text: #d1fae5;
      --lt-low-bg: #78350f;
      --lt-low-text: #fef3c7;
      --lt-status-bg: #1f2937;
      --lt-status-text: #e5e7eb;
      --lt-status-edge: #9ca3af;
      --lt-err-bg: #7f1d1d;
      --lt-err-text: #fee2e2;
      --lt-control-bg: #111827;
    }
  }
  [data-lms-tool="suggested"] {
    outline: 2px solid #15803d !important;
    outline-offset: 2px !important;
    background-color: rgba(22, 163, 74, 0.10) !important;
    transition: background-color 200ms;
  }
  [data-lms-tool="suggested-low"] {
    outline-color: #d97706 !important;
    background-color: rgba(217, 119, 6, 0.10) !important;
  }
  @media (prefers-reduced-motion: reduce) {
    [data-lms-tool="suggested"] { transition: none; }
  }
  .lms-tool-tooltip {
    position: absolute;
    z-index: 2147483647;
    background: var(--lt-surface);
    color: var(--lt-text);
    border: 1px solid var(--lt-border);
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
    background: var(--lt-surface);
    border: 1px solid var(--lt-border);
    border-radius: 8px;
    box-shadow: 0 12px 32px rgba(0,0,0,0.18);
    font: 13px/1.4 system-ui, sans-serif;
    color: var(--lt-text);
    overflow: hidden;
  }
  .lms-tool-step__hdr {
    background: var(--lt-accent);
    color: var(--lt-on-accent);
    padding: 8px 12px;
    font-weight: 600;
  }
  .lms-tool-step__body { padding: 12px; }
  .lms-tool-step__reason { color: var(--lt-muted); font-size: 12px; margin-top: 4px; }
  .lms-tool-step__btns {
    display: flex; gap: 8px; margin-top: 12px; justify-content: flex-end;
  }
  .lms-tool-step__btn {
    padding: 6px 12px; border: 1px solid var(--lt-border);
    background: var(--lt-control-bg); color: var(--lt-text);
    cursor: pointer; border-radius: 4px;
    font: inherit;
  }
  .lms-tool-step__btn--primary {
    background: var(--lt-accent); color: var(--lt-on-accent); border-color: var(--lt-accent);
  }
  .lms-tool-toast {
    position: fixed;
    z-index: 2147483647;
    left: 50%;
    top: 20px;
    transform: translateX(-50%);
    background: var(--lt-surface);
    color: var(--lt-text);
    border: 1px solid var(--lt-border);
    border-left: 4px solid var(--lt-status-edge);
    padding: 10px 16px;
    border-radius: 8px;
    font: 13px/1.4 system-ui, sans-serif;
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    max-width: 480px;
  }
  .lms-tool-toast--warn { border-left-color: var(--lt-warn); }
  .lms-tool-toast--err  { border-left-color: var(--lt-danger); }
  .lms-tool-badge {
    display: block;
    margin: 8px 0;
    padding: 10px 14px;
    background: var(--lt-ok-bg);
    color: var(--lt-ok-text);
    border-left: 4px solid var(--lt-accent);
    border-radius: 6px;
    font: 600 14px/1.4 system-ui, sans-serif;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  }
  .lms-tool-badge--low {
    background: var(--lt-low-bg);
    color: var(--lt-low-text);
    border-left-color: var(--lt-warn);
  }
  .lms-tool-badge__pick {
    font-size: 18px;
    background: var(--lt-accent);
    color: var(--lt-on-accent);
    padding: 2px 10px;
    border-radius: 4px;
    margin-right: 8px;
    display: inline-block;
  }
  .lms-tool-badge--low .lms-tool-badge__pick { background: var(--lt-warn); }
  .lms-tool-badge__meta { font-size: 11px; opacity: 0.85; font-weight: 400; }
  .lms-tool-badge__reason {
    display: block;
    margin-top: 6px;
    font-size: 12px;
    font-weight: 400;
    opacity: 0.9;
  }
  .lms-tool-badge--status {
    background: var(--lt-status-bg);
    color: var(--lt-status-text);
    border-left-color: var(--lt-status-edge);
    font-weight: 400;
    font-size: 13px;
  }
  .lms-tool-badge--error {
    background: var(--lt-err-bg);
    color: var(--lt-err-text);
    border-left-color: var(--lt-danger);
  }
  .lms-tool-badge__actions { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
  .lms-tool-badge__btn {
    padding: 4px 10px;
    border: 1px solid var(--lt-border);
    background: var(--lt-control-bg);
    color: var(--lt-text);
    border-radius: 4px;
    font: 500 12px/1.4 system-ui, sans-serif;
    cursor: pointer;
  }
  .lms-tool-badge__btn:hover { border-color: var(--lt-accent); }
  .lms-tool-badge__btn:focus-visible,
  .lms-tool-step__btn:focus-visible,
  .lms-tool-badge__input:focus-visible { outline: 2px solid var(--lt-accent); outline-offset: 1px; }
  .lms-tool-badge__input {
    display: block;
    width: 100%;
    box-sizing: border-box;
    margin-top: 8px;
    padding: 6px 8px;
    min-height: 54px;
    border: 1px solid var(--lt-border);
    border-radius: 4px;
    background: var(--lt-control-bg);
    color: var(--lt-text);
    font: 12px/1.4 system-ui, sans-serif;
    resize: vertical;
  }
  .lms-tool-badge__hint { display: block; margin-top: 6px; font-size: 12px; }
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
    result.confidence < LOW_CONFIDENCE ? "suggested-low" : "suggested";
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
    "lms-tool-badge" + (result.confidence < LOW_CONFIDENCE ? " lms-tool-badge--low" : "");
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

function placeBadge(questionContainer: HTMLElement, badge: HTMLElement): void {
  const anchor =
    questionContainer.querySelector(".qtext") ??
    questionContainer.querySelector(".content") ??
    questionContainer;
  questionContainer.querySelector(".lms-tool-badge")?.remove();
  anchor.insertAdjacentElement("afterend", badge);
}

export interface BadgeAction {
  label: string;
  onClick: () => void;
}

export type QuestionStatus = "queued" | "thinking" | "error" | "unsupported";

/**
 * Per-question state shown in place of the answer badge: waiting in the
 * queue, model working, failed, or not answerable. Replaces any badge
 * already on the question. Returns a cleanup function.
 */
export function showStatusBadge(
  questionContainer: HTMLElement,
  status: QuestionStatus,
  text: string,
  actions: BadgeAction[] = [],
): () => void {
  injectStylesOnce(questionContainer.ownerDocument);
  const doc = questionContainer.ownerDocument;
  const badge = doc.createElement("div");
  badge.className =
    "lms-tool-badge lms-tool-badge--status" +
    (status === "error" ? " lms-tool-badge--error" : "");
  badge.setAttribute("data-lms-tool-status", status);
  badge.setAttribute("role", "status");

  const label = doc.createElement("span");
  label.textContent = text;
  badge.appendChild(label);

  let timer: ReturnType<typeof setInterval> | undefined;
  if (status === "thinking") {
    const started = Date.now();
    timer = setInterval(() => {
      if (!badge.isConnected) {
        clearInterval(timer);
        return;
      }
      label.textContent = `${text} ${Math.round((Date.now() - started) / 1000)} с`;
    }, 1000);
  }

  if (actions.length > 0) badge.appendChild(buildActions(doc, actions));
  placeBadge(questionContainer, badge);
  return () => {
    if (timer) clearInterval(timer);
    badge.remove();
  };
}

function buildActions(doc: Document, actions: BadgeAction[]): HTMLElement {
  const row = doc.createElement("div");
  row.className = "lms-tool-badge__actions";
  for (const action of actions) {
    const btn = doc.createElement("button");
    btn.type = "button";
    btn.className = "lms-tool-badge__btn";
    btn.textContent = action.label;
    btn.addEventListener("click", action.onClick);
    row.appendChild(btn);
  }
  return row;
}

export interface ManualPanelHandlers {
  /** Copy the ready-made prompt; resolve false if the clipboard refused. */
  onCopy: () => Promise<boolean>;
  /** Try to apply the pasted reply; return an error text, or null on success. */
  onSubmit: (reply: string) => string | null;
}

/**
 * Manual mode: "copy question" button plus a field for the pasted reply.
 * Everything is built with textContent — the reply is untrusted input.
 */
export function showManualPanel(
  questionContainer: HTMLElement,
  handlers: ManualPanelHandlers,
): () => void {
  injectStylesOnce(questionContainer.ownerDocument);
  const doc = questionContainer.ownerDocument;
  const badge = doc.createElement("div");
  badge.className = "lms-tool-badge lms-tool-badge--status";
  badge.setAttribute("data-lms-tool-status", "manual");

  const title = doc.createElement("span");
  title.textContent =
    "Ручной режим: скопируйте вопрос в любую нейросеть и вставьте её ответ сюда.";
  badge.appendChild(title);

  const input = doc.createElement("textarea");
  input.className = "lms-tool-badge__input";
  input.placeholder = "Ответ нейросети, например «Ответ: 2»";
  input.setAttribute("aria-label", "Ответ нейросети");

  const hint = doc.createElement("span");
  hint.className = "lms-tool-badge__hint";
  hint.setAttribute("role", "status");

  badge.appendChild(
    buildActions(doc, [
      {
        label: "Скопировать вопрос",
        onClick: () => {
          void handlers.onCopy().then((ok) => {
            hint.textContent = ok
              ? "Вопрос скопирован."
              : "Не удалось скопировать — разрешите странице доступ к буферу обмена.";
          });
        },
      },
      {
        label: "Показать ответ",
        onClick: () => {
          const error = handlers.onSubmit(input.value);
          if (error) hint.textContent = error;
        },
      },
    ]),
  );
  badge.appendChild(input);
  badge.appendChild(hint);

  placeBadge(questionContainer, badge);
  return () => badge.remove();
}

export interface DotSettings {
  diameter: number;
  offsetX: number;
  offsetY: number;
}

/**
 * Stealth mode: places a small black dot directly under each correct answer
 * label. No badge, no outline — only a subtle positional marker.
 * offsetX shifts the dot horizontally, offsetY adds vertical gap from label.
 */
export function highlightDots(
  questionContainer: HTMLElement,
  result: AnswerResult,
  dot: DotSettings = { diameter: 10, offsetX: 0, offsetY: 0 },
): () => void {
  const placed: HTMLElement[] = [];
  for (const idx of result.answer_indices) {
    const label = findOptionLabel(questionContainer, idx);
    if (!label) continue;
    const el = label.ownerDocument.createElement("span");
    el.setAttribute("data-lms-dot", "1");
    el.style.cssText =
      `display:block;` +
      `width:${dot.diameter}px;` +
      `height:${dot.diameter}px;` +
      `border-radius:50%;` +
      `background:#000;` +
      `pointer-events:none;` +
      `margin-top:${dot.offsetY}px;` +
      `margin-left:${dot.offsetX}px;`;
    label.insertAdjacentElement("afterend", el);
    placed.push(el);
  }
  return () => placed.forEach((d) => d.remove());
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
