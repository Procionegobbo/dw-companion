import { describe, expect, it } from "vitest";
import { readSse, SseParser, type SseMessage } from "../../src/lib/chat/sse";

function streamFromChunks(chunks: readonly Uint8Array[]): ReadableStream<Uint8Array> {
  const queue = [...chunks];
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      const next = queue.shift();
      if (next) {
        controller.enqueue(next);
      } else {
        controller.close();
      }
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<SseMessage[]> {
  const out: SseMessage[] = [];
  for await (const message of readSse(stream)) {
    out.push(message);
  }
  return out;
}

describe("SseParser", () => {
  it("parses named events", () => {
    const parser = new SseParser();
    const messages = parser.feed('event: status\ndata: {"step":"router"}\n\n');
    expect(messages).toEqual([{ event: "status", data: '{"step":"router"}' }]);
  });

  it("joins multi-line data", () => {
    const parser = new SseParser();
    const messages = parser.feed("event: reply\ndata: line one\ndata: line two\n\n");
    expect(messages).toEqual([{ event: "reply", data: "line one\nline two" }]);
  });

  it("handles CRLF and CR line endings", () => {
    const crlf = new SseParser();
    expect(crlf.feed("event: a\r\ndata: x\r\n\r\n")).toEqual([{ event: "a", data: "x" }]);

    const cr = new SseParser();
    expect(cr.feed("event: a\rdata: x\r\r")).toEqual([{ event: "a", data: "x" }]);
  });

  it("handles events and line endings split across chunks (byte by byte matches one chunk)", () => {
    const whole = 'event: status\r\ndata: {"step":"retrieve"}\r\n\r\n';

    const oneShot = new SseParser();
    const expected = oneShot.feed(whole);

    const incremental = new SseParser();
    const got: SseMessage[] = [];
    for (const char of whole) {
      got.push(...incremental.feed(char));
    }
    expect(got).toEqual(expected);
    expect(got).toEqual([{ event: "status", data: '{"step":"retrieve"}' }]);
  });

  it("ignores comments and unknown fields", () => {
    const parser = new SseParser();
    const messages = parser.feed(
      ": this is a comment\nid: 7\nretry: 1000\nevent: reply\ndata: ok\n\n",
    );
    expect(messages).toEqual([{ event: "reply", data: "ok" }]);
  });

  it("strips one leading space only", () => {
    const parser = new SseParser();
    const messages = parser.feed("event:  reply\ndata:  ok\n\n");
    expect(messages).toEqual([{ event: " reply", data: " ok" }]);
  });

  it("defaults event name to message", () => {
    const parser = new SseParser();
    const messages = parser.feed("data: hello\n\n");
    expect(messages).toEqual([{ event: "message", data: "hello" }]);
  });

  it("drops an unterminated final event", () => {
    const parser = new SseParser();
    const messages = parser.feed("event: reply\ndata: never dispatched");
    expect(messages).toEqual([]);
  });
});

describe("readSse", () => {
  it("decodes a multi-byte character split across two chunks", async () => {
    // "’" (U+2019) is 3 UTF-8 bytes: 0xE2 0x80 0x99. Split it across two chunks.
    const full = new TextEncoder().encode('event: reply\ndata: curly’quote\n\n');
    const splitPoint = full.indexOf(0x80) + 1; // split inside the multi-byte sequence
    const stream = streamFromChunks([full.slice(0, splitPoint), full.slice(splitPoint)]);

    const messages = await collect(stream);
    expect(messages).toEqual([{ event: "reply", data: "curly’quote" }]);
  });

  it("yields messages from a complete stream", async () => {
    const encoder = new TextEncoder();
    const stream = streamFromChunks([
      encoder.encode('event: status\ndata: {"step":"router"}\n\n'),
      encoder.encode('event: reply\ndata: {"ok":true}\n\n'),
    ]);
    const messages = await collect(stream);
    expect(messages).toEqual([
      { event: "status", data: '{"step":"router"}' },
      { event: "reply", data: '{"ok":true}' },
    ]);
  });
});
