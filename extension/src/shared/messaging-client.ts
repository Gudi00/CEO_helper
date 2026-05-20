/**
 * Messaging-based backend client for content scripts.
 *
 * Since Chrome 117 content scripts do NOT bypass CORS via host_permissions,
 * direct fetch() to localhost will be blocked unless the backend explicitly
 * adds the page origin to CORS. Instead we route through the service
 * worker — fetches there happen in the extension origin and CORS rules
 * permit them via host_permissions.
 *
 * The interface mirrors `BackendClient` for the methods the content
 * script actually uses; expand as needed.
 */

import { ApiError } from "./api-client.js";
import type {
  AnswerRequest,
  AnswerResult,
  StartSessionRequest,
  StartSessionResponse,
} from "./types.js";

interface SwOk<T> { ok: true; data: T }
interface SwOkVoid { ok: true; data?: undefined }
interface SwErr { ok: false; status: number; code: string; message: string }

type SwResponse<T> = SwOk<T> | SwOkVoid | SwErr;

async function sendMessage<T>(msg: object): Promise<T> {
  const resp = (await chrome.runtime.sendMessage(msg)) as SwResponse<T>;
  if (!resp || resp.ok === false) {
    const e = resp as SwErr | undefined;
    throw new ApiError(
      e?.status ?? 0,
      e?.code ?? "UNKNOWN",
      e?.message ?? "no response from service worker",
    );
  }
  return (resp as SwOk<T>).data;
}

export class MessagingBackendClient {
  async answerQuestion(req: AnswerRequest): Promise<AnswerResult> {
    return sendMessage<AnswerResult>({ type: "backend:answer", req });
  }

  async startSession(req: StartSessionRequest): Promise<StartSessionResponse> {
    return sendMessage<StartSessionResponse>({
      type: "backend:start-session",
      req,
    });
  }

  async stopSession(sessionId: string): Promise<void> {
    await sendMessage<undefined>({
      type: "backend:stop-session",
      sessionId,
    });
  }

  async health(): Promise<{ status: string; version: string }> {
    return sendMessage<{ status: string; version: string }>({
      type: "backend:health",
    });
  }
}
