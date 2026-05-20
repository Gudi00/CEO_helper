/**
 * chrome.storage helpers: returns defaults when chrome is unavailable,
 * merges stored values over defaults, and saves patch objects.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { loadSettings, saveSettings } from "@/shared/api-client.js";
import {
  DEFAULT_SETTINGS,
  type ExtensionSettings,
} from "@/shared/types.js";

interface ChromeStub {
  storage: {
    local: { get: ReturnType<typeof vi.fn>; set: ReturnType<typeof vi.fn> };
  };
}

const g = globalThis as unknown as { chrome?: ChromeStub };
const originalChrome = g.chrome;

afterEach(() => {
  g.chrome = originalChrome;
});

describe("loadSettings", () => {
  it("returns defaults verbatim when chrome.storage is unavailable", async () => {
    g.chrome = undefined;
    const got = await loadSettings(DEFAULT_SETTINGS);
    expect(got).toEqual(DEFAULT_SETTINGS);
  });

  it("merges stored values over defaults", async () => {
    const partial: Partial<ExtensionSettings> = {
      backendToken: "secret",
      mode: "full_auto",
    };
    g.chrome = {
      storage: {
        local: {
          get: vi.fn().mockResolvedValue(partial),
          set: vi.fn().mockResolvedValue(undefined),
        },
      },
    };
    const got = await loadSettings(DEFAULT_SETTINGS);
    expect(got.backendUrl).toBe(DEFAULT_SETTINGS.backendUrl);
    expect(got.backendToken).toBe("secret");
    expect(got.mode).toBe("full_auto");
  });

  it("passes defaults to chrome.storage.local.get so it returns those if unset", async () => {
    const get = vi.fn().mockResolvedValue({});
    g.chrome = { storage: { local: { get, set: vi.fn() } } };
    await loadSettings(DEFAULT_SETTINGS);
    expect(get).toHaveBeenCalledWith(DEFAULT_SETTINGS);
  });
});

describe("saveSettings", () => {
  it("forwards the patch to chrome.storage.local.set", async () => {
    const set = vi.fn().mockResolvedValue(undefined);
    g.chrome = { storage: { local: { get: vi.fn(), set } } };
    await saveSettings({ backendToken: "new" });
    expect(set).toHaveBeenCalledWith({ backendToken: "new" });
  });

  it("is a no-op when chrome is undefined", async () => {
    g.chrome = undefined;
    await expect(saveSettings({ backendToken: "x" })).resolves.toBeUndefined();
  });
});
