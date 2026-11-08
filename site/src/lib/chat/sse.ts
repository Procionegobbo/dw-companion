// Server-Sent Events parser, following the WHATWG event-stream parsing rules (spec 008 D6):
// the widget talks to fetch()'s own ReadableStream rather than EventSource, so it needs its own
// parser. Pure and incremental: `feed` can be called with arbitrarily small chunks (even single
// bytes once decoded to text) and must yield the same messages as one large chunk would.

export interface SseMessage {
  event: string;
  data: string;
}

/**
 * Splits text into lines on \n, \r\n or \r, including terminators split across separate
 * `push` calls. A \r is treated as ending a line as soon as it is seen; if the very next
 * character turns out to be \n (whether in this chunk or the start of the next one), it is
 * swallowed as the second half of that same CRLF terminator rather than starting a blank line.
 */
class LineSplitter {
  private buffer = "";
  private pendingCr = false;

  push(chunk: string): string[] {
    const lines: string[] = [];
    let start = 0;
    let i = 0;

    if (this.pendingCr && chunk.length > 0 && chunk[0] === "\n") {
      start = 1;
      i = 1;
    }
    this.pendingCr = false;

    while (i < chunk.length) {
      const ch = chunk[i];
      if (ch === "\n") {
        lines.push(this.buffer + chunk.slice(start, i));
        this.buffer = "";
        i += 1;
        start = i;
      } else if (ch === "\r") {
        lines.push(this.buffer + chunk.slice(start, i));
        this.buffer = "";
        i += 1;
        start = i;
        if (i >= chunk.length) {
          this.pendingCr = true;
        } else if (chunk[i] === "\n") {
          i += 1;
          start = i;
        }
      } else {
        i += 1;
      }
    }
    this.buffer += chunk.slice(start);
    return lines;
  }
}

export class SseParser {
  private readonly splitter = new LineSplitter();
  private eventName: string | undefined;
  private dataLines: string[] = [];

  /** Feeds one chunk of decoded text and returns any messages it completes. */
  feed(chunk: string): SseMessage[] {
    const messages: SseMessage[] = [];
    for (const line of this.splitter.push(chunk)) {
      if (line === "") {
        if (this.dataLines.length > 0) {
          messages.push({ event: this.eventName ?? "message", data: this.dataLines.join("\n") });
        }
        this.eventName = undefined;
        this.dataLines = [];
        continue;
      }
      if (line.startsWith(":")) continue; // comment line

      const colonIndex = line.indexOf(":");
      const field = colonIndex === -1 ? line : line.slice(0, colonIndex);
      let value = colonIndex === -1 ? "" : line.slice(colonIndex + 1);
      if (value.startsWith(" ")) value = value.slice(1);

      if (field === "event") {
        this.eventName = value;
      } else if (field === "data") {
        this.dataLines.push(value);
      }
      // Other fields (id, retry, ...) are ignored per spec 008 D1/D6.
    }
    return messages;
  }
}

/** Reads a fetch response body as a sequence of SSE messages. */
export async function* readSse(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<SseMessage> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  const parser = new SseParser();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const message of parser.feed(decoder.decode(value, { stream: true }))) {
        yield message;
      }
    }
    const tail = decoder.decode();
    if (tail) {
      for (const message of parser.feed(tail)) {
        yield message;
      }
    }
  } finally {
    // Covers both natural completion and a consumer stopping early (e.g. sendChat returning as
    // soon as it has a reply): cancelling releases the underlying connection either way.
    try {
      await reader.cancel();
    } catch {
      // Already closed/cancelled; nothing to do.
    }
  }
}
