/**
 * Popup UI logic: load settings, health-check the backend, start/stop a
 * session, persist current sessionId via the service worker.
 */

import { ApiError, BackendClient, loadSettings, saveSettings } from "@/shared/api-client.js";
import { DEFAULT_SETTINGS, type ExtensionSettings } from "@/shared/types.js";
import { applyStatus, readFormValues, shortSessionId } from "./popup-helpers.js";

const $ = <T extends HTMLElement = HTMLElement>(id: string): T =>
  document.getElementById(id) as T;

interface PopupRefs {
  mode: HTMLSelectElement;
  cmid: HTMLInputElement;
  backendUrl: HTMLInputElement;
  backendToken: HTMLInputElement;
  showOverlay: HTMLInputElement;
  modelPreference: HTMLSelectElement;
  systemPrompt: HTMLTextAreaElement;
  promptReset: HTMLButtonElement;
  start: HTMLButtonElement;
  stop: HTMLButtonElement;
  status: HTMLDivElement;
  dotDiameter: HTMLInputElement;
  dotOffsetX: HTMLInputElement;
  dotOffsetY: HTMLInputElement;
  stealthPanel: HTMLDivElement;
}

function refs(): PopupRefs {
  return {
    mode: $<HTMLSelectElement>("mode"),
    cmid: $<HTMLInputElement>("cmid"),
    backendUrl: $<HTMLInputElement>("backend-url"),
    backendToken: $<HTMLInputElement>("backend-token"),
    showOverlay: $<HTMLInputElement>("show-overlay"),
    modelPreference: $<HTMLSelectElement>("model-preference"),
    systemPrompt: $<HTMLTextAreaElement>("system-prompt"),
    promptReset: $<HTMLButtonElement>("prompt-reset"),
    start: $<HTMLButtonElement>("start"),
    stop: $<HTMLButtonElement>("stop"),
    status: $<HTMLDivElement>("status"),
    dotDiameter: $<HTMLInputElement>("dot-diameter"),
    dotOffsetX: $<HTMLInputElement>("dot-offset-x"),
    dotOffsetY: $<HTMLInputElement>("dot-offset-y"),
    stealthPanel: $<HTMLDivElement>("stealth-panel"),
  };
}

function syncStealthPanel(refs: PopupRefs): void {
  refs.stealthPanel.style.display = refs.mode.value === "stealth" ? "block" : "none";
}

function populate(refs: PopupRefs, settings: ExtensionSettings): void {
  refs.mode.value = settings.mode;
  refs.backendUrl.value = settings.backendUrl;
  refs.backendToken.value = settings.backendToken;
  refs.showOverlay.checked = settings.showOverlay;
  refs.modelPreference.value = settings.modelPreference;
  refs.systemPrompt.value = settings.systemPrompt;
  refs.dotDiameter.value = String(settings.stealthDot.diameter);
  refs.dotOffsetX.value = String(settings.stealthDot.offsetX);
  refs.dotOffsetY.value = String(settings.stealthDot.offsetY);
  syncStealthPanel(refs);
}

async function checkHealth(client: BackendClient, status: HTMLDivElement): Promise<void> {
  try {
    const h = await client.health();
    applyStatus(status, `Backend ok (v${h.version})`, "ok");
  } catch (err) {
    applyStatus(status, "Backend offline: запустите uvicorn", "err");
    console.warn("[popup] health failed", err);
  }
}

async function onStart(refs: PopupRefs): Promise<void> {
  const settings = readFormValues(refs);
  await saveSettings(settings);
  const cmid = refs.cmid.value.trim();
  if (!cmid) {
    applyStatus(refs.status, "Введите cmid теста", "err");
    return;
  }
  const client = new BackendClient({
    backendUrl: settings.backendUrl,
    backendToken: settings.backendToken,
  });
  try {
    const resp = await client.startSession({
      mode: settings.mode,
      cmid,
      access_strategy:
        settings.mode === "full_auto" ? "cdp" : "extension_native",
    });
    await chrome.runtime.sendMessage({
      type: "session-started",
      sessionId: resp.session_id,
    });
    applyStatus(refs.status, `Сессия запущена: ${shortSessionId(resp.session_id)}`, "ok");
  } catch (err) {
    const msg = err instanceof ApiError ? `${err.code}: ${err.message}` : String(err);
    applyStatus(refs.status, `Не удалось стартовать: ${msg}`, "err");
  }
}

async function onStop(refs: PopupRefs): Promise<void> {
  const settings = readFormValues(refs);
  const sessionId =
    ((await chrome.storage.local.get(["activeSessionId"]))[
      "activeSessionId"
    ] as string | undefined) ?? null;
  if (!sessionId) {
    applyStatus(refs.status, "Активной сессии нет", "neutral");
    return;
  }
  const client = new BackendClient({
    backendUrl: settings.backendUrl,
    backendToken: settings.backendToken,
  });
  try {
    await client.stopSession(sessionId);
    await chrome.runtime.sendMessage({ type: "session-stopped" });
    applyStatus(refs.status, "Сессия остановлена", "ok");
  } catch (err) {
    const msg = err instanceof ApiError ? `${err.code}: ${err.message}` : String(err);
    applyStatus(refs.status, `Не удалось остановить: ${msg}`, "err");
  }
}

async function bootstrap(): Promise<void> {
  const r = refs();
  const settings = await loadSettings(DEFAULT_SETTINGS);
  populate(r, settings);

  const client = new BackendClient({
    backendUrl: settings.backendUrl,
    backendToken: settings.backendToken,
  });

  const active = await chrome.storage.local.get(["activeSessionId"]);
  const sid = active.activeSessionId as string | undefined;
  if (sid) {
    applyStatus(r.status, `Активная сессия: ${shortSessionId(sid)}`, "ok");
    r.start.disabled = true;
  } else {
    void checkHealth(client, r.status);
  }

  r.mode.addEventListener("change", () => syncStealthPanel(r));
  r.start.addEventListener("click", () => void onStart(r));
  r.stop.addEventListener("click", () => void onStop(r));
  r.promptReset.addEventListener("click", () => {
    r.systemPrompt.value = "";
    void saveSettings({ systemPrompt: "" });
  });

  // React to other popup instances / SW updating storage live.
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local" || !("activeSessionId" in changes)) return;
    const next = changes.activeSessionId.newValue as string | undefined;
    if (next) {
      applyStatus(r.status, `Активная сессия: ${shortSessionId(next)}`, "ok");
      r.start.disabled = true;
    } else {
      applyStatus(r.status, "Сессия остановлена", "neutral");
      r.start.disabled = false;
    }
  });
}

if (typeof document !== "undefined" && document.readyState !== "loading") {
  void bootstrap();
} else if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => void bootstrap());
}
