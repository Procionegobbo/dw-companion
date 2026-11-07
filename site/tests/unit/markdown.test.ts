import { describe, expect, it } from "vitest";
import { renderMarkdown } from "../../src/lib/markdown";

describe("renderMarkdown", () => {
  it("renders emphasis and strong", () => {
    const html = renderMarkdown("*emphasis* and **strong**");
    expect(html).toContain("<em>emphasis</em>");
    expect(html).toContain("<strong>strong</strong>");
  });

  it("renders bulleted and numbered lists", () => {
    const bulleted = renderMarkdown("- one\n- two");
    expect(bulleted).toContain("<ul>");
    expect(bulleted).toContain("<li>one</li>");
    expect(bulleted).toContain("<li>two</li>");

    const numbered = renderMarkdown("1. one\n2. two");
    expect(numbered).toContain("<ol>");
    expect(numbered).toContain("<li>one</li>");
    expect(numbered).toContain("<li>two</li>");
  });

  it("renders a GFM table", () => {
    const html = renderMarkdown("| Score | Modifier |\n| --- | --- |\n| 16 | +2 |");
    expect(html).toContain("<table>");
    expect(html).toContain("<th>Score</th>");
    expect(html).toContain("<th>Modifier</th>");
  });

  it("renders blockquotes and h4 headings", () => {
    const html = renderMarkdown("> a quote\n\n#### Heading Four");
    expect(html).toContain("<blockquote>");
    expect(html).toContain("<h4>Heading Four</h4>");
  });

  it("unescapes backslash escapes", () => {
    const html = renderMarkdown("b\\[2d6\\] \\_\\_");
    expect(html).toContain("b[2d6] __");
  });

  it("escapes raw html", () => {
    const html = renderMarkdown("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });

  it("returns empty string for empty input", () => {
    expect(renderMarkdown("")).toBe("");
  });
});
