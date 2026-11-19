import "server-only";
import { marked } from "marked";

/**
 * Markdown from the model → HTML for the page editor to insert. The editor's schema only keeps the nodes
 * it knows (paragraphs, headings, lists, quotes, code, bold, italic, links), so raw HTML in the model's
 * output is dropped on insert; we also escape it here so nothing runs even in a preview.
 */
export function markdownToHtml(md: string): string {
  const escaped = md.replace(/<(?=[a-z/!?])/gi, "&lt;");
  const html = marked.parse(escaped, { async: false, gfm: true, breaks: false }) as string;
  // Links only to the web or email; anything else (javascript:, data:) becomes inert.
  return html.replace(/\b(href|src)="(?!https?:|mailto:)[^"]*"/gi, '$1="#"');
}
