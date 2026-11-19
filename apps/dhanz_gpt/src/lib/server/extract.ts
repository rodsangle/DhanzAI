import "server-only";

/**
 * Text extraction, token estimates and chunking for uploaded files.
 *
 * Token counts are estimates (about 4 characters per token for English prose),
 * shown to people as "about N tokens". They decide two limits:
 *  - FILE: a single file over this is refused at upload (the original's limit is 2M).
 *  - PER_MESSAGE: files attached to one message must fit in one request. Bigger sets
 *    are refused with a pointer to projects, where only the relevant parts are read.
 */
export const TOKEN_LIMITS = {
  file: 2_000_000,
  perMessage: Number(process.env.MESSAGE_FILE_TOKEN_BUDGET ?? 150_000),
} as const;

/** Inputs larger than this aren't parsed (PDF and DOCX parsing holds the whole file in memory). */
const MAX_PARSE_BYTES = 64 * 1024 * 1024;

export const estimateTokens = (text: string) => Math.ceil(text.length / 4);

export function formatTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

export type Extractable = "text" | "pdf" | "docx";

export function extractKind(mime: string, name: string): Extractable | null {
  if (mime === "application/pdf" || /\.pdf$/i.test(name)) return "pdf";
  if (mime === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" || /\.docx$/i.test(name)) return "docx";
  if (/^(text\/|application\/(json|xml|csv|x-ndjson))/.test(mime) || /\.(md|txt|csv|json|tsv|html?|xml|ya?ml)$/i.test(name)) return "text";
  return null;
}

export class ExtractError extends Error {}

/** Returns the file's text, or null if it is too big to parse here or has no text layer. */
export async function extractText(bytes: Buffer, kind: Extractable): Promise<string | null> {
  if (bytes.length > MAX_PARSE_BYTES) return null;
  let text: string;
  try {
    if (kind === "text") {
      text = bytes.toString("utf8");
    } else if (kind === "pdf") {
      const { getDocumentProxy, extractText: pdfText } = await import("unpdf");
      const pdf = await getDocumentProxy(new Uint8Array(bytes));
      const { text: pages } = await pdfText(pdf, { mergePages: false });
      text = (pages as string[]).map((p, i) => `[Page ${i + 1}]\n${p.trim()}`).join("\n\n");
    } else {
      const mammoth = await import("mammoth");
      const { value } = await mammoth.extractRawText({ buffer: bytes });
      text = value;
    }
  } catch {
    throw new ExtractError("We couldn't read this file. It may be damaged or password-protected.");
  }
  text = text.replace(/\u0000/g, "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  // A scanned PDF has page markers and nothing else.
  if (!text.replace(/\[Page \d+\]/g, "").trim()) return null;
  return text;
}

/**
 * Splits text into ~1,800-character chunks on paragraph boundaries, carrying a short
 * overlap so a sentence split across chunks can still be found.
 */
export function chunkText(text: string, size = 1800, overlap = 200): string[] {
  const paras = text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const pieces: string[] = [];
  for (const p of paras) {
    if (p.length <= size) pieces.push(p);
    else for (let i = 0; i < p.length; i += size - overlap) pieces.push(p.slice(i, i + size));
  }
  const chunks: string[] = [];
  let cur = "";
  for (const p of pieces) {
    if (cur && cur.length + p.length + 2 > size) {
      chunks.push(cur);
      const tail = cur.slice(-overlap);
      cur = tail.includes("\n") ? tail.slice(tail.indexOf("\n") + 1) : "";
    }
    cur = cur ? `${cur}\n\n${p}` : p;
  }
  if (cur) chunks.push(cur);
  // Keep the page marker that each chunk falls under, so answers can say "page 4".
  let page: string | null = null;
  return chunks.map((c) => {
    const first = /^\[Page \d+\]/.exec(c)?.[0];
    const out = page && !first ? `${page} (continued)\n${c}` : c;
    const all = c.match(/\[Page \d+\]/g);
    if (all) page = all[all.length - 1];
    return out;
  });
}
