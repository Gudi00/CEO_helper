/**
 * Thin HTTP wrapper around the local backend (127.0.0.1:8765).
 * Reads `backendUrl` / `backendToken` from chrome.storage at construction
 * — for tests we accept them directly.
 */

import type {
  AnswerRequest,
  AnswerResult,
  ExecutionMode,
  ExtensionSettings,
  HealthInfo,
  ModelInfo,
  SessionState,
  StartSessionRequest,
  StartSessionResponse,
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

  async health(): Promise<HealthInfo> {
    const r = await this.fetch(`${this.backendUrl}/api/health`);
    if (!r.ok) throw await this._toApiError(r);
    return (await r.json()) as HealthInfo;
  }

  /** Trade a one-time pairing code for the backend token. */
  async pair(code: string): Promise<string> {
    const r = await this.fetch(`${this.backendUrl}/api/pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    if (!r.ok) throw await this._toApiError(r);
    return ((await r.json()) as { token: string }).token;
  }

  async models(): Promise<ModelInfo[]> {
    return this._get<ModelInfo[]>("/api/models");
  }

  async getSession(sessionId: string): Promise<SessionState> {
    return this._get<SessionState>(`/api/session/${sessionId}`);
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

  private async _get<T>(path: string): Promise<T> {
    const r = await this.fetch(`${this.backendUrl}${path}`, {
      headers: { "X-Backend-Token": this.token },
    });
    if (!r.ok) throw await this._toApiError(r);
    return (await r.json()) as T;
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
