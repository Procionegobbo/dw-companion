// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { URL } from "node:url";
import { describe, expect, it } from "vitest";
import {
  diceText,
  renderFailure,
  renderReply,
  renderUserMessage,
  segmentText,
} from "../../src/lib/chat/render";
import type { ChatReply, MoveCardPayload } from "../../src/lib/chat/protocol";

// `import.meta.url` is assigned to a variable before being passed to `new URL` because Vite's
// static asset-URL analysis rewrites the inline pattern `new URL("...", import.meta.url)` under
// the happy-dom test environment, producing an http: URL instead of the real file: one.
interface Fixtures {
  rules_answer: ChatReply;
  rules_not_found: ChatReply;
  move_rolled_with_modifier: ChatReply;
  move_rolled_without_modifier: ChatReply;
}

const moduleUrl = import.meta.url;
const fixture = JSON.parse(
  readFileSync(
    new URL("../../../backend/tests/fixtures/chat_reply_examples.json", moduleUrl),
  ).toString(),
) as Fixtures;

function assertDefined<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) {
    throw new Error("expected a value, got null/undefined");
  }
  return value;
}

describe("segmentText", () => {
  it("segments markers into numbered citations", () => {
    const reply = fixture.rules_answer;
    const segments = segmentText(reply.text, reply.citations);
    expect(segments.map((s) => s.type)).toEqual(["text", "citation", "text", "citation", "text"]);
    expect(segments[1]).toMatchObject({ type: "citation", index: 1 });
    expect(segments[3]).toMatchObject({ type: "citation", index: 2 });
  });

  it("drops markers that are not citations", () => {
    const segments = segmentText("before [[unknown/id]] after", []);
    expect(segments).toEqual([{ type: "text", text: "before " }, { type: "text", text: " after" }]);
  });
});

describe("diceText", () => {
  it("formats a roll with a positive modifier", () => {
    expect(diceText({ dice: [4, 5], modifier: 1, total: 10 })).toBe("4 + 5 + 1 = 10");
  });

  it("formats negative modifiers", () => {
    expect(diceText({ dice: [3, 3], modifier: -1, total: 5 })).toBe("3 + 3 - 1 = 5");
  });

  it("formats a roll without a modifier", () => {
    expect(diceText({ dice: [3, 5], modifier: null, total: null })).toBe(
      "3 + 5 = 8, before your modifier",
    );
  });
});

describe("renderReply", () => {
  it("renders paragraphs and citation links", () => {
    const li = renderReply(document, fixture.rules_answer);
    const paragraphs = li.querySelectorAll(".chat-text p");
    expect(paragraphs).toHaveLength(2);

    const links = li.querySelectorAll(".chat-text a");
    expect(links).toHaveLength(2);
    const [firstLink, secondLink] = links;
    const first = assertDefined(firstLink);
    const second = assertDefined(secondLink);
    expect(first.getAttribute("href")).toBe("/rules/moves/hack-and-slash/");
    expect(first.textContent).toBe("[1]");
    expect(first.getAttribute("target")).toBe("_blank");
    expect(first.getAttribute("rel")).toBe("noopener noreferrer");
    expect(first.getAttribute("aria-label")?.startsWith("Source 1: Hack and Slash")).toBe(true);
    expect(second.getAttribute("href")).toBe("/rules/moves/defy-danger/");
  });

  it("renders a sources list titled Sources", () => {
    const li = renderReply(document, fixture.rules_answer);
    const title = li.querySelector(".chat-sources-title");
    expect(title?.textContent).toBe("Sources");
    expect(li.querySelectorAll(".chat-sources li")).toHaveLength(2);
  });

  it("titles not-found citations as closest sections", () => {
    const li = renderReply(document, fixture.rules_not_found);
    const title = li.querySelector(".chat-sources-title");
    expect(title?.textContent).toBe("Closest sections in the rules");
  });

  it("renders the move card with roll and result band", () => {
    const li = renderReply(document, fixture.move_rolled_with_modifier);
    const card = assertDefined(li.querySelector(".move-card"));

    const headingLink = card.querySelector("h3 a");
    expect(headingLink?.getAttribute("href")).toBe("/moves/hack-and-slash/");

    const facts = [...card.querySelectorAll(".move-facts dt, .move-facts dd")].map(
      (el) => el.textContent,
    );
    const rollIndex = facts.indexOf("Roll");
    expect(facts[rollIndex + 1]).toBe("+STR");
    const diceIndex = facts.indexOf("Dice");
    expect(facts[diceIndex + 1]).toBe("4 + 5 + 1 = 10");

    const resultDt = card.querySelector(".outcomes dt.is-result");
    expect(resultDt?.textContent).toBe("10+ (strong hit) (your roll)");
    const missDd = [...card.querySelectorAll(".outcomes dd")].find(
      (dd) => dd.textContent === "Not stated by this move.",
    );
    expect(missDd).toBeDefined();
  });

  it("renders a roll without modifier", () => {
    const li = renderReply(document, fixture.move_rolled_without_modifier);
    const card = assertDefined(li.querySelector(".move-card"));
    const facts = [...card.querySelectorAll(".move-facts dt, .move-facts dd")].map(
      (el) => el.textContent,
    );
    expect(facts[facts.indexOf("Roll") + 1]).toBe("+stat chosen by how you act");
    expect(facts[facts.indexOf("Dice") + 1]).toBe("3 + 5 = 8, before your modifier");
    expect(card.querySelector(".outcomes .is-result")).toBeNull();
  });

  it("renders no outcomes block for a non-rolled move", () => {
    const move: MoveCardPayload = {
      move_id: "hack-and-slash",
      name: "Hack and Slash",
      url: "/moves/hack-and-slash/",
      trigger: "When you attack an enemy in melee",
      stat: null,
      roll_stat: null,
      outcomes: null,
      roll: null,
      outcome: null,
      bands_by_modifier: [],
    };
    const reply: ChatReply = { ...fixture.move_rolled_with_modifier, move };
    const li = renderReply(document, reply);
    const card = assertDefined(li.querySelector(".move-card"));
    expect(card.querySelector(".outcomes")).toBeNull();
    const facts = [...card.querySelectorAll(".move-facts dt, .move-facts dd")].map(
      (el) => el.textContent,
    );
    expect(facts[facts.indexOf("Roll") + 1]).toBe("Not rolled");
  });

  it("escapes html in all text", () => {
    const reply: ChatReply = {
      trace_id: "f".repeat(32),
      kind: "rules_answer",
      text: "<img src=x onerror=alert(1)>",
      citations: [
        { section_id: "moves/hack-and-slash", title: "<b>bold</b>", url: "/rules/moves/hack-and-slash/" },
      ],
      move: null,
    };
    const li = renderReply(document, reply);
    expect(li.querySelector("img")).toBeNull();
    expect(li.querySelector("b")).toBeNull();
    expect(li.querySelector(".chat-text p")?.textContent).toBe(
      "<img src=x onerror=alert(1)>",
    );
    const sourceLink = li.querySelector(".chat-sources a");
    expect(sourceLink?.textContent).toContain("<b>bold</b>");
  });

  it("marks error replies", () => {
    const reply: ChatReply = {
      trace_id: "e".repeat(32),
      kind: "error",
      text: "Something went wrong.",
      citations: [],
      move: null,
    };
    const li = renderReply(document, reply);
    expect(li.classList.contains("chat-error")).toBe(true);
    const firstParagraph = li.querySelector(".chat-text p");
    expect(firstParagraph?.textContent?.startsWith("Error: ")).toBe(true);
  });
});

describe("renderUserMessage", () => {
  it("renders a user message item", () => {
    const li = renderUserMessage(document, "How does Hack and Slash work?");
    expect(li.className).toBe("chat-user");
    expect(li.textContent).toBe("You: How does Hack and Slash work?");
  });
});

describe("renderFailure", () => {
  it("renders a failure item", () => {
    const li = renderFailure(document, "The answer was interrupted. Please try again.");
    expect(li.classList.contains("chat-error")).toBe(true);
    expect(li.dataset.kind).toBe("failure");
    expect(li.textContent).toBe(
      "Assistant: Error: The answer was interrupted. Please try again.",
    );
  });
});
