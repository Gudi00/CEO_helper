/**
 * Thin HTTP + WebSocket wrapper around the local backend (127.0.0.1:8765).
 * Reads `backendUrl` / `backendToken` from chrome.storage at construction
 * — for tests we accept them directly.
 */

import type {
  AnswerRequest,
  AnswerResult,
  ExecutionMode,
  ExtensionSettings,
  StartSessionRequest,
  StartSessionResponse,
  WSEvent,
} from "./types.js";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClientConfig {
  backendUrl: string;
  backendToken: string;
  /** Injectable for tests; defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

export class BackendClient {
  private readonly backendUrl: string;
  private readonly token: string;
  private readonly fetch: typeof fetch;

  constructor(config: ApiClientConfig) {
    this.backendUrl = config.backendUrl.replace(/\/+$/, "");
    this.token = config.backendToken;
    this.fetch = config.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  async health(): Promise<{ status: string; version: string }> {
    const r = await this.fetch(`${this.backendUrl}/api/health`);
    if (!r.ok) throw await this._toApiError(r);
    return (await r.json()) as { status: string; version: string };
  }

  async startSession(req: StartSessionRequest): Promise<StartSessionResponse> {
    return this._post<StartSessionResponse>("/api/session/start", req);
  }

  async stopSession(sessionId: string): Promise<void> {
    const r = await this.fetch(
      `${this.backendUrl}/api/session/${sessionId}/stop`,
      { method: "POST", headers: { "X-Backend-Token": this.token } },
    );
    if (!r.ok && r.status !== 204) throw await this._toApiError(r);
  }

  async answerQuestion(req: AnswerRequest): Promise<AnswerResult> {
    return this._post<AnswerResult>("/api/question/answer", req);
  }

  async submitFeedback(questionHash: string, wasCorrect: boolean, sessionId?: string): Promise<void> {
    const r = await this.fetch(
      `${this.backendUrl}/api/question/${questionHash}/feedback`,
      {
        method: "POST",
        headers: this._jsonHeaders(),
        body: JSON.stringify({ was_correct: wasCorrect, session_id: sessionId ?? null }),
      },
    );
    if (!r.ok && r.status !== 204) throw await this._toApiError(r);
  }

  /**
   * Open a WS connection and authenticate. The returned EventTarget-like
   * object emits typed events; caller must `close()` it when done.
   */
  async openWs(sessionId: string): Promise<TypedWebSocket> {
    const wsUrl =
      this.backendUrl.replace(/^http/, "ws") + `/ws/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    return await TypedWebSocket.create(ws, this.token);
  }

  private async _post<T>(path: string, body: unknown): Promise<T> {
    const r = await this.fetch(`${this.backendUrl}${path}`, {
      method: "POST",
      headers: this._jsonHeaders(),
      body: JSON.stringify(body),
    });
    if (!r.ok) throw await this._toApiError(r);
    return (await r.json()) as T;
  }

  private _jsonHeaders(): Record<string, string> {
    return {
      "Content-Type": "application/json",
      "X-Backend-Token": this.token,
    };
  }

  private async _toApiError(r: Response): Promise<ApiError> {
    let code = "HTTP_" + r.status;
    let message = r.statusText;
    try {
      const data = (await r.json()) as { detail?: { code?: string; message?: string } };
      if (data?.detail) {
        code = data.detail.code ?? code;
        message = data.detail.message ?? message;
      }
    } catch {
      /* response not JSON */
    }
    return new ApiError(r.status, code, message);
  }
}

export type WSListener = (event: WSEvent) => void;

/**
 * Wraps a WebSocket, sends the auth handshake, and re-emits parsed
 * messages as typed events. Auto-reconnect is left to the caller for now
 * (the extension popup decides whether to retry).
 */
export class TypedWebSocket {
  private listeners = new Set<WSListener>();

  private constructor(private readonly ws: WebSocket) {
    ws.addEventListener("message", (ev) => {
      try {
        const data = JSON.parse(ev.data as string) as WSEvent;
        for (const fn of this.listeners) fn(data);
      } catch {
        /* swallow parse errors — server-side bug, not ours */
      }
    });
  }

  static async create(ws: WebSocket, token: string): Promise<TypedWebSocket> {
    await new Promise<void>((resolve, reject) => {
      const onOpen = () => {
        ws.removeEventListener("open", onOpen);
        ws.removeEventListener("error", onError);
        resolve();
      };
      const onError = (e: Event) => {
        ws.removeEventListener("open", onOpen);
        ws.removeEventListener("error", onError);
        reject(e);
      };
      ws.addEventListener("open", onOpen);
      ws.addEventListener("error", onError);
    });
    ws.send(JSON.stringify({ type: "auth", token }));
    return new TypedWebSocket(ws);
  }

  on(listener: WSListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  send(message: { type: string } & Record<string, unknown>): void {
    this.ws.send(JSON.stringify(message));
  }

  close(): void {
    this.listeners.clear();
    this.ws.close();
  }
}

// --- chrome.storage helpers (no-op when chrome is undefined, e.g. tests) -

export async function loadSettings(
  defaults: ExtensionSettings,
): Promise<ExtensionSettings> {
  if (typeof chrome === "undefined" || !chrome?.storage?.local) {
    return defaults;
  }
  const stored = await chrome.storage.local.get(defaults);
  return { ...defaults, ...(stored as Partial<ExtensionSettings>) };
}

export async function saveSettings(
  patch: Partial<ExtensionSettings>,
): Promise<void> {
  if (typeof chrome === "undefined" || !chrome?.storage?.local) return;
  await chrome.storage.local.set(patch);
}

export function buildSettingsForMode(mode: ExecutionMode): Partial<ExtensionSettings> {
  return { mode };
}
