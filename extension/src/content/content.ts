/**
 * Content-script entrypoint. Observes the Moodle quiz DOM, parses each
 * question once it appears, asks the backend for an answer, then either
 * highlights / prompts / clicks depending on the current mode.
 *
 * Sessions are owned by the popup (it calls /api/session/start); the
 * service worker stashes the current sessionId+mode in chrome.storage
 * so this script can pick them up.
 *
 * Important runtime ordering: a Moodle page can finish loading BEFORE
 * the user opens the popup and starts a session. So `bootstrap()` must
 * not give up if the session is empty — it must react when the popup
 * writes `activeSessionId` into chrome.storage later on.
 */

import { loadSettings } from "@/shared/api-client.js";
import { describeError } from "@/shared/errors.js";
import { buildManualPrompt, parseManualAnswer } from "@/shared/manual-answer.js";
import { MessagingBackendClient } from "@/shared/messaging-client.js";
import {
  DEFAULT_SETTINGS,
  type AnswerResult,
  type AnswerSource,
  type ExecutionMode,
  type ExtensionSettings,
  type NormalizedQuestion,
  type QuizProgress,
} from "@/shared/types.js";
import { collectImages } from "./images.js";
import { parseOne } from "./moodle-parser.js";
import {
  dispatchClick,
  highlight,
  highlightDots,
  injectStylesOnce,
  showManualPanel,
  showStatusBadge,
  showStepPrompt,
  showToast,
} from "./overlay.js";

interface RuntimeContext {
  settings: ExtensionSettings;
  sessionId: string | null;
  cmid: string | null;
  client: MessagingBackendClient;
}

// Containers we've already processed for the *current* sessionId. Keyed by
// container element so a DOM swap reuses the slot. Note: this is intentionally
// a per-(container, sessionId) record rather than a plain WeakSet — if the
// sessionId changes, we re-process every visible question.
const handled = new WeakMap<HTMLElement, string>();
const MANUAL_MARK = "manual";

// Questions go to the backend one at a time: a local model can't serve a
// whole page in parallel, and free cloud tiers rate-limit bursts.
let queueTail: Promise<void> = Promise.resolve();
function enqueue(task: () => Promise<void>): void {
  queueTail = queueTail.then(task, task);
}

const progress: QuizProgress = { total: 0, done: 0, failed: 0 };
function publishProgress(): void {
  void chrome.storage.local.set({ progress: { ...progress } });
}
function resetProgress(): void {
  progress.total = progress.done = progress.failed = 0;
  publishProgress();
}

function extractCmid(): string | null {
  const params = new URLSearchParams(globalThis.location.search);
  return params.get("cmid") ?? params.get("id");
}

function log(...args: unknown[]): void {
  console.log("[lms-tool]", ...args);
}

/** Show the result on the page the way the current mode asks for. */
async function act(
  ctx: RuntimeContext,
  container: HTMLElement,
  result: AnswerResult,
): Promise<void> {
  switch (ctx.settings.mode) {
    case "assist":
      if (ctx.settings.showOverlay) highlight(container, result);
      return;
    case "step_by_step": {
      const decision = await showStepPrompt(container, result);
      if (decision === "confirm") {
        for (const idx of result.answer_indices) {
          dispatchClick(container, idx);
        }
      }
      return;
    }
    case "full_auto":
      // Engine drives the browser from the Python side. The content
      // script just records the suggestion for visibility.
      if (ctx.settings.showOverlay) highlight(container, result);
      return;
    case "stealth":
      highlightDots(container, result, ctx.settings.stealthDot);
      return;
  }
}

function offerManual(container: HTMLElement, question: NormalizedQuestion): void {
  showManualPanel(container, {
    onCopy: async () => {
      try {
        await navigator.clipboard.writeText(buildManualPrompt(question));
        return true;
      } catch {
        return false;
      }
    },
    onSubmit: (reply) => {
      const indices = parseManualAnswer(reply, question);
      if (!indices) {
        return question.type === "single_choice"
          ? "Не удалось распознать ответ. Нужен один номер варианта, например «Ответ: 2»."
          : "Не удалось распознать ответ. Нужны номера вариантов, например «Ответ: 1, 3».";
      }
      highlight(container, {
        answer_indices: indices,
        confidence: 1,
        reasoning: null,
        provider: "вручную",
        from_cache: false,
      });
      return null;
    },
  });
}

async function askBackend(
  ctx: RuntimeContext,
  container: HTMLElement,
  question: NormalizedQuestion,
  sessionId: string,
  visible: boolean,
): Promise<void> {
  // The session may have been stopped or replaced while this waited in line.
  if (ctx.sessionId !== sessionId || !container.isConnected) return;
  if (visible) showStatusBadge(container, "thinking", "Нейросеть думает…");

  let result: AnswerResult;
  try {
    result = await ctx.client.answerQuestion({
      session_id: sessionId,
      question,
      use_cache: true,
    });
  } catch (err) {
    console.error("[lms-tool] backend error", err);
    progress.failed += 1;
    publishProgress();
    if (visible) {
      showStatusBadge(container, "error", describeError(err), [
        {
          label: "Повторить",
          onClick: () => {
            progress.failed -= 1;
            publishProgress();
            showStatusBadge(container, "queued", "В очереди…");
            enqueue(() => askBackend(ctx, container, question, sessionId, visible));
          },
        },
        { label: "Ответить вручную", onClick: () => offerManual(container, question) },
      ]);
    }
    return;
  }

  progress.done += 1;
  publishProgress();
  log(
    `answer for ${question.id}: indices=${JSON.stringify(result.answer_indices)} ` +
      `confidence=${result.confidence.toFixed(2)} (${result.provider}` +
      `${result.from_cache ? ", cached" : ""})`,
  );
  await act(ctx, container, result);
}

async function answerAndAct(
  ctx: RuntimeContext,
  container: HTMLElement,
): Promise<void> {
  const manual = ctx.settings.answerSource === "manual";
  if (!manual && !ctx.sessionId) {
    log("no active session yet — waiting for popup → Start");
    return;
  }
  const mark = manual ? MANUAL_MARK : (ctx.sessionId as string);
  if (handled.get(container) === mark) return;
  // Claim the container before the async parse so a second pass (mutation
  // observer, storage event) doesn't process the same question twice.
  handled.set(container, mark);

  // Stealth mode keeps the page free of our status badges.
  const visible = ctx.settings.mode !== "stealth";

  let question: NormalizedQuestion;
  try {
    question = await parseOne(container, {
      cmid: ctx.cmid ?? "0",
      pageNumber: 0,
    });
  } catch (err) {
    console.warn("[lms-tool] parse failed", err);
    if (visible) {
      showStatusBadge(
        container,
        "unsupported",
        "Этот тип вопроса пока не поддерживается — ответьте на него сами.",
      );
    }
    return;
  }

  if (manual) {
    offerManual(container, question);
    return;
  }

  if (question.metadata.has_images) {
    question.images = await collectImages(container);
  }

  const sessionId = mark;
  progress.total += 1;
  publishProgress();
  if (visible) showStatusBadge(container, "queued", "В очереди…");
  enqueue(() => askBackend(ctx, container, question, sessionId, visible));
}

function processAllQuestions(ctx: RuntimeContext): void {
  document
    .querySelectorAll<HTMLElement>('div.que[id^="question-"]')
    .forEach((q) => void answerAndAct(ctx, q));
}

async function bootstrap(): Promise<void> {
  const settings = await loadSettings(DEFAULT_SETTINGS);
  const stored = await chrome.storage.local.get(["activeSessionId"]);
  const sessionId = (stored.activeSessionId as string | undefined) ?? null;

  const ctx: RuntimeContext = {
    settings,
    sessionId,
    cmid: extractCmid(),
    client: new MessagingBackendClient(),
  };

  injectStylesOnce();
  log(
    `content script ready (mode=${settings.mode}, cmid=${ctx.cmid ?? "?"}, ` +
      `session=${ctx.sessionId ? ctx.sessionId.slice(0, 8) + "…" : "none"})`,
  );
  resetProgress();
  if (!ctx.sessionId && settings.answerSource !== "manual") {
    showToast(
      "Откройте окно расширения и нажмите «Начать», чтобы получить подсказки.",
      "info",
      6000,
    );
  }

  processAllQuestions(ctx);

  // 1) React to storage changes — popup writes activeSessionId / mode /
  //    settings async; we want the content script to wake up.
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    let needsReprocess = false;
    if ("activeSessionId" in changes) {
      ctx.sessionId =
        (changes.activeSessionId.newValue as string | undefined) ?? null;
      log(
        `session changed → ${
          ctx.sessionId ? ctx.sessionId.slice(0, 8) + "…" : "none"
        }`,
      );
      resetProgress();
      needsReprocess = true;
    }
    if ("answerSource" in changes) {
      ctx.settings.answerSource = changes.answerSource.newValue as AnswerSource;
      needsReprocess = true;
    }
    if ("mode" in changes) {
      ctx.settings.mode = changes.mode.newValue as ExecutionMode;
      needsReprocess = true;
    }
    if ("showOverlay" in changes) {
      ctx.settings.showOverlay = Boolean(changes.showOverlay.newValue);
    }
    if ("stealthDot" in changes) {
      ctx.settings.stealthDot = changes.stealthDot.newValue as typeof ctx.settings.stealthDot;
    }
    if (needsReprocess) processAllQuestions(ctx);
  });

  // 2) Observe DOM mutations — Moodle swaps `.que` on every "Next page".
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((n) => {
        if (!(n instanceof HTMLElement)) return;
        if (n.matches?.('div.que[id^="question-"]')) {
          void answerAndAct(ctx, n);
        }
        n.querySelectorAll?.<HTMLElement>(
          'div.que[id^="question-"]',
        ).forEach((q) => void answerAndAct(ctx, q));
      });
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

if (typeof window !== "undefined") {
  // Don't run inside jsdom-style harnesses.
  void bootstrap().catch((err) =>
    console.error("[lms-tool] bootstrap failed", err),
  );
}
