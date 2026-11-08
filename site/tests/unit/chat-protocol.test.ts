import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  httpErrorSchema,
  replySchema,
  type ChatReply,
} from "../../src/lib/chat/protocol";

const fixture = JSON.parse(
  readFileSync(
    new URL(
      "../../../backend/tests/fixtures/chat_reply_examples.json",
      import.meta.url,
    ),
  ).toString(),
) as Record<string, unknown>;

function assertDefined<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) {
    throw new Error("expected a value, got null/undefined");
  }
  return value;
}

describe("replySchema", () => {
  it("accepts every fixture reply", () => {
    for (const [name, reply] of Object.entries(fixture)) {
      const result = replySchema.safeParse(reply);
      expect(result.success, `${name}: ${JSON.stringify(result.error?.issues)}`).toBe(true);
    }
  });

  it("rejects a citation url that differs from sectionUrl", () => {
    const reply = structuredClone(fixture.rules_answer) as ChatReply;
    const [firstCitation] = reply.citations;
    assertDefined(firstCitation).url = "javascript:alert(1)";
    expect(replySchema.safeParse(reply).success).toBe(false);
  });

  it("rejects a move url that differs from moveUrl", () => {
    const reply = structuredClone(fixture.move_rolled_with_modifier) as ChatReply;
    assertDefined(reply.move).url = "/moves/some-other-move/";
    expect(replySchema.safeParse(reply).success).toBe(false);
  });

  it("rejects an unknown kind", () => {
    const reply = { ...(fixture.rules_answer as object), kind: "bogus" };
    expect(replySchema.safeParse(reply).success).toBe(false);
  });

  it("rejects dice outside 1-6", () => {
    const reply = structuredClone(fixture.move_rolled_with_modifier) as ChatReply;
    assertDefined(reply.move).roll = { dice: [0, 7], modifier: 1, total: 7 };
    expect(replySchema.safeParse(reply).success).toBe(false);
  });

  it("strips unknown keys", () => {
    const reply = { ...(fixture.rules_answer as object), intent: "rules_question" };
    const result = replySchema.safeParse(reply);
    expect(result.success).toBe(true);
    expect(result.data && "intent" in result.data).toBe(false);
  });
});

describe("httpErrorSchema", () => {
  it("parses a valid http error body", () => {
    const result = httpErrorSchema.safeParse({
      error: { code: "rate_limited", message: "Slow down." },
    });
    expect(result.success).toBe(true);
    expect(result.data).toEqual({ error: { code: "rate_limited", message: "Slow down." } });
  });

  it("rejects an error body missing message", () => {
    expect(httpErrorSchema.safeParse({ error: { code: "x" } }).success).toBe(false);
  });

  it("rejects a body with no error key", () => {
    expect(httpErrorSchema.safeParse({ detail: "Not Found" }).success).toBe(false);
  });
});
