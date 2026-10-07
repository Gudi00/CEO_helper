/**
 * DOM-independent helpers extracted from `popup.ts` so they can be
 * unit-tested without running the popup bootstrap (which depends on the
 * chrome.* runtime).
 */

import type {
  AnswerSource,
  ExecutionMode,
  ExtensionSettings,
  ModelInfo,
  ModelPreference,
  QuizProgress,
} from "@/shared/types.js";
import { DEFAULT_SETTINGS } from "@/shared/types.js";

function parsePx(s: string, fallback: number): number {
  const n = parseInt(s, 10);
  return Number.isNaN(n) ? fallback : n;
}

export interface PopupFormFields {
  mode: ExecutionMode;
  backendUrl: string;
  backendToken: string;
  showOverlay: boolean;
  modelPreference: ModelPreference;
  systemPrompt: string;
  dotDiameter: string;
  dotOffsetX: string;
  dotOffsetY: string;
}

export function readFormValues(fields: {
  mode: { value: string };
  backendUrl: { value: string };
  backendToken: { value: string };
  showOverlay: { checked: boolean };
  modelPreference: { value: string };
  systemPrompt: { value: string };
  dotDiameter: { value: string };
  dotOffsetX: { value: string };
  dotOffsetY: { value: string };
  answerSource?: { value: string };
  moodleUrl?: { value: string };
}): ExtensionSettings {
  return {
    mode: fields.mode.value as ExecutionMode,
    backendUrl: fields.backendUrl.value.trim() || DEFAULT_SETTINGS.backendUrl,
    backendToken: fields.backendToken.value.trim(),
    showOverlay: fields.showOverlay.checked,
    modelPreference: fields.modelPreference.value as ModelPreference,
    systemPrompt: fields.systemPrompt.value.trim(),
    stealthDot: {
      diameter: Math.max(1, parsePx(fields.dotDiameter.value, DEFAULT_SETTINGS.stealthDot.diameter)),
      offsetX: parsePx(fields.dotOffsetX.value, 0),
      offsetY: parsePx(fields.dotOffsetY.value, 0),
    },
    answerSource:
      (fields.answerSource?.value as AnswerSource | undefined) ||
      DEFAULT_SETTINGS.answerSource,
    moodleOrigin: moodleOriginFromInput(fields.moodleUrl?.value ?? "") ?? "",
  };
}

export type StatusKind = "ok" | "err" | "neutral";

export function applyStatus(
  el: { textContent: string | null; classList: { add: (c: string) => void; remove: (...c: string[]) => void } },
  text: string,
  kind: StatusKind = "neutral",
): void {
  el.textContent = text;
  el.classList.remove("status--ok", "status--err");
  if (kind === "ok") el.classList.add("status--ok");
  else if (kind === "err") el.classList.add("status--err");
}

export function shortSessionId(id: string): string {
  return id.slice(0, 8) + "…";
}

/** Quiz id from a Moodle quiz URL (`?cmid=` on attempt pages, `?id=` on view). */
export function cmidFromUrl(url: string | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    if (!u.pathname.includes("/mod/quiz/")) return null;
    return u.searchParams.get("cmid") ?? u.searchParams.get("id");
  } catch {
    return null;
  }
}

export function progressText(p: QuizProgress | undefined): string {
  if (!p || p.total === 0) return "";
  const failed = p.failed > 0 ? `, с ошибкой: ${p.failed}` : "";
  return `Вопросов с подсказкой: ${p.done} из ${p.total}${failed}`;
}

const MODEL_TITLES: Record<ModelPreference, string> = {
  accurate: "Точная",
  fast: "Быстрая",
};

/** Label for a model option, with the model the server will actually use. */
export function modelOptionLabel(
  id: ModelPreference,
  available: ModelInfo[],
): { label: string; available: boolean } {
  const info = available.find((m) => m.id === id);
  return info
    ? { label: `${MODEL_TITLES[id]} — ${info.model}`, available: true }
    : { label: `${MODEL_TITLES[id]} (не настроена)`, available: false };
}

/**
 * Site origin from whatever the user typed: a bare host, an origin, or a
 * full page address. Returns null when it isn't a usable http(s) site.
 */
export function moodleOriginFromInput(input: string): string | null {
  const raw = input.trim();
  if (!raw) return null;
  try {
    const u = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!u.hostname.includes(".") && u.hostname !== "localhost") return null;
    return u.origin;
  } catch {
    return null;
  }
}
