/**
 * TypedWebSocket auth handshake + event dispatch via a hand-rolled fake
 * WebSocket. happy-dom does NOT provide a usable WebSocket so we plug a
 * stub directly into BackendClient.openWs.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BackendClient, TypedWebSocket } from "@/shared/api-client.js";
import type { WSEvent } from "@/shared/types.js";

class FakeWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  readyState = 0;
  sent: string[] = [];
  private listeners = new Map<string, Set<(ev: Event) => void>>();

  constructor(public url: string) {
    queueMicrotask(() => this._emit("open", new Event("open")));
  }

  addEventListener(t: string, fn: (ev: Event) => void): void {
    if (!this.listeners.has(t)) this.listeners.set(t, new Set());
    this.listeners.get(t)!.add(fn);
  }
  removeEventListener(t: string, fn: (ev: Event) => void): void {
    this.listeners.get(t)?.delete(fn);
  }
  send(data: string): void {
    this.sent.push(data);
  }
  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
    this._emit("close", new Event("close"));
  }

  // Test helpers
  fire(data: WSEvent): void {
    const ev = new MessageEvent("message", { data: JSON.stringify(data) });
    this._emit("message", ev);
  }
  fireRaw(raw: string): void {
    this._emit("message", new MessageEvent("message", { data: raw }));
  }
  fireError(): void {
    this._emit("error", new Event("error"));
  }
  private _emit(type: string, ev: Event): void {
    this.listeners.get(type)?.forEach((fn) => fn(ev));
  }
}

const realWS = globalThis.WebSocket;

beforeEach(() => {
  // @ts-expect-error replace constructor
  globalThis.WebSocket = FakeWebSocket;
});

afterEach(() => {
  globalThis.WebSocket = realWS;
});

describe("TypedWebSocket via BackendClient.openWs", () => {
  it("opens, sends auth handshake, and routes parsed events", async () => {
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "tok",
    });
    const ws = await client.openWs("sess-1");
    // url derived from backendUrl
    const inner = (ws as unknown as { ws: FakeWebSocket }).ws;
    expect(inner.url).toBe("ws://127.0.0.1:8765/ws/sess-1");
    // auth message was sent
    expect(JSON.parse(inner.sent[0]!)).toEqual({ type: "auth", token: "tok" });

    // Subscriber receives parsed events
    const seen: WSEvent[] = [];
    const off = ws.on((e) => seen.push(e));
    inner.fire({
      type: "answer_suggested",
      question_id: "q1",
      answer_indices: [0],
      confidence: 0.9,
      reasoning: null,
      provider: "stub",
      from_cache: false,
    });
    expect(seen[0]).toMatchObject({ type: "answer_suggested", question_id: "q1" });

    off();
    inner.fire({ type: "ping" });
    expect(seen).toHaveLength(1);
  });

  it("ignores messages that are not valid JSON", async () => {
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "tok",
    });
    const ws = await client.openWs("sess-1");
    const inner = (ws as unknown as { ws: FakeWebSocket }).ws;
    const fn = vi.fn();
    ws.on(fn);
    inner.fireRaw("not json {{{");
    expect(fn).not.toHaveBeenCalled();
  });

  it("send() serializes payload as JSON", async () => {
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "tok",
    });
    const ws = await client.openWs("sess-1");
    const inner = (ws as unknown as { ws: FakeWebSocket }).ws;
    inner.sent.length = 0;
    ws.send({ type: "confirm_answer", question_id: "q1" });
    expect(JSON.parse(inner.sent[0]!)).toEqual({
      type: "confirm_answer",
      question_id: "q1",
    });
  });

  it("close() clears listeners and forwards to underlying socket", async () => {
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "tok",
    });
    const ws = await client.openWs("sess-1");
    const inner = (ws as unknown as { ws: FakeWebSocket }).ws;
    const fn = vi.fn();
    ws.on(fn);
    ws.close();
    expect(inner.readyState).toBe(FakeWebSocket.CLOSED);
    inner.fire({ type: "ping" });
    expect(fn).not.toHaveBeenCalled();
  });

  it("rejects when the underlying socket errors during handshake", async () => {
    class FailingWS extends FakeWebSocket {
      constructor(url: string) {
        super(url);
        queueMicrotask(() => this.fireError());
      }
    }
    // @ts-expect-error inject failing ctor
    globalThis.WebSocket = FailingWS;
    const client = new BackendClient({
      backendUrl: "http://127.0.0.1:8765",
      backendToken: "tok",
    });
    // FailingWS fires "open" before "error" — auth completes anyway. So
    // to verify the error path we construct the wrapper directly with a
    // socket that only errors.
    class OnlyErrorWS {
      static OPEN = 1;
      readyState = 0;
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      constructor(_url: string) {}
      addEventListener(t: string, fn: (e: Event) => void): void {
        if (t === "error") queueMicrotask(() => fn(new Event("error")));
      }
      removeEventListener(): void {}
      send(): void {}
      close(): void {}
    }
    await expect(
      TypedWebSocket.create(new OnlyErrorWS("x") as unknown as WebSocket, "t"),
    ).rejects.toBeInstanceOf(Event);
    // Restore for other tests
    // @ts-expect-error restore
    globalThis.WebSocket = FakeWebSocket;
  });
});
