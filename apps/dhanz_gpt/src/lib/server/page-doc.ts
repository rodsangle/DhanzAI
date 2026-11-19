import "server-only";
import { generateJSON } from "@tiptap/html/server";
import { pageExtensions } from "@/lib/page-schema";
import { markdownToHtml } from "./markdown-html";

/** Markdown → the editor's JSON document (for pages the assistant drafts). */
export function markdownToDoc(md: string) {
  return generateJSON(markdownToHtml(md), pageExtensions) as { type: "doc"; content?: unknown[] };
}
