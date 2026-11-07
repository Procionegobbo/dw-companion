import { describe, expect, it } from "vitest";
import { ancestorsOf, loadRulebook, parseRulebook, RulebookError } from "../../src/lib/rulebook";

function validSection(overrides: Record<string, unknown> = {}) {
  return {
    id: "intro",
    chapter: "intro",
    title: "Introduction",
    slug: "introduction",
    parent_id: null,
    order: 0,
    text_markdown: "Some text.",
    ...overrides,
  };
}

function validMove(overrides: Record<string, unknown> = {}) {
  return {
    id: "test-move",
    name: "Test Move",
    category: "basic",
    class: null,
    stat: "STR",
    trigger: "When you test",
    outcomes: {
      strong_hit: "On a 10+, it works.",
      weak_hit: "On a 7-9, it mostly works.",
      miss: null,
    },
    body_markdown: "When you test, roll+Str.",
    section_id: "intro",
    ...overrides,
  };
}

describe("rulebook", () => {
  it("loads the committed data without errors", () => {
    const rb = loadRulebook();
    expect(rb.moves).toHaveLength(21);
    expect(rb.classes).toHaveLength(8);
    expect(rb.sections.length).toBeGreaterThanOrEqual(37);
    expect(rb.sections.filter((section) => section.parent_id === null)).toHaveLength(37);
  });

  it("repeated calls return the same memoised result", () => {
    expect(loadRulebook()).toBe(loadRulebook());
  });

  it("sorts sections by order", () => {
    const rb = loadRulebook();
    const orders = rb.sections.map((section) => section.order);
    const sorted = [...orders].sort((a, b) => a - b);
    expect(orders).toEqual(sorted);
  });

  it("childrenOf lists children in order", () => {
    const rb = loadRulebook();
    const children = rb.childrenOf.get("moves/basic-moves") ?? [];
    expect(children.length).toBeGreaterThan(0);
    const orders = children.map((section) => section.order);
    const sorted = [...orders].sort((a, b) => a - b);
    expect(orders).toEqual(sorted);
    expect(children[0]?.id).toBe("moves/hack-and-slash");
  });

  it("indexes moves by section id", () => {
    const rb = loadRulebook();
    expect(rb.moveBySectionId.get("moves/hack-and-slash")?.id).toBe("hack-and-slash");
  });

  it("indexes classes by section id", () => {
    const rb = loadRulebook();
    expect(rb.classBySectionId.get("fighter")?.base_damage).toBe("d10");
  });

  it("ancestorsOf returns root first", () => {
    const rb = loadRulebook();
    const ancestors = ancestorsOf(rb, "moves/hack-and-slash");
    expect(ancestors.map((section) => section.id)).toEqual(["moves", "moves/basic-moves"]);
  });

  it("rejects unknown keys", () => {
    const raw = {
      sections: [{ ...validSection(), extra: "nope" }],
      moves: [],
      classes: [],
    };
    expect(() => parseRulebook(raw)).toThrow(RulebookError);
  });

  it("rejects a dangling parent_id", () => {
    const raw = {
      sections: [validSection({ parent_id: "missing" })],
      moves: [],
      classes: [],
    };
    expect(() => parseRulebook(raw)).toThrow(RulebookError);
  });

  it("rejects a move whose section_id does not exist", () => {
    const raw = {
      sections: [validSection()],
      moves: [validMove({ section_id: "missing" })],
      classes: [],
    };
    expect(() => parseRulebook(raw)).toThrow(RulebookError);
  });

  it("rejects duplicate section ids", () => {
    const raw = {
      sections: [validSection(), validSection({ order: 1 })],
      moves: [],
      classes: [],
    };
    expect(() => parseRulebook(raw)).toThrow(RulebookError);
  });

  it("rejects a malformed section id", () => {
    const raw = {
      sections: [validSection({ id: "Moves/Hack" })],
      moves: [],
      classes: [],
    };
    expect(() => parseRulebook(raw)).toThrow(RulebookError);
  });

  it("rejects an invalid stat", () => {
    const raw = {
      sections: [validSection()],
      moves: [validMove({ stat: "LUCK" })],
      classes: [],
    };
    expect(() => parseRulebook(raw)).toThrow(RulebookError);
  });

  it("rejects outcomes missing the miss key", () => {
    const raw = {
      sections: [validSection()],
      moves: [
        validMove({
          outcomes: { strong_hit: "On a 10+.", weak_hit: "On a 7-9." },
        }),
      ],
      classes: [],
    };
    expect(() => parseRulebook(raw)).toThrow(RulebookError);
  });

  it("reports every problem in one error", () => {
    const raw = {
      sections: [validSection({ id: "Moves/Hack" })],
      moves: [validMove({ stat: "LUCK" })],
      classes: [],
    };
    let caught: unknown;
    try {
      parseRulebook(raw);
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(RulebookError);
    const message = (caught as Error).message;
    expect(message).toContain("Moves/Hack");
    expect(message).toContain("LUCK");
  });
});
