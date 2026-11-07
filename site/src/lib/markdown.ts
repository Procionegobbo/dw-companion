import { Marked } from "marked";

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
  },
});

export function renderMarkdown(markdown: string): string {
  if (markdown === "") return "";
  return marked.parse(markdown, { async: false });
}
