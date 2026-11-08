import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { checkSite } from "../../src/lib/link-check";
import { loadRulebook } from "../../src/lib/rulebook";

const DIST = join(process.cwd(), "dist");

function readDist(relPath: string): string {
  return readFileSync(join(DIST, relPath), "utf-8");
}

function listHtmlFilesRecursive(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...listHtmlFilesRecursive(full));
    } else if (entry.isFile() && entry.name.endsWith(".html")) {
      files.push(full);
    }
  }
  return files;
}

beforeAll(() => {
  if (!existsSync(join(DIST, "index.html"))) {
    throw new Error("site/dist not found: run `npm run build` first");
  }
});

describe("built site", () => {
  it("every section_id and move_id resolves and every internal link works", () => {
    const report = checkSite(DIST, loadRulebook());
    expect(report.problems).toEqual([]);
  });

  it("home links every chapter", () => {
    const rb = loadRulebook();
    const home = readDist("index.html");
    const chapters = rb.sections.filter((section) => section.parent_id === null);
    expect(chapters.length).toBeGreaterThan(0);
    for (const chapter of chapters) {
      expect(home).toContain(`href="/rules/${chapter.id}/"`);
    }
  });

  it("moves index links every move", () => {
    const rb = loadRulebook();
    const movesIndex = readDist(join("moves", "index.html"));
    expect(rb.moves.length).toBeGreaterThan(0);
    for (const move of rb.moves) {
      expect(movesIndex).toContain(`href="/moves/${move.id}/"`);
    }
  });

  it("hack-and-slash card shows trigger, roll, bands and unstated miss", () => {
    const card = readDist(join("moves", "hack-and-slash", "index.html"));
    expect(card).toContain("When you attack an enemy in melee");
    expect(card).toContain("+STR");
    expect(card).toContain("10+ (strong hit)");
    expect(card).toContain("Not stated by this move.");
    expect(card).toContain('href="/rules/moves/hack-and-slash/"');
  });

  it("last-breath card shows its miss", () => {
    const card = readDist(join("moves", "last-breath", "index.html"));
    expect(card).toContain("On a miss, your fate is sealed.");
    expect(card).toContain("2d6, no stat added");
  });

  it("encumbrance card has no outcomes block", () => {
    const card = readDist(join("moves", "encumbrance", "index.html"));
    expect(card).toContain("Not rolled");
    expect(card).not.toContain("10+ (strong hit)");
  });

  it("move section links back to its card", () => {
    const section = readDist(join("rules", "moves", "hack-and-slash", "index.html"));
    expect(section).toContain('href="/moves/hack-and-slash/"');
  });

  it("breadcrumbs list ancestors", () => {
    const section = readDist(join("rules", "moves", "hack-and-slash", "index.html"));
    expect(section).toContain('href="/rules/moves/"');
    expect(section).toContain('href="/rules/moves/basic-moves/"');
  });

  it("fighter chapter shows class stats", () => {
    const chapter = readDist(join("rules", "fighter", "index.html"));
    expect(chapter).toContain("Max HP");
    expect(chapter).toContain("10 + Constitution");
    expect(chapter).toContain("d10");
    expect(chapter).toContain("12 + Str");
  });

  it("stat table renders as html table", () => {
    const files = listHtmlFilesRecursive(join(DIST, "rules", "character-creation"));
    const hasTable = files.some((file) => {
      const html = readFileSync(file, "utf-8");
      return html.includes("<table>") && html.includes("<th>Score</th>");
    });
    expect(hasTable).toBe(true);
  });

  it("every page declares lang and has a main landmark", () => {
    const files = listHtmlFilesRecursive(DIST);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const html = readFileSync(file, "utf-8");
      expect(html).toContain('<html lang="en"');
      expect(html).toContain('id="main"');
    }
  });

  it("assistant page renders the chat widget", () => {
    const page = readDist(join("assistant", "index.html"));
    expect(page).toContain('id="chat-form"');
    expect(page).toContain('maxlength="500"');
    expect(page).toContain('role="log"');
    expect(page).toContain('role="status"');
    expect(page).toContain('<label for="chat-message">');
    expect(page).toContain("<script type=\"module\"");
  });

  it("header links the assistant on every page", () => {
    const files = listHtmlFilesRecursive(DIST);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const html = readFileSync(file, "utf-8");
      expect(html).toContain('href="/assistant/"');
    }
  });
});
