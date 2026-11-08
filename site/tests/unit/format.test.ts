import { describe, expect, it } from "vitest";
import { bandLabel, categoryLabel, pageTitle, rollLabel } from "../../src/lib/format";
import type { Stat } from "../../src/lib/rulebook";
import type { Band } from "../../src/lib/chat/protocol";

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

  it("bandLabel maps every band", () => {
    const cases: Array<[Band, string]> = [
      ["strong_hit", "10+ (strong hit)"],
      ["weak_hit", "7–9 (weak hit)"],
      ["miss", "6- (miss)"],
    ];
    for (const [band, expected] of cases) {
      expect(bandLabel(band)).toBe(expected);
    }
  });
});
