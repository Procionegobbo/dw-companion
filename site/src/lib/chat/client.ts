// Chat transport (spec 008 D6, D16): fetch() over a relative, same-origin path, read as a
// stream through the project's own SSE parser. Never EventSource (GET-only, auto-reconnect would
// re-send and re-bill a turn).

import { readSse } from "./sse";
import {
  httpErrorSchema,
  replySchema,
  statusSchema,
  streamErrorSchema,
  type ChatReply,
} from "./protocol";
import { INTERRUPTED, NETWORK_FAILURE, UNAVAILABLE } from "./copy";

export const CHAT_ENDPOINT = "/api/chat";
export const MAX_MESSAGE_CHARS = 500;

export interface ChatRequestBody {
  message: string;
  roll: boolean;
  modifier: number | null;
  session_id: string;
}

export type ChatOutcome =
  | { type: "reply"; reply: ChatReply }
  | { type: "failure"; code: string; message: string };

function failure(code: string, message: string): ChatOutcome {
  return { type: "failure", code, message };
}

function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === "AbortError";
}

async function failureFromErrorResponse(response: Response): Promise<ChatOutcome> {
  const text = await response.text().catch(() => "");
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    return failure(`http_${response.status}`, UNAVAILABLE);
  }
  const parsed = httpErrorSchema.safeParse(body);
  if (!parsed.success) {
    return failure(`http_${response.status}`, UNAVAILABLE);
  }
  return failure(parsed.data.error.code, parsed.data.error.message);
}

export async function sendChat(
  body: ChatRequestBody,
  opts?: { fetch?: typeof fetch; onStatus?: (step: string) => void; signal?: AbortSignal },
): Promise<ChatOutcome> {
  const doFetch = opts?.fetch ?? fetch;

  let response: Response;
  try {
    response = await doFetch(CHAT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal: opts?.signal,
    });
  } catch (err) {
    if (isAbortError(err)) throw err;
    return failure("network", NETWORK_FAILURE);
  }

  if (!response.ok) {
    return failureFromErrorResponse(response);
  }

  const contentType = response.headers.get("Content-Type") ?? "";
  if (!response.body || !contentType.startsWith("text/event-stream")) {
    return failure("malformed", INTERRUPTED);
  }

  try {
    for await (const message of readSse(response.body)) {
      let data: unknown;
      try {
        data = JSON.parse(message.data);
      } catch {
        if (message.event === "status" || message.event === "reply" || message.event === "error") {
          return failure("malformed", INTERRUPTED);
        }
        continue; // unknown event, unparseable data: ignored
      }

      if (message.event === "status") {
        const parsed = statusSchema.safeParse(data);
        if (!parsed.success) return failure("malformed", INTERRUPTED);
        opts?.onStatus?.(parsed.data.step);
        continue;
      }
      if (message.event === "reply") {
        const parsed = replySchema.safeParse(data);
        if (!parsed.success) return failure("malformed", INTERRUPTED);
        return { type: "reply", reply: parsed.data };
      }
      if (message.event === "error") {
        const parsed = streamErrorSchema.safeParse(data);
        if (!parsed.success) return failure("malformed", INTERRUPTED);
        return failure(parsed.data.code, parsed.data.message);
      }
      // Any other event name is ignored (forward-compatible, D1).
    }
  } catch {
    return failure("interrupted", INTERRUPTED);
  }

  return failure("interrupted", INTERRUPTED);
}
