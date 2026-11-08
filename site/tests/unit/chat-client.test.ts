import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import {
  CHAT_ENDPOINT,
  MAX_MESSAGE_CHARS,
  sendChat,
  type ChatRequestBody,
} from "../../src/lib/chat/client";

const fixture = JSON.parse(
  readFileSync(
    new URL(
      "../../../backend/tests/fixtures/chat_reply_examples.json",
      import.meta.url,
    ),
  ).toString(),
) as Record<string, unknown>;

const REQUEST_BODY: ChatRequestBody = {
  message: "How does Hack and Slash work?",
  roll: false,
  modifier: null,
  session_id: "ab".repeat(16),
};

function sseResponse(body: string, headers: Record<string, string> = {}): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream", ...headers },
  });
}

function sseEvent(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function fakeFetch(response: Response | (() => Response)): [typeof fetch, { calls: unknown[] }] {
  const calls: unknown[] = [];
  const fn = vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return typeof response === "function" ? response() : response;
  });
  return [fn as unknown as typeof fetch, { calls }];
}

describe("sendChat", () => {
  it("posts the request body as json with sse accept header", async () => {
    const [fetchFn, record] = fakeFetch(
      sseResponse(sseEvent("reply", fixture.rules_answer)),
    );
    await sendChat(REQUEST_BODY, { fetch: fetchFn });

    expect(record.calls).toHaveLength(1);
    const call = record.calls[0] as { url: string; init: RequestInit };
    expect(call.url).toBe(CHAT_ENDPOINT);
    expect(call.init.method).toBe("POST");
    const headers = call.init.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers["Accept"]).toBe("text/event-stream");
    expect(call.init.body).toBe(JSON.stringify(REQUEST_BODY));
  });

  it("reports status steps then returns the reply", async () => {
    const body =
      sseEvent("status", { step: "router" }) +
      sseEvent("status", { step: "retrieve" }) +
      sseEvent("reply", fixture.rules_answer);
    const [fetchFn] = fakeFetch(sseResponse(body));
    const steps: string[] = [];

    const outcome = await sendChat(REQUEST_BODY, {
      fetch: fetchFn,
      onStatus: (step) => steps.push(step),
    });

    expect(steps).toEqual(["router", "retrieve"]);
    expect(outcome).toEqual({ type: "reply", reply: fixture.rules_answer });
  });

  it("ignores unknown events", async () => {
    const body = sseEvent("delta", { text: "partial" }) + sseEvent("reply", fixture.rules_answer);
    const [fetchFn] = fakeFetch(sseResponse(body));

    const outcome = await sendChat(REQUEST_BODY, { fetch: fetchFn });
    expect(outcome).toEqual({ type: "reply", reply: fixture.rules_answer });
  });

  it("maps an error event to a failure", async () => {
    const body = sseEvent("error", { code: "internal_error", message: "Something broke." });
    const [fetchFn] = fakeFetch(sseResponse(body));

    const outcome = await sendChat(REQUEST_BODY, { fetch: fetchFn });
    expect(outcome).toEqual({
      type: "failure",
      code: "internal_error",
      message: "Something broke.",
    });
  });

  it("maps http error bodies for 429 and 503", async () => {
    const [fetch429] = fakeFetch(
      new Response(JSON.stringify({ error: { code: "rate_limited", message: "Slow down." } }), {
        status: 429,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const outcome429 = await sendChat(REQUEST_BODY, { fetch: fetch429 });
    expect(outcome429).toEqual({ type: "failure", code: "rate_limited", message: "Slow down." });

    const [fetch503] = fakeFetch(
      new Response(
        JSON.stringify({ error: { code: "budget_exhausted", message: "No budget left." } }),
        { status: 503, headers: { "Content-Type": "application/json" } },
      ),
    );
    const outcome503 = await sendChat(REQUEST_BODY, { fetch: fetch503 });
    expect(outcome503).toEqual({
      type: "failure",
      code: "budget_exhausted",
      message: "No budget left.",
    });
  });

  it("falls back when the error body is not json", async () => {
    const [fetchFn] = fakeFetch(
      new Response("<html>Bad Gateway</html>", {
        status: 502,
        headers: { "Content-Type": "text/html" },
      }),
    );
    const outcome = await sendChat(REQUEST_BODY, { fetch: fetchFn });
    expect(outcome.type).toBe("failure");
    if (outcome.type === "failure") {
      expect(outcome.code).toBe("http_502");
      expect(outcome.message).toBe("The assistant is unavailable right now. Please try again in a moment.");
    }
  });

  it("maps network errors", async () => {
    const fetchFn = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;

    const outcome = await sendChat(REQUEST_BODY, { fetch: fetchFn });
    expect(outcome).toEqual({
      type: "failure",
      code: "network",
      message: "Couldn't reach the assistant. Check your connection and try again.",
    });
  });

  it("fails when the stream ends without a reply", async () => {
    const [fetchFn] = fakeFetch(sseResponse(sseEvent("status", { step: "router" })));
    const outcome = await sendChat(REQUEST_BODY, { fetch: fetchFn });
    expect(outcome.type).toBe("failure");
    if (outcome.type === "failure") expect(outcome.code).toBe("interrupted");
  });

  it("fails on malformed reply json", async () => {
    const [fetchFn] = fakeFetch(sseResponse("event: reply\ndata: {not valid json\n\n"));
    const outcome = await sendChat(REQUEST_BODY, { fetch: fetchFn });
    expect(outcome).toEqual({
      type: "failure",
      code: "malformed",
      message: "The answer was interrupted. Please try again.",
    });
  });

  it("fails on a non sse response", async () => {
    const [fetchFn] = fakeFetch(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const outcome = await sendChat(REQUEST_BODY, { fetch: fetchFn });
    expect(outcome).toEqual({
      type: "failure",
      code: "malformed",
      message: "The answer was interrupted. Please try again.",
    });
  });

  it("MAX_MESSAGE_CHARS is 500", () => {
    expect(MAX_MESSAGE_CHARS).toBe(500);
  });
});
