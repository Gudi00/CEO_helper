/**
 * Popup UI logic: pair with the backend, pick the answer source and model,
 * start/stop a session, show progress. Settings are saved as they change.
 */

import { ApiError, BackendClient, loadSettings, saveSettings } from "@/shared/api-client.js";
import { describeError, errorCode } from "@/shared/errors.js";
import {
  API_VERSION,
  DEFAULT_SETTINGS,
  type ExtensionSettings,
  type ModelInfo,
  type ModelPreference,
  type QuizProgress,
} from "@/shared/types.js";
import {
  applyStatus,
  cmidFromUrl,
  modelOptionLabel,
  moodleOriginFromInput,
  progressText,
  readFormValues,
} from "./popup-helpers.js";

const $ = <T extends HTMLElement = HTMLElement>(id: string): T =>
  document.getElementById(id) as T;

interface PopupRefs {
  mode: HTMLSelectElement;
  cmid: HTMLInputElement;
  backendUrl: HTMLInputElement;
  backendToken: HTMLInputElement;
  showOverlay: HTMLInputElement;
  modelPreference: HTMLSelectElement;
  answerSource: HTMLSelectElement;
  systemPrompt: HTMLTextAreaElement;
  promptReset: HTMLButtonElement;
  start: HTMLButtonElement;
  stop: HTMLButtonElement;
  status: HTMLDivElement;
  progress: HTMLDivElement;
  dotDiameter: HTMLInputElement;
  dotOffsetX: HTMLInputElement;
  dotOffsetY: HTMLInputElement;
  stealthPanel: HTMLDivElement;
  serverPanel: HTMLDivElement;
  pairPanel: HTMLDivElement;
  pairCode: HTMLInputElement;
  pairBtn: HTMLButtonElement;
  moodleUrl: HTMLInputElement;
  moodleConnect: HTMLButtonElement;
}

function refs(): PopupRefs {
  return {
    mode: $<HTMLSelectElement>("mode"),
    cmid: $<HTMLInputElement>("cmid"),
    backendUrl: $<HTMLInputElement>("backend-url"),
    backendToken: $<HTMLInputElement>("backend-token"),
    showOverlay: $<HTMLInputElement>("show-overlay"),
    modelPreference: $<HTMLSelectElement>("model-preference"),
    answerSource: $<HTMLSelectElement>("answer-source"),
    systemPrompt: $<HTMLTextAreaElement>("system-prompt"),
    promptReset: $<HTMLButtonElement>("prompt-reset"),
    start: $<HTMLButtonElement>("start"),
    stop: $<HTMLButtonElement>("stop"),
    status: $<HTMLDivElement>("status"),
    progress: $<HTMLDivElement>("progress"),
    dotDiameter: $<HTMLInputElement>("dot-diameter"),
    dotOffsetX: $<HTMLInputElement>("dot-offset-x"),
    dotOffsetY: $<HTMLInputElement>("dot-offset-y"),
    stealthPanel: $<HTMLDivElement>("stealth-panel"),
    serverPanel: $<HTMLDivElement>("server-panel"),
    pairPanel: $<HTMLDivElement>("pair-panel"),
    pairCode: $<HTMLInputElement>("pair-code"),
    pairBtn: $<HTMLButtonElement>("pair-btn"),
    moodleUrl: $<HTMLInputElement>("moodle-url"),
    moodleConnect: $<HTMLButtonElement>("moodle-connect"),
  };
}

function syncStealthPanel(r: PopupRefs): void {
  r.stealthPanel.style.display = r.mode.value === "stealth" ? "block" : "none";
}

function populate(r: PopupRefs, settings: ExtensionSettings): void {
  r.mode.value = settings.mode;
  r.backendUrl.value = settings.backendUrl;
  r.backendToken.value = settings.backendToken;
  r.showOverlay.checked = settings.showOverlay;
  r.modelPreference.value = settings.modelPreference;
  r.answerSource.value = settings.answerSource;
  r.systemPrompt.value = settings.systemPrompt;
  r.moodleUrl.value = settings.moodleOrigin;
  r.dotDiameter.value = String(settings.stealthDot.diameter);
  r.dotOffsetX.value = String(settings.stealthDot.offsetX);
  r.dotOffsetY.value = String(settings.stealthDot.offsetY);
  syncStealthPanel(r);
}

function clientFor(r: PopupRefs): BackendClient {
  const s = readFormValues(r);
  return new BackendClient({ backendUrl: s.backendUrl, backendToken: s.backendToken });
}

function showModels(r: PopupRefs, available: ModelInfo[]): void {
  for (const option of Array.from(r.modelPreference.options)) {
    const { label, available: ok } = modelOptionLabel(
      option.value as ModelPreference,
      available,
    );
    option.textContent = label;
    option.disabled = !ok;
  }
}

async function storedSessionId(): Promise<string | null> {
  const stored = await chrome.storage.local.get(["activeSessionId"]);
  return (stored.activeSessionId as string | undefined) ?? null;
}

/** Drop a session the server no longer runs, so «Начать» is never stuck. */
async function reconcileSession(client: BackendClient): Promise<string | null> {
  const sid = await storedSessionId();
  if (!sid) return null;
  try {
    const state = await client.getSession(sid);
    if (state.status === "running") return sid;
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 404) throw err;
  }
  await chrome.runtime.sendMessage({ type: "session-stopped" });
  return null;
}

/** Bring the whole popup in line with the server's actual state. */
async function refresh(r: PopupRefs): Promise<void> {
  const manual = r.answerSource.value === "manual";
  r.serverPanel.hidden = manual;
  r.pairPanel.hidden = true;
  if (manual) {
    applyStatus(
      r.status,
      "Ручной режим: сервер не нужен. Откройте тест — под каждым вопросом появится кнопка «Скопировать вопрос».",
      "ok",
    );
    return;
  }

  const client = clientFor(r);
  r.start.disabled = true;
  try {
    const health = await client.health();
    if (health.api_version !== undefined && health.api_version !== API_VERSION) {
      applyStatus(
        r.status,
        "Версии расширения и сервера не совпадают. Обновите обе части. (VERSION_MISMATCH)",
        "err",
      );
      return;
    }
    showModels(r, await client.models());
    const sid = await reconcileSession(client);
    r.start.disabled = sid !== null;
    applyStatus(
      r.status,
      sid ? "Подсказки включены. Откройте страницу теста." : "Сервер подключён. Нажмите «Начать».",
      "ok",
    );
  } catch (err) {
    const code = errorCode(err);
    if (code === "INVALID_TOKEN" || code === "ORIGIN_NOT_PAIRED") {
      r.pairPanel.hidden = false;
      applyStatus(r.status, "Свяжите расширение с сервером — введите код ниже.", "neutral");
      r.pairCode.focus();
      return;
    }
    applyStatus(r.status, describeError(err), "err");
  }
}

async function onPair(r: PopupRefs): Promise<void> {
  const code = r.pairCode.value.trim();
  if (!/^\d{6}$/.test(code)) {
    applyStatus(r.status, "Код сопряжения — это 6 цифр из окна сервера.", "err");
    return;
  }
  try {
    const token = await clientFor(r).pair(code);
    r.backendToken.value = token;
    await saveSettings({ backendToken: token });
    r.pairCode.value = "";
    await refresh(r);
  } catch (err) {
    applyStatus(r.status, describeError(err), "err");
  }
}

/** Ask for access to the user's Moodle site and start working there. */
async function onConnectMoodle(r: PopupRefs): Promise<void> {
  const typed = r.moodleUrl.value.trim();
  const origin = moodleOriginFromInput(typed);
  if (typed && !origin) {
    applyStatus(r.status, "Не похоже на адрес сайта. Пример: lms.example.edu", "err");
    return;
  }
  if (origin) {
    // Must be called straight from the click, or Chrome refuses the prompt.
    const granted = await chrome.permissions.request({ origins: [`${origin}/*`] });
    if (!granted) {
      applyStatus(r.status, "Без разрешения расширение не увидит тесты на этом сайте.", "err");
      return;
    }
  }
  r.moodleUrl.value = origin ?? "";
  await saveSettings({ moodleOrigin: origin ?? "" });
  await chrome.runtime.sendMessage({ type: "register-host" });
  applyStatus(
    r.status,
    origin
      ? `Сайт ${new URL(origin).host} подключён. Обновите страницу теста.`
      : "Дополнительный сайт отключён.",
    "ok",
  );
}

async function activeTabCmid(): Promise<string | null> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return cmidFromUrl(tab?.url);
}

async function onStart(r: PopupRefs): Promise<void> {
  const settings = readFormValues(r);
  await saveSettings(settings);
  // The content script sends the real cmid with every question; this value
  // only labels the session in history.
  const cmid = r.cmid.value.trim() || (await activeTabCmid()) || "0";
  try {
    const resp = await clientFor(r).startSession({
      mode: settings.mode,
      cmid,
      access_strategy:
        settings.mode === "full_auto" ? "cdp" : "extension_native",
    });
    await chrome.runtime.sendMessage({
      type: "session-started",
      sessionId: resp.session_id,
    });
    r.start.disabled = true;
    applyStatus(r.status, "Подсказки включены. Откройте страницу теста.", "ok");
  } catch (err) {
    applyStatus(r.status, describeError(err), "err");
  }
}

async function onStop(r: PopupRefs): Promise<void> {
  const sessionId = await storedSessionId();
  if (!sessionId) {
    applyStatus(r.status, "Подсказки и так выключены.", "neutral");
    return;
  }
  try {
    await clientFor(r).stopSession(sessionId);
  } catch (err) {
    // A session the server forgot is already stopped as far as we care.
    if (!(err instanceof ApiError) || err.status !== 404) {
      applyStatus(r.status, describeError(err), "err");
      return;
    }
  }
  await chrome.runtime.sendMessage({ type: "session-stopped" });
  r.start.disabled = false;
  applyStatus(r.status, "Подсказки выключены.", "neutral");
}

async function bootstrap(): Promise<void> {
  const r = refs();
  populate(r, await loadSettings(DEFAULT_SETTINGS));

  const stored = await chrome.storage.local.get(["progress"]);
  r.progress.textContent = progressText(stored.progress as QuizProgress | undefined);

  const save = () => void saveSettings(readFormValues(r));
  for (const el of [
    r.mode, r.modelPreference, r.showOverlay, r.systemPrompt,
    r.dotDiameter, r.dotOffsetX, r.dotOffsetY,
  ]) {
    el.addEventListener("change", save);
  }
  r.mode.addEventListener("change", () => syncStealthPanel(r));
  // These change what the popup should show, so re-check the server too.
  for (const el of [r.answerSource, r.backendUrl, r.backendToken]) {
    el.addEventListener("change", () => {
      save();
      void refresh(r);
    });
  }

  r.start.addEventListener("click", () => void onStart(r));
  r.stop.addEventListener("click", () => void onStop(r));
  r.pairBtn.addEventListener("click", () => void onPair(r));
  r.moodleConnect.addEventListener("click", () => void onConnectMoodle(r));
  r.pairCode.addEventListener("keydown", (e) => {
    if (e.key === "Enter") void onPair(r);
  });
  r.promptReset.addEventListener("click", () => {
    r.systemPrompt.value = "";
    void saveSettings({ systemPrompt: "" });
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if ("progress" in changes) {
      r.progress.textContent = progressText(
        changes.progress.newValue as QuizProgress | undefined,
      );
    }
  });

  await refresh(r);
}

if (typeof document !== "undefined" && document.readyState !== "loading") {
  void bootstrap();
} else if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => void bootstrap());
}
