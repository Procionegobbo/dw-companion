import { describe, expect, it } from "vitest";
import { HOME_URL, MOVES_INDEX_URL, moveUrl, sectionUrl } from "../../src/lib/urls";
import { loadRulebook } from "../../src/lib/rulebook";

describe("urls", () => {
  it("exposes the fixed home and moves index urls", () => {
    expect(HOME_URL).toBe("/");
    expect(MOVES_INDEX_URL).toBe("/moves/");
  });

  it("builds section urls from ids", () => {
    expect(sectionUrl("fighter")).toBe("/rules/fighter/");
    expect(sectionUrl("moves/hack-and-slash")).toBe("/rules/moves/hack-and-slash/");
  });

  it("builds move urls from ids", () => {
    expect(moveUrl("hack-and-slash")).toBe("/moves/hack-and-slash/");
  });

  it("rejects ids that do not match the pattern", () => {
    for (const badId of ["Hack and Slash", "../x", ""]) {
      expect(() => sectionUrl(badId)).toThrow();
      expect(() => moveUrl(badId)).toThrow();
    }
  });

  it("every committed section and move maps to a distinct url", () => {
    const rb = loadRulebook();
    const urls = new Set<string>();
    for (const section of rb.sections) {
      const url = sectionUrl(section.id);
      expect(urls.has(url)).toBe(false);
      urls.add(url);
    }
    for (const move of rb.moves) {
      const url = moveUrl(move.id);
      expect(urls.has(url)).toBe(false);
      urls.add(url);
    }
  });
});
