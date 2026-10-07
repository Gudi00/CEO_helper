/**
 * Background service worker (MV3).
 *
 * Responsibilities:
 *  - On install: seed default settings.
 *  - **Proxy all backend HTTP calls** for content scripts. Since Chrome 117
 *    content scripts no longer bypass CORS via host_permissions, so the
 *    backend would have to special-case every page origin. Routing through
 *    the service worker means the fetch happens in the extension's origin
 *    and the backend only needs to allow `chrome-extension://*`.
 *  - Relay popup → content-script messages (session lifecycle).
 */

import {
  ApiError,
  BackendClient,
  loadSettings,
} from "@/shared/api-client.js";
import {
  DEFAULT_SETTINGS,
  type AnswerRequest,
  type StartSessionRequest,
} from "@/shared/types.js";

chrome.runtime.onInstalled.addListener(async () => {
  const current = await chrome.storage.local.get(DEFAULT_SETTINGS);
  await chrome.storage.local.set({ ...DEFAULT_SETTINGS, ...current });
  // Built file names change with every build, so re-register after an update.
  await registerCustomHost();
});

const CUSTOM_SCRIPT_ID = "custom-moodle";

/**
 * Run the content script on the user's own Moodle site as well as the
 * built-in one. The host permission is requested by the popup beforehand.
 */
async function registerCustomHost(): Promise<void> {
  const { moodleOrigin } = await loadSettings(DEFAULT_SETTINGS);
  const existing = await chrome.scripting.getRegisteredContentScripts({
    ids: [CUSTOM_SCRIPT_ID],
  });
  if (existing.length > 0) {
    await chrome.scripting.unregisterContentScripts({ ids: [CUSTOM_SCRIPT_ID] });
  }
  if (!moodleOrigin) return;
  const js = chrome.runtime.getManifest().content_scripts?.[0]?.js;
  if (!js) return;
  await chrome.scripting.registerContentScripts([
    {
      id: CUSTOM_SCRIPT_ID,
      matches: [`${moodleOrigin}/mod/quiz/*`],
      js,
      runAt: "document_idle",
    },
  ]);
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  void handleMessage(msg)
    .then(sendResponse)
    .catch((err: unknown) => {
      const wrapped =
        err instanceof ApiError
          ? { ok: false, status: err.status, code: err.code, message: err.message }
          : { ok: false, status: 0, code: "UNKNOWN", message: String(err) };
      sendResponse(wrapped);
    });
  return true; // async response
});

// --- message types ---

interface SessionStartedMsg { type: "session-started"; sessionId: string }
interface SessionStoppedMsg { type: "session-stopped" }
interface GetSessionMsg { type: "get-session" }

interface BackendAnswerMsg {
  type: "backend:answer";
  req: AnswerRequest;
}
interface BackendStartSessionMsg {
  type: "backend:start-session";
  req: StartSessionRequest;
}
interface BackendStopSessionMsg {
  type: "backend:stop-session";
  sessionId: string;
}
interface BackendHealthMsg { type: "backend:health" }
interface RegisterHostMsg { type: "register-host" }

type SwMessage =
  | SessionStartedMsg
  | SessionStoppedMsg
  | GetSessionMsg
  | BackendAnswerMsg
  | BackendStartSessionMsg
  | BackendStopSessionMsg
  | BackendHealthMsg
  | RegisterHostMsg;

// --- handler ---

async function handleMessage(msg: SwMessage): Promise<unknown> {
  switch (msg.type) {
    case "session-started":
      await chrome.storage.local.set({ activeSessionId: msg.sessionId });
      return { ok: true };
    case "session-stopped":
      await chrome.storage.local.remove("activeSessionId");
      return { ok: true };
    case "register-host":
      await registerCustomHost();
      return { ok: true };
    case "get-session": {
      const stored = await chrome.storage.local.get(["activeSessionId"]);
      return { sessionId: stored["activeSessionId"] ?? null };
    }
    case "backend:answer": {
      const settings = await loadSettings(DEFAULT_SETTINGS);
      const fullReq: AnswerRequest = {
        ...msg.req,
        model_preference: settings.modelPreference,
        system_prompt: settings.systemPrompt || null,
      };
      const client = await makeClient();
      const data = await client.answerQuestion(fullReq);
      return { ok: true, data };
    }
    case "backend:start-session": {
      const client = await makeClient();
      const data = await client.startSession(msg.req);
      return { ok: true, data };
    }
    case "backend:stop-session": {
      const client = await makeClient();
      await client.stopSession(msg.sessionId);
      return { ok: true };
    }
    case "backend:health": {
      const client = await makeClient();
      const data = await client.health();
      return { ok: true, data };
    }
    default:
      throw new Error(`unknown message type: ${(msg as { type: string }).type}`);
  }
}

async function makeClient(): Promise<BackendClient> {
  const settings = await loadSettings(DEFAULT_SETTINGS);
  return new BackendClient({
    backendUrl: settings.backendUrl,
    backendToken: settings.backendToken,
  });
}
