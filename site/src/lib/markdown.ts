import { Marked, Renderer } from "marked";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const marked = new Marked({
  gfm: true,
  breaks: false,
  renderer: {
    html(token) {
      return escapeHtml(token.raw);
    },
    // Wrap tables so a wide one can scroll on a phone without changing the table's own
    // `display` (which would strip its table semantics in some browser/AT combinations).
    table(token) {
      return `<div class="table-scroll">${Renderer.prototype.table.call(this, token)}</div>\n`;
    },
  },
});

export function renderMarkdown(markdown: string): string {
  if (markdown === "") return "";
  return marked.parse(markdown, { async: false });
}
