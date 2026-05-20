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
 *  - Hold the in-memory WS connection on behalf of UI surfaces.
 */

import {
  ApiError,
  BackendClient,
  TypedWebSocket,
  loadSettings,
} from "@/shared/api-client.js";
import {
  DEFAULT_SETTINGS,
  type AnswerRequest,
  type StartSessionRequest,
  type WSEvent,
} from "@/shared/types.js";

let liveSocket: TypedWebSocket | null = null;
let liveSessionId: string | null = null;

chrome.runtime.onInstalled.addListener(async () => {
  const current = await chrome.storage.local.get(DEFAULT_SETTINGS);
  await chrome.storage.local.set({ ...DEFAULT_SETTINGS, ...current });
});

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
interface OpenWsMsg { type: "open-ws"; sessionId: string }
interface CloseWsMsg { type: "close-ws" }
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

type SwMessage =
  | SessionStartedMsg
  | SessionStoppedMsg
  | OpenWsMsg
  | CloseWsMsg
  | GetSessionMsg
  | BackendAnswerMsg
  | BackendStartSessionMsg
  | BackendStopSessionMsg
  | BackendHealthMsg;

// --- handler ---

async function handleMessage(msg: SwMessage): Promise<unknown> {
  switch (msg.type) {
    case "session-started":
      await chrome.storage.local.set({ activeSessionId: msg.sessionId });
      return { ok: true };
    case "session-stopped":
      await chrome.storage.local.remove("activeSessionId");
      await closeWs();
      return { ok: true };
    case "open-ws":
      await openWs(msg.sessionId);
      return { ok: true };
    case "close-ws":
      await closeWs();
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

async function openWs(sessionId: string): Promise<void> {
  if (liveSocket && liveSessionId === sessionId) return;
  await closeWs();
  const client = await makeClient();
  liveSocket = await client.openWs(sessionId);
  liveSessionId = sessionId;
  liveSocket.on(forwardToTabs);
}

async function closeWs(): Promise<void> {
  liveSocket?.close();
  liveSocket = null;
  liveSessionId = null;
}

function forwardToTabs(event: WSEvent): void {
  void chrome.runtime.sendMessage({ type: "ws-event", event }).catch(() => {
    /* nobody listening — ok */
  });
}
