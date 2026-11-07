import { describe, expect, it } from "vitest";
import { categoryLabel, pageTitle, rollLabel } from "../../src/lib/format";
import type { Stat } from "../../src/lib/rulebook";

describe("format", () => {
  it("rollLabel maps every stat", () => {
    const cases: Array<[Stat | null, string]> = [
      ["STR", "+STR"],
      ["DEX", "+DEX"],
      ["CON", "+CON"],
      ["INT", "+INT"],
      ["WIS", "+WIS"],
      ["CHA", "+CHA"],
      ["BOND", "+Bond"],
      ["VARIES", "+stat chosen by how you act"],
      ["NONE", "2d6, no stat added"],
      [null, "Not rolled"],
    ];
    for (const [stat, expected] of cases) {
      expect(rollLabel(stat)).toBe(expected);
    }
  });

  it("categoryLabel maps every category", () => {
    expect(categoryLabel("basic")).toBe("Basic move");
    expect(categoryLabel("special")).toBe("Special move");
    expect(categoryLabel("class")).toBe("Class move");
  });

  it("pageTitle with and without a title", () => {
    expect(pageTitle("Fighter")).toBe("Fighter · Dungeon World Companion");
    expect(pageTitle()).toBe("Dungeon World Companion (unofficial)");
  });
});
