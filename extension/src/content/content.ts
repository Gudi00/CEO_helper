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

import { ApiError } from "@/shared/api-client.js";
import { loadSettings } from "@/shared/api-client.js";
import { MessagingBackendClient } from "@/shared/messaging-client.js";
import {
  DEFAULT_SETTINGS,
  type AnswerResult,
  type ExecutionMode,
  type ExtensionSettings,
  type NormalizedQuestion,
} from "@/shared/types.js";
import { parseOne } from "./moodle-parser.js";
import {
  dispatchClick,
  highlight,
  injectStylesOnce,
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
let lastBackendErrorAt = 0;

function extractCmid(): string | null {
  const params = new URLSearchParams(globalThis.location.search);
  return params.get("cmid") ?? params.get("id");
}

function log(...args: unknown[]): void {
  console.log("[lms-tool]", ...args);
}

function reportBackendError(err: unknown): void {
  console.error("[lms-tool] backend error", err);
  // Rate-limit toasts so we don't pile up if 20 questions all fail.
  const now = Date.now();
  if (now - lastBackendErrorAt < 4000) return;
  lastBackendErrorAt = now;
  const msg =
    err instanceof ApiError
      ? `${err.code}: ${err.message}`
      : err instanceof Error
        ? err.message
        : String(err);
  showToast(`LMS-tool: backend error — ${msg}`, "err", 6000);
}

async function answerAndAct(
  ctx: RuntimeContext,
  container: HTMLElement,
): Promise<void> {
  if (!ctx.sessionId) {
    log("no active session yet — waiting for popup → Start");
    return;
  }
  if (handled.get(container) === ctx.sessionId) return;

  let question: NormalizedQuestion;
  try {
    question = await parseOne(container, {
      cmid: ctx.cmid ?? "0",
      pageNumber: 0,
    });
  } catch (err) {
    console.warn("[lms-tool] parse failed", err);
    return;
  }

  // Mark only AFTER we have a valid parse and an active session.
  handled.set(container, ctx.sessionId);

  let result: AnswerResult;
  try {
    result = await ctx.client.answerQuestion({
      session_id: ctx.sessionId,
      question,
      use_cache: true,
    });
  } catch (err) {
    // Roll back the handled mark so a manual reload (or sessionId change)
    // gives the question another chance.
    handled.delete(container);
    reportBackendError(err);
    return;
  }

  log(
    `answer for ${question.id}: indices=${JSON.stringify(result.answer_indices)} ` +
      `confidence=${result.confidence.toFixed(2)} (${result.provider}` +
      `${result.from_cache ? ", cached" : ""})`,
  );

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
  }
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
  if (!ctx.sessionId) {
    showToast(
      "LMS-tool: откройте popup и нажмите «Старт» чтобы начать сессию.",
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
      if (ctx.sessionId) {
        showToast(
          `LMS-tool: сессия активна (${ctx.sessionId.slice(0, 8)}…)`,
          "info",
          3000,
        );
      }
      needsReprocess = true;
    }
    if ("mode" in changes) {
      ctx.settings.mode = changes.mode.newValue as ExecutionMode;
      needsReprocess = true;
    }
    if ("showOverlay" in changes) {
      ctx.settings.showOverlay = Boolean(changes.showOverlay.newValue);
    }
    if (needsReprocess && ctx.sessionId) processAllQuestions(ctx);
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
