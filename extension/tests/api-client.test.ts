/**
 * BackendClient unit tests with an injectable fetch stub. We exercise
 * URL/body construction, header propagation, and error mapping.
 */

import { describe, expect, it, vi } from "vitest";
import { ApiError, BackendClient } from "@/shared/api-client.js";
import type { NormalizedQuestion } from "@/shared/types.js";

function makeFetchStub(handlers: Record<string, (init?: RequestInit) => Response | Promise<Response>>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const key = (init?.method ?? "GET") + " " + url;
    const handler = handlers[key];
    if (!handler) {
      throw new Error(`unexpected fetch ${key}; known: ${Object.keys(handlers).join(", ")}`);
    }
    return handler(init);
  });
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

function makeQuestion(): NormalizedQuestion {
  return {
    id: "q1:1",
    hash: "0".repeat(64),
    type: "single_choice",
    text: "x?",
    options: [
      { index: 0, value: "1", text: "a" },
      { index: 1, value: "2", text: "b" },
    ],
    metadata: {
      page_number: 0,
      attempt_id: "1",
      cmid: "1",
      has_images: false,
    },
  };
}

describe("BackendClient.health", () => {
  it("returns parsed status payload", async () => {
    const fetchImpl = makeFetchStub({
      "GET http://127.0.0.1:8765/api/health": () =>
        jsonResponse({ status: "ok", version: "0.1.0" }),
    });
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "tok",
      fetchImpl,
    });
    const h = await client.health();
    expect(h.status).toBe("ok");
    expect(h.version).toBe("0.1.0");
  });

  it("strips trailing slashes from backendUrl", async () => {
    const fetchImpl = makeFetchStub({
      "GET http://127.0.0.1:8765/api/health": () =>
        jsonResponse({ status: "ok", version: "0.1.0" }),
    });
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765///",
      backendToken: "tok",
      fetchImpl,
    });
    await client.health();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});

describe("BackendClient.startSession", () => {
  it("posts JSON body with token header", async () => {
    let captured: RequestInit | undefined;
    const fetchImpl = makeFetchStub({
      "POST http://127.0.0.1:8765/api/session/start": (init) => {
        captured = init;
        return jsonResponse(
          { session_id: "abc-123", ws_url: "ws://127.0.0.1:8765/ws/abc-123" },
          { status: 201 },
        );
      },
    });
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "secret-tok",
      fetchImpl,
    });
    const resp = await client.startSession({
      mode: "assist",
      cmid: "305095",
      access_strategy: "extension_native",
    });
    expect(resp.session_id).toBe("abc-123");
    expect(resp.ws_url).toContain("abc-123");

    const headers = captured?.headers as Record<string, string>;
    expect(headers["X-Backend-Token"]).toBe("secret-tok");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(captured?.body as string)).toEqual({
      mode: "assist",
      cmid: "305095",
      access_strategy: "extension_native",
    });
  });
});

describe("BackendClient.answerQuestion", () => {
  it("returns the AnswerResult", async () => {
    const fetchImpl = makeFetchStub({
      "POST http://127.0.0.1:8765/api/question/answer": () =>
        jsonResponse({
          answer_indices: [0],
          confidence: 0.9,
          reasoning: "stub",
          provider: "stub",
          from_cache: false,
        }),
    });
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "t",
      fetchImpl,
    });
    const r = await client.answerQuestion({
      session_id: "s",
      question: makeQuestion(),
    });
    expect(r.answer_indices).toEqual([0]);
    expect(r.confidence).toBeCloseTo(0.9);
  });
});

describe("BackendClient error mapping", () => {
  it("converts FastAPI detail payload into ApiError", async () => {
    const fetchImpl = makeFetchStub({
      "POST http://127.0.0.1:8765/api/session/start": () =>
        new Response(
          JSON.stringify({ detail: { code: "BAD_REQUEST", message: "missing cmid" } }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
    });
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "t",
      fetchImpl,
    });
    await expect(
      client.startSession({ mode: "assist", cmid: "" }),
    ).rejects.toMatchObject({
      status: 422,
      code: "BAD_REQUEST",
      message: "missing cmid",
    });
  });

  it("falls back to HTTP_<status> code when body is not JSON", async () => {
    const fetchImpl = makeFetchStub({
      "GET http://127.0.0.1:8765/api/health": () =>
        new Response("oops", { status: 500 }),
    });
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "t",
      fetchImpl,
    });
    try {
      await client.health();
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(500);
      expect((err as ApiError).code).toBe("HTTP_500");
    }
  });
});

describe("BackendClient.stopSession + feedback", () => {
  it("stop accepts 204 No Content", async () => {
    const fetchImpl = makeFetchStub({
      "POST http://127.0.0.1:8765/api/session/abc/stop": () =>
        new Response(null, { status: 204 }),
    });
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "t",
      fetchImpl,
    });
    await expect(client.stopSession("abc")).resolves.toBeUndefined();
  });

  it("feedback posts was_correct and session_id", async () => {
    let captured: RequestInit | undefined;
    const fetchImpl = makeFetchStub({
      "POST http://127.0.0.1:8765/api/question/aaa/feedback": (init) => {
        captured = init;
        return new Response(null, { status: 204 });
      },
    });
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "t",
      fetchImpl,
    });
    await client.submitFeedback("aaa", true, "sess-1");
    expect(JSON.parse(captured?.body as string)).toEqual({
      was_correct: true,
      session_id: "sess-1",
    });
  });
});
