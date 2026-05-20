/**
 * DOM-independent helpers extracted from `popup.ts` so they can be
 * unit-tested without running the popup bootstrap (which depends on the
 * chrome.* runtime).
 */

import type { ExecutionMode, ExtensionSettings, ModelPreference } from "@/shared/types.js";
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
