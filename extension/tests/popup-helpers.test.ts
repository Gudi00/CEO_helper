import { describe, expect, it } from "vitest";

import {
  applyStatus,
  cmidFromUrl,
  modelOptionLabel,
  moodleOriginFromInput,
  progressText,
  readFormValues,
  shortSessionId,
} from "@/popup/popup-helpers.js";
import { DEFAULT_SETTINGS } from "@/shared/types.js";

const DOT_DEFAULTS = { dotDiameter: { value: "10" }, dotOffsetX: { value: "0" }, dotOffsetY: { value: "0" } };

describe("readFormValues", () => {
  it("trims inputs and casts mode", () => {
    const settings = readFormValues({
      mode: { value: "full_auto" },
      backendUrl: { value: "  http://x  " },
      backendToken: { value: " tok " },
      showOverlay: { checked: true },
      modelPreference: { value: "accurate" },
      systemPrompt: { value: "  Ты эксперт  " },
      dotDiameter: { value: "15" },
      dotOffsetX: { value: "5" },
      dotOffsetY: { value: "3" },
    });
    expect(settings).toEqual({
      mode: "full_auto",
      backendUrl: "http://x",
      backendToken: "tok",
      showOverlay: true,
      modelPreference: "accurate",
      systemPrompt: "Ты эксперт",
      stealthDot: { diameter: 15, offsetX: 5, offsetY: 3 },
      answerSource: "server",
      moodleOrigin: "",
    });
  });

  it("falls back to default backendUrl on blank input", () => {
    const settings = readFormValues({
      mode: { value: "assist" },
      backendUrl: { value: "   " },
      backendToken: { value: "" },
      showOverlay: { checked: false },
      modelPreference: { value: "fast" },
      systemPrompt: { value: "" },
      ...DOT_DEFAULTS,
    });
    expect(settings.backendUrl).toBe(DEFAULT_SETTINGS.backendUrl);
    expect(settings.showOverlay).toBe(false);
    expect(settings.modelPreference).toBe("fast");
    expect(settings.systemPrompt).toBe("");
  });

  it("clamps diameter to min 1 and handles NaN offset", () => {
    const settings = readFormValues({
      mode: { value: "stealth" },
      backendUrl: { value: "" },
      backendToken: { value: "" },
      showOverlay: { checked: false },
      modelPreference: { value: "fast" },
      systemPrompt: { value: "" },
      dotDiameter: { value: "0" },
      dotOffsetX: { value: "abc" },
      dotOffsetY: { value: "" },
    });
    expect(settings.stealthDot.diameter).toBe(1);
    expect(settings.stealthDot.offsetX).toBe(0);
    expect(settings.stealthDot.offsetY).toBe(0);
  });
});

describe("applyStatus", () => {
  function makeEl() {
    const added = new Set<string>();
    return {
      added,
      el: {
        textContent: null as string | null,
        classList: {
          add: (c: string) => {
            added.add(c);
          },
          remove: (...cls: string[]) => {
            for (const c of cls) added.delete(c);
          },
        },
      },
    };
  }

  it("writes text and clears prior status classes", () => {
    const { el, added } = makeEl();
    added.add("status--ok");
    applyStatus(el, "hello", "neutral");
    expect(el.textContent).toBe("hello");
    expect(added.has("status--ok")).toBe(false);
    expect(added.has("status--err")).toBe(false);
  });

  it("toggles ok and err classes", () => {
    const a = makeEl();
    applyStatus(a.el, "ok", "ok");
    expect(a.added.has("status--ok")).toBe(true);

    const b = makeEl();
    applyStatus(b.el, "fail", "err");
    expect(b.added.has("status--err")).toBe(true);
  });
});

describe("shortSessionId", () => {
  it("renders an 8-char prefix with ellipsis", () => {
    expect(shortSessionId("abcdef0123456789")).toBe("abcdef01…");
  });
});

describe("cmidFromUrl", () => {
  it("reads cmid from an attempt page and id from a view page", () => {
    expect(cmidFromUrl("https://lms.example/mod/quiz/attempt.php?attempt=7&cmid=305095")).toBe("305095");
    expect(cmidFromUrl("https://lms.example/mod/quiz/view.php?id=42")).toBe("42");
  });

  it("returns null outside a quiz or for junk", () => {
    expect(cmidFromUrl("https://lms.example/course/view.php?id=42")).toBeNull();
    expect(cmidFromUrl("not a url")).toBeNull();
    expect(cmidFromUrl(undefined)).toBeNull();
  });
});

describe("progressText", () => {
  it("is empty before any question is seen", () => {
    expect(progressText(undefined)).toBe("");
    expect(progressText({ total: 0, done: 0, failed: 0 })).toBe("");
  });

  it("counts done and failed", () => {
    expect(progressText({ total: 12, done: 3, failed: 0 })).toBe("Вопросов с подсказкой: 3 из 12");
    expect(progressText({ total: 12, done: 3, failed: 2 })).toContain("с ошибкой: 2");
  });
});

describe("modelOptionLabel", () => {
  it("shows the model the server uses, or that it is not configured", () => {
    const available = [{ id: "fast" as const, model: "some-flash" }];
    expect(modelOptionLabel("fast", available)).toEqual({ label: "Быстрая — some-flash", available: true });
    expect(modelOptionLabel("accurate", available).available).toBe(false);
  });
});

describe("moodleOriginFromInput", () => {
  it("accepts a bare host, an origin and a full page address", () => {
    expect(moodleOriginFromInput("lms.example.edu")).toBe("https://lms.example.edu");
    expect(moodleOriginFromInput(" https://lms.example.edu/ ")).toBe("https://lms.example.edu");
    expect(moodleOriginFromInput("http://moodle.local:8080/mod/quiz/view.php?id=1")).toBe(
      "http://moodle.local:8080",
    );
  });

  it("rejects empty and unusable input", () => {
    expect(moodleOriginFromInput("")).toBeNull();
    expect(moodleOriginFromInput("просто текст")).toBeNull();
    expect(moodleOriginFromInput("ftp://lms.example.edu")).toBeNull();
  });
});
