import { describe, expect, it } from "vitest";

import {
  applyStatus,
  readFormValues,
  shortSessionId,
} from "@/popup/popup-helpers.js";
import { DEFAULT_SETTINGS } from "@/shared/types.js";

describe("readFormValues", () => {
  it("trims inputs and casts mode", () => {
    const settings = readFormValues({
      mode: { value: "full_auto" },
      backendUrl: { value: "  http://x  " },
      backendToken: { value: " tok " },
      showOverlay: { checked: true },
    });
    expect(settings).toEqual({
      mode: "full_auto",
      backendUrl: "http://x",
      backendToken: "tok",
      showOverlay: true,
    });
  });

  it("falls back to default backendUrl on blank input", () => {
    const settings = readFormValues({
      mode: { value: "assist" },
      backendUrl: { value: "   " },
      backendToken: { value: "" },
      showOverlay: { checked: false },
    });
    expect(settings.backendUrl).toBe(DEFAULT_SETTINGS.backendUrl);
    expect(settings.showOverlay).toBe(false);
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
