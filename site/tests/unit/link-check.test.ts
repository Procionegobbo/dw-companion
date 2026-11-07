import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";
import { checkSite } from "../../src/lib/link-check";
import { parseRulebook } from "../../src/lib/rulebook";

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

const FOOTER_HTML = `
  <footer>
    <a href="https://creativecommons.org/licenses/by/3.0/">CC BY 3.0</a>
    <a href="https://github.com/Sagelt/Dungeon-World">source</a>
    <p>This is an unofficial fan project.</p>
  </footer>
`;

function page(body: string, includeFooter: boolean): string {
  return `<!doctype html><html lang="en"><body><main id="main">${body}</main>${
    includeFooter ? FOOTER_HTML : ""
  }</body></html>`;
}

function writePage(dir: string, relPath: string, body: string, includeFooter = true): void {
  const full = join(dir, relPath);
  mkdirSync(dirname(full), { recursive: true });
  writeFileSync(full, page(body, includeFooter));
}

function makeDist(): string {
  return mkdtempSync(join(tmpdir(), "link-check-"));
}

describe("checkSite", () => {
  it("passes a complete site", () => {
    const dist = makeDist();
    const rb = parseRulebook({
      sections: [validSection(), validSection({ id: "basics", order: 1 })],
      moves: [validMove()],
      classes: [],
    });
    writePage(
      dist,
      "index.html",
      `<a href="/rules/intro/">Intro</a><a href="/rules/basics/">Basics</a><a href="/moves/">Moves</a>`,
    );
    writePage(dist, "moves/index.html", `<a href="/moves/test-move/">Test Move</a>`);
    writePage(dist, "404.html", `<a href="/">Home</a>`);
    writePage(
      dist,
      "rules/intro/index.html",
      `<div data-section-id="intro"><a href="/">Home</a><a href="/moves/test-move/">Test Move</a></div>`,
    );
    writePage(dist, "rules/basics/index.html", `<div data-section-id="basics"><a href="/">Home</a></div>`);
    writePage(
      dist,
      "moves/test-move/index.html",
      `<div data-move-id="test-move"><a href="/rules/intro/">Intro</a></div>`,
    );

    const report = checkSite(dist, rb);

    expect(report.problems).toEqual([]);
    expect(report.pages).toBe(6);
    expect(report.internalLinks).toBe(9);
  });

  it("reports a missing section page", () => {
    const dist = makeDist();
    const rb = parseRulebook({ sections: [validSection()], moves: [], classes: [] });
    writePage(dist, "index.html", `<a href="/">Home</a>`);
    writePage(dist, "moves/index.html", `<p>No moves.</p>`);
    writePage(dist, "404.html", `<a href="/">Home</a>`);

    const report = checkSite(dist, rb);

    expect(report.problems.length).toBeGreaterThan(0);
    expect(report.problems.some((problem) => problem.includes("intro"))).toBe(true);
  });

  it("reports a page without its id marker", () => {
    const dist = makeDist();
    const rb = parseRulebook({ sections: [validSection()], moves: [], classes: [] });
    writePage(dist, "index.html", `<a href="/">Home</a>`);
    writePage(dist, "moves/index.html", `<p>No moves.</p>`);
    writePage(dist, "404.html", `<a href="/">Home</a>`);
    writePage(dist, "rules/intro/index.html", `<div data-section-id="wrong"><a href="/">Home</a></div>`);

    const report = checkSite(dist, rb);

    expect(report.problems.length).toBeGreaterThan(0);
    expect(
      report.problems.some(
        (problem) => problem.includes("intro") && problem.includes("data-section-id"),
      ),
    ).toBe(true);
  });

  it("reports a missing move page", () => {
    const dist = makeDist();
    const rb = parseRulebook({
      sections: [validSection()],
      moves: [validMove()],
      classes: [],
    });
    writePage(dist, "index.html", `<a href="/">Home</a>`);
    writePage(dist, "moves/index.html", `<p>No moves.</p>`);
    writePage(dist, "404.html", `<a href="/">Home</a>`);
    writePage(dist, "rules/intro/index.html", `<div data-section-id="intro"><a href="/">Home</a></div>`);

    const report = checkSite(dist, rb);

    expect(report.problems.length).toBeGreaterThan(0);
    expect(report.problems.some((problem) => problem.includes("test-move"))).toBe(true);
  });

  it("reports a broken internal link", () => {
    const dist = makeDist();
    const rb = parseRulebook({ sections: [validSection()], moves: [], classes: [] });
    writePage(dist, "index.html", `<a href="/nowhere/">Nowhere</a>`);
    writePage(dist, "moves/index.html", `<p>No moves.</p>`);
    writePage(dist, "404.html", `<a href="/">Home</a>`);
    writePage(dist, "rules/intro/index.html", `<div data-section-id="intro"><a href="/">Home</a></div>`);

    const report = checkSite(dist, rb);

    expect(report.problems.length).toBeGreaterThan(0);
    expect(report.problems.some((problem) => problem.includes("/nowhere/"))).toBe(true);
  });

  it("reports a missing trailing slash", () => {
    const dist = makeDist();
    const rb = parseRulebook({ sections: [validSection()], moves: [], classes: [] });
    writePage(dist, "index.html", `<a href="/rules/intro">Intro</a>`);
    writePage(dist, "moves/index.html", `<p>No moves.</p>`);
    writePage(dist, "404.html", `<a href="/">Home</a>`);
    writePage(dist, "rules/intro/index.html", `<div data-section-id="intro"><a href="/">Home</a></div>`);

    const report = checkSite(dist, rb);

    expect(report.problems.length).toBeGreaterThan(0);
    expect(
      report.problems.some(
        (problem) => problem.includes("/rules/intro") && problem.toLowerCase().includes("trailing slash"),
      ),
    ).toBe(true);
  });

  it("reports a missing fragment target", () => {
    const dist = makeDist();
    const rb = parseRulebook({ sections: [validSection()], moves: [], classes: [] });
    writePage(dist, "index.html", `<a href="#missing-target">Jump</a>`);
    writePage(dist, "moves/index.html", `<p>No moves.</p>`);
    writePage(dist, "404.html", `<a href="/">Home</a>`);
    writePage(dist, "rules/intro/index.html", `<div data-section-id="intro"><a href="/">Home</a></div>`);

    const report = checkSite(dist, rb);

    expect(report.problems.length).toBeGreaterThan(0);
    expect(report.problems.some((problem) => problem.includes("#missing-target"))).toBe(true);
  });

  it("reports a relative link", () => {
    const dist = makeDist();
    const rb = parseRulebook({ sections: [validSection()], moves: [], classes: [] });
    writePage(dist, "index.html", `<a href="about.html">About</a>`);
    writePage(dist, "moves/index.html", `<p>No moves.</p>`);
    writePage(dist, "404.html", `<a href="/">Home</a>`);
    writePage(dist, "rules/intro/index.html", `<div data-section-id="intro"><a href="/">Home</a></div>`);

    const report = checkSite(dist, rb);

    expect(report.problems.length).toBeGreaterThan(0);
    expect(report.problems.some((problem) => problem.includes("about.html"))).toBe(true);
  });

  it("skips external links", () => {
    const dist = makeDist();
    const rb = parseRulebook({ sections: [validSection()], moves: [], classes: [] });
    writePage(
      dist,
      "index.html",
      `<a href="http://example.com">HTTP</a><a href="https://example.com">HTTPS</a><a href="mailto:test@example.com">Mail</a>`,
    );
    writePage(dist, "moves/index.html", `<p>No moves.</p>`);
    writePage(dist, "404.html", `<a href="/">Home</a>`);
    writePage(dist, "rules/intro/index.html", `<div data-section-id="intro"><a href="/">Home</a></div>`);

    const report = checkSite(dist, rb);

    expect(report.problems).toEqual([]);
    // Only the two internal links (on 404.html and rules/intro/index.html) are counted; the
    // three external hrefs on the home page are classified as external and skipped.
    expect(report.internalLinks).toBe(2);
  });

  it("reports a page without the attribution footer", () => {
    const dist = makeDist();
    const rb = parseRulebook({ sections: [validSection()], moves: [], classes: [] });
    writePage(dist, "index.html", `<a href="/">Home</a>`, false);
    writePage(dist, "moves/index.html", `<p>No moves.</p>`);
    writePage(dist, "404.html", `<a href="/">Home</a>`);
    writePage(dist, "rules/intro/index.html", `<div data-section-id="intro"><a href="/">Home</a></div>`);

    const report = checkSite(dist, rb);

    expect(report.problems.length).toBeGreaterThan(0);
    expect(report.problems.some((problem) => problem.includes("index.html"))).toBe(true);
  });
});
