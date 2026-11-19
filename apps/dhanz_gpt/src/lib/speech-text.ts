/** Turning an answer into text to read aloud (pure functions, shared by the server and tests). */

/** The model takes up to ~2,000 tokens per request; parts stay well under that. */
const PART_CHARS = 3000;
export const MAX_SPEECH_PARTS = 12;

/** Markdown to plain sentences: no code blocks, link targets, citation markers or table pipes. */
export function speakable(markdown: string) {
  return markdown
    .replace(/```[\s\S]*?```/g, " (code omitted) ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\s*\[\[\d+\]\]\([^)]*\)/g, "")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^[ \t]{0,3}#{1,6}[ \t]+/gm, "")
    .replace(/^[ \t]*[-*+][ \t]+/gm, "")
    .replace(/^[ \t]*\|?[ \t]*:?-{3,}[-:| \t]*$/gm, "")
    .replace(/^[ \t]*\|[ \t]*|[ \t]*\|[ \t]*$/gm, "")
    .replace(/[ \t]*\|[ \t]*/g, ", ")
    .replace(/[*_~]{1,3}([^*_~]+)[*_~]{1,3}/g, "$1")
    .replace(/\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]/g, " (formula) ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * Splits text into parts of at most PART_CHARS: whole paragraphs where they fit, a long paragraph by
 * sentences, a very long sentence at spaces. Parts are packed as full as they can be.
 */
export function speechParts(text: string): string[] {
  const units: string[] = [];
  for (const para of text.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean)) {
    if (para.length <= PART_CHARS) {
      units.push(para);
      continue;
    }
    for (const sentence of para.match(/[^.!?]+(?:[.!?]+["')\]]*|$)\s*/g) ?? [para]) {
      let rest = sentence.trim();
      while (rest.length > PART_CHARS) {
        const space = rest.lastIndexOf(" ", PART_CHARS);
        const at = space > 0 ? space : PART_CHARS;
        units.push(rest.slice(0, at));
        rest = rest.slice(at).trim();
      }
      if (rest) units.push(rest);
    }
  }
  const parts: string[] = [];
  let cur = "";
  for (const u of units) {
    if (cur && cur.length + 2 + u.length > PART_CHARS) {
      parts.push(cur);
      cur = "";
    }
    cur = cur ? `${cur}\n\n${u}` : u;
  }
  if (cur) parts.push(cur);
  return parts.slice(0, MAX_SPEECH_PARTS);
}
