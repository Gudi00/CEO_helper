/**
 * Single source of truth for types shared with the Python backend.
 * Must stay aligned with `docs/specs/question-model.md` and
 * `docs/specs/api-contract.yaml`. Keep field names *exactly* the same so
 * JSON round-trips without transformation.
 */

export type ExecutionMode = "assist" | "full_auto" | "step_by_step";

export type AccessStrategy =
  | "extension_native"
  | "cdp"
  | "manual_login"
  | "cookie_export";

export type QuestionType = "single_choice" | "multiple_choice";

export type SessionStatus = "running" | "completed" | "aborted" | "failed";

export interface Option {
  index: number;
  value: string;
  text: string;
}

export interface QuestionMetadata {
  page_number: number;
  attempt_id: string;
  cmid: string;
  has_images: boolean;
}

export interface NormalizedQuestion {
  id: string;
  hash: string;
  type: QuestionType;
  text: string;
  options: Option[];
  metadata: QuestionMetadata;
}

export interface AnswerResult {
  answer_indices: number[];
  confidence: number;
  reasoning: string | null;
  provider: string;
  from_cache: boolean;
  latency_ms?: number | null;
}

// --- API request/response bodies ---

export interface StartSessionRequest {
  mode: ExecutionMode;
  cmid: string;
  access_strategy?: AccessStrategy;
  ai_provider_override?: string;
}

export interface StartSessionResponse {
  session_id: string;
  ws_url: string;
}

export interface AnswerRequest {
  session_id: string;
  question: NormalizedQuestion;
  use_cache?: boolean;
}

export interface SessionState {
  session_id: string;
  mode: ExecutionMode;
  status: SessionStatus;
  cmid: string;
  attempt_id: string | null;
  started_at: string;
  finished_at: string | null;
  score: number | null;
  max_score: number | null;
}

// --- WS event union ---

export type WSEvent =
  | { type: "session_state"; session_id: string; mode: ExecutionMode; status: SessionStatus; current_page: number; questions_answered: number }
  | { type: "question_loaded"; question_id: string; page_number: number }
  | ({ type: "answer_suggested"; question_id: string } & AnswerResult)
  | { type: "engine_clicked"; question_id: string; option_index: number; delay_ms?: number }
  | { type: "page_advanced"; from: number; to: number }
  | { type: "attempt_completed"; session_id: string; score: number | null; max_score: number | null; duration_s?: number }
  | { type: "error"; code: string; message: string; fatal?: boolean; fallback?: string }
  | { type: "log"; level: string; msg: string }
  | { type: "ping" };

// --- Storage shape (chrome.storage.local) ---

export interface ExtensionSettings {
  backendUrl: string; // "http://127.0.0.1:8765"
  backendToken: string;
  mode: ExecutionMode;
  showOverlay: boolean;
}

export const DEFAULT_SETTINGS: ExtensionSettings = {
  backendUrl: "http://127.0.0.1:8765",
  backendToken: "",
  mode: "assist",
  showOverlay: true,
};
