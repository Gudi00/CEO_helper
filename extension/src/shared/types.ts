/**
 * Single source of truth for types shared with the Python backend.
 * Must stay aligned with `docs/specs/question-model.md` and
 * `docs/specs/api-contract.yaml`. Keep field names *exactly* the same so
 * JSON round-trips without transformation.
 */

export type ExecutionMode = "assist" | "full_auto" | "step_by_step" | "stealth";

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

export type QuestionImageMime = "image/png" | "image/jpeg" | "image/webp";

export interface QuestionImage {
  mime: QuestionImageMime;
  /** base64 without the data: prefix */
  data: string;
}

export interface NormalizedQuestion {
  id: string;
  hash: string;
  type: QuestionType;
  text: string;
  options: Option[];
  metadata: QuestionMetadata;
  images?: QuestionImage[];
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
}

export type ModelPreference = "fast" | "accurate";

/** Where answers come from: the local server, or pasted in by the user. */
export type AnswerSource = "server" | "manual";

/** Must equal the backend's API_VERSION (see /api/health). */
export const API_VERSION = 1;

export interface HealthInfo {
  status: string;
  version: string;
  api_version?: number;
}

export interface ModelInfo {
  id: ModelPreference;
  model: string;
}

/** Written to chrome.storage.local by the content script, read by the popup. */
export interface QuizProgress {
  total: number;
  done: number;
  failed: number;
}

export interface AnswerRequest {
  session_id: string;
  question: NormalizedQuestion;
  use_cache?: boolean;
  model_preference?: ModelPreference;
  system_prompt?: string | null;
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

// --- Storage shape (chrome.storage.local) ---

export interface StealthDotSettings {
  diameter: number; // px, default 10
  offsetX: number;  // px horizontal shift from natural position
  offsetY: number;  // px vertical shift (margin-top) from label
}

export interface ExtensionSettings {
  backendUrl: string; // "http://127.0.0.1:8765"
  backendToken: string;
  mode: ExecutionMode;
  showOverlay: boolean;
  modelPreference: ModelPreference;
  systemPrompt: string; // empty string = use backend default
  stealthDot: StealthDotSettings;
  answerSource: AnswerSource;
  /** Extra Moodle site, e.g. "https://lms.example.edu"; empty = built-in only. */
  moodleOrigin: string;
}

export const DEFAULT_SETTINGS: ExtensionSettings = {
  backendUrl: "http://127.0.0.1:8765",
  backendToken: "",
  mode: "assist",
  showOverlay: true,
  modelPreference: "accurate",
  systemPrompt: "",
  stealthDot: { diameter: 10, offsetX: 0, offsetY: 0 },
  answerSource: "server",
  moodleOrigin: "",
};

/** Below this confidence an answer is shown as doubtful. */
export const LOW_CONFIDENCE = 0.6;
