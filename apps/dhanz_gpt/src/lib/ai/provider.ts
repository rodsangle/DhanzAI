import "server-only";
import { BRAND } from "@/lib/brand";
import Anthropic from "@anthropic-ai/sdk";
import type { FileRow } from "@/lib/data/types";
import { planResponse, titleFor, tokenize } from "./fake-model";

/**
 * Text models behind one interface.
 * - "anthropic": the Claude API through the official SDK. Requests send no sampling parameters
 *   (current Sonnet models reject non-default ones) and mark the system prompt for prompt caching.
 * - "demo": the offline sample model, for development and tests.
 * Chosen by MODEL_PROVIDER, defaulting to "anthropic" when ANTHROPIC_API_KEY is set.
 */

export type Attachment = { file: FileRow; bytes: Buffer | null };

export interface AnswerContext {
  model: string;
  prompt: string;
  attachments: Attachment[];
  history: { role: "user" | "assistant"; text: string; attachmentNames: string[] }[];
  aboutYou: string;
  responseStyle: string;
  /** The person's memory summary, when memory is on (never in temporary chats). */
  memory?: string | null;
  /** App actions available in this chat (apps the person @mentioned and has connected). */
  tools?: ToolSpec[];
  /** App names, for the system prompt. */
  appNames?: string[];
  /** A note about apps mentioned but not connected. */
  appNote?: string | null;
  /** App action rounds already done in this answer. */
  steps?: AgentStep[];
  /** Web search is offered to the model (the model decides), and forced when the person turned it on. */
  webSearch?: "auto" | "forced" | "off";
  /** Earlier exchanges from their other chats that match this question, when chat history is on. */
  pastChats?: { conversation_id: string; title: string; date: string; question: string; answer: string }[];
  project: ({ name: string; instructions: string } & Knowledge) | null;
  /** The custom assistant this chat runs with. */
  assistant?: ({ name: string; instructions: string } & Knowledge) | null;
}

export type ToolCall = { id: string; name: string; input: Record<string, unknown> };
export type ToolResult = { tool_use_id: string; content: string; is_error?: boolean };
/** One round of app actions: what the model said and asked for, and what came back. */
export type AgentStep = { assistantContent: unknown[]; calls: ToolCall[]; results: ToolResult[] };
export type ToolSpec = { name: string; description: string; input_schema: Record<string, unknown> };

export type Chunk =
  | { type: "text"; text: string }
  /** The model wants app actions run before it continues. */
  | { type: "tool_calls"; calls: ToolCall[]; assistantContent: unknown[] }
  | { type: "usage"; input_tokens: number; output_tokens: number; web_searches?: number }
  /** A search started (the query, for the "Searching the web" status). */
  | { type: "searching"; query: string }
  /** Web pages cited in the answer, numbered in the order the [n] markers use. */
  | { type: "web_sources"; items: { title: string; url: string }[] };

/**
 * WEB_SEARCH: "auto" (default: offered on every answer, the model decides), "manual" (only when the
 * person turns it on for a message) or "off". Each search costs $10 per 1,000 on the Claude API, plus tokens.
 */
export function webSearchMode(): "auto" | "manual" | "off" {
  const m = process.env.WEB_SEARCH ?? "auto";
  return m === "off" || m === "manual" ? m : "auto";
}
export const webSearchAvailable = () => webSearchMode() !== "off";
const WEB_SEARCH_MAX_USES = Number(process.env.WEB_SEARCH_MAX_USES ?? 5);

export class ModelError extends Error {
  constructor(message: string, public retryable: boolean) {
    super(message);
  }
}

export function modelProvider(): "anthropic" | "demo" {
  const p = process.env.MODEL_PROVIDER ?? (process.env.ANTHROPIC_API_KEY ? "anthropic" : "demo");
  if (p !== "anthropic" && p !== "demo") throw new Error(`Unknown MODEL_PROVIDER ${p}`);
  return p;
}

let client: Anthropic | null = null;
export function anthropic() {
  if (!client) {
    client = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY,
      baseURL: process.env.ANTHROPIC_BASE_URL || undefined,
      maxRetries: 2,
      timeout: 10 * 60 * 1000,
    });
  }
  return client;
}

/* ------------------------------------------------------------------ prompt building */

/** Project files up to this many characters (~75k tokens) are read whole; past it, by excerpt. */
export const PROJECT_FILES_CHAR_BUDGET = 300_000;
/** How much excerpt text a long-file project gets per question (~40k tokens). */
export const PROJECT_EXCERPT_CHAR_BUDGET = 160_000;
const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/gif", "image/webp"]);

export function systemPrompt(ctx: AnswerContext) {
  const parts = [
    `You are ${BRAND.name}, the chat assistant from ${BRAND.company}. ` +
      "You help with writing, research, planning, analysis, code and creative ideas. " +
      "Be direct and practical. Use Markdown when it helps (lists, tables, code blocks). " +
      "If you don't know something, say so rather than guessing. Never invent facts, prices, dates or sources.",
  ];
  if (ctx.aboutYou.trim()) parts.push(`About the person you're helping:\n${ctx.aboutYou.trim()}`);
  if (ctx.responseStyle.trim()) parts.push(`How they want you to respond:\n${ctx.responseStyle.trim()}`);
  if (ctx.tools?.length)
    parts.push(
      `Connected apps you can use in this chat: ${ctx.appNames?.join(", ")}. Use their actions when the person asks for something in those apps. ` +
        "Actions that change things may first ask the person to approve; just call the action and the app shows them what you want to do. " +
        "Never claim an action happened unless its result says so.",
    );
  if (ctx.appNote) parts.push(ctx.appNote);
  if (ctx.webSearch === "forced")
    parts.push("The person turned on web search for this message: search the web before answering, and cite what you use.");
  else if (ctx.webSearch === "auto")
    parts.push("You can search the web. Do it for anything current or specific you aren't sure of (news, prices, releases, events); answer directly otherwise.");
  if (ctx.memory?.trim())
    parts.push(
      "What you remember about this person from earlier chats (they can see and edit this in Settings). " +
        `Use it when it's relevant; don't recite it or mention it unprompted:\n${ctx.memory.trim()}`,
    );
  if (ctx.pastChats?.length)
    parts.push(
      "Earlier chats with this person that may relate to the question (they may be out of date; prefer what they say now):\n" +
        ctx.pastChats
          .map((c) => `<earlier_chat title="${c.title.replace(/"/g, "'")}" date="${c.date}">\nThey asked: ${c.question}\nYou answered: ${c.answer}\n</earlier_chat>`)
          .join("\n"),
    );
  if (ctx.assistant) {
    parts.push(`In this chat you are "${ctx.assistant.name}", an assistant set up in this workspace.`);
    if (ctx.assistant.instructions.trim()) parts.push(`Assistant instructions (follow these):\n${ctx.assistant.instructions.trim()}`);
    parts.push(...knowledgeParts("Assistant knowledge files", ctx.assistant));
  }
  if (ctx.project) {
    parts.push(`This chat is in the project "${ctx.project.name}".`);
    if (ctx.project.instructions.trim()) parts.push(`Project instructions (follow these):\n${ctx.project.instructions.trim()}`);
    parts.push(...knowledgeParts("Project files", ctx.project));
  }
  return parts.join("\n\n");
}

export type Knowledge = {
  files: FileRow[];
  /** Set when the files are too long to read whole: the parts picked for this question. */
  excerpts?: { name: string; chunks: { idx: number; content: string }[] }[];
  /** The single best-matching part (shown by the demo model so tests can see what was read). */
  topExcerpt?: { name: string; content: string } | null;
};

/** A set of files for the system prompt: whole when short, the matching parts when long. */
function knowledgeParts(label: string, k: Knowledge): string[] {
  const parts: string[] = [];
  const unreadable = k.files.filter((f) => !f.extracted_text).map((f) => f.name);
  if (k.excerpts) {
    const docs = k.excerpts.map((e) => {
      let prev = -1;
      const body = e.chunks.map((c) => {
        const gap = prev >= 0 && c.idx !== prev + 1 ? "\n…\n" : prev < 0 && c.idx > 0 ? "…\n" : "";
        prev = c.idx;
        return gap + c.content;
      });
      return `<file name="${e.name.replace(/"/g, "'")}" excerpts="true">\n${body.join("\n\n")}\n</file>`;
    });
    if (docs.length)
      parts.push(
        `${label}. They're too long to include whole, so these are the parts that best match the question, ` +
          "in reading order (… marks skipped text). If the answer isn't here, say that you only see parts of the files " +
          `and suggest asking about a specific section.\n${docs.join("\n")}`,
      );
  } else {
    let budget = PROJECT_FILES_CHAR_BUDGET;
    const docs: string[] = [];
    for (const f of k.files) {
      if (!f.extracted_text || budget <= 0) continue;
      const text = f.extracted_text.slice(0, budget);
      budget -= text.length;
      docs.push(`<file name="${f.name.replace(/"/g, "'")}">\n${text}\n</file>`);
    }
    if (docs.length) parts.push(`${label}:\n${docs.join("\n")}`);
  }
  if (unreadable.length) parts.push(`Other ${label.toLowerCase()} (not readable as text here): ${unreadable.join(", ")}`);
  return parts;
}

type Block = Anthropic.Messages.ContentBlockParam;

export function userContent(ctx: AnswerContext): Block[] {
  const blocks: Block[] = [];
  for (const { file, bytes } of ctx.attachments) {
    if (bytes && IMAGE_TYPES.has(file.mime) && bytes.length <= 5 * 1024 * 1024) {
      blocks.push({ type: "image", source: { type: "base64", media_type: file.mime as "image/png", data: bytes.toString("base64") } });
    } else if (bytes && file.mime === "application/pdf" && bytes.length <= 32 * 1024 * 1024) {
      blocks.push({ type: "document", title: file.name, source: { type: "base64", media_type: "application/pdf", data: bytes.toString("base64") } });
    } else if (file.extracted_text) {
      blocks.push({ type: "document", title: file.name, source: { type: "text", media_type: "text/plain", data: file.extracted_text } });
    } else {
      blocks.push({ type: "text", text: `[The user attached "${file.name}" (${file.mime}), which can't be read here. Say so if it matters.]` });
    }
  }
  blocks.push({ type: "text", text: ctx.prompt.trim() || "(See the attached files.)" });
  return blocks;
}

/** The conversation for the API, plus any app-action rounds already done in this answer. */
export function messagesWithSteps(ctx: AnswerContext): Anthropic.Messages.MessageParam[] {
  const out = buildMessages(ctx);
  for (const st of ctx.steps ?? []) {
    out.push({ role: "assistant", content: st.assistantContent as Anthropic.Messages.ContentBlockParam[] });
    out.push({ role: "user", content: st.results.map((r) => ({ type: "tool_result" as const, tool_use_id: r.tool_use_id, content: r.content, is_error: r.is_error })) });
  }
  return out;
}

export function buildMessages(ctx: AnswerContext): Anthropic.Messages.MessageParam[] {
  const out: Anthropic.Messages.MessageParam[] = [];
  for (const h of ctx.history) {
    const text = h.text.trim() + (h.attachmentNames.length ? `\n[Attached earlier: ${h.attachmentNames.join(", ")}]` : "");
    if (!text.trim()) continue;
    const last = out.at(-1);
    // The API needs alternating roles starting with the user; merge any repeats.
    if (last && last.role === h.role) last.content = `${last.content as string}\n\n${text}`;
    else if (out.length || h.role === "user") out.push({ role: h.role, content: text });
  }
  if (out.at(-1)?.role === "user") out.push({ role: "assistant", content: "(No answer was given.)" });
  out.push({ role: "user", content: userContent(ctx) });
  return out;
}

/* ------------------------------------------------------------------ streaming */

export function friendly(e: unknown): ModelError {
  if (e instanceof Anthropic.APIError) {
    const s = e.status ?? 0;
    if (s === 429 || s === 529 || s === 503) return new ModelError("The model is busy right now. Try again in a moment.", true);
    if (s === 401 || s === 403) return new ModelError("The assistant isn't connected to the model correctly. Tell your admin.", false);
    if (s === 400 || s === 413) return new ModelError("The model couldn't process this message. Try a shorter message or fewer attachments.", false);
    return new ModelError("The model stopped responding.", true);
  }
  if ((e as Error)?.name === "AbortError" || e instanceof Anthropic.APIUserAbortError) return new ModelError("stopped", false);
  return new ModelError("The model stopped responding.", true);
}

export async function* streamAnswer(ctx: AnswerContext, signal: AbortSignal): AsyncGenerator<Chunk> {
  if (modelProvider() === "demo" && ctx.tools?.length) {
    yield* demoToolTurn(ctx, signal);
    return;
  }
  if (modelProvider() === "demo") {
    const plan = planResponse({
      prompt: ctx.prompt,
      history: ctx.history.map((h) => ({ role: h.role, text: h.text })),
      projectName: ctx.project?.name,
      projectInstructions: [ctx.project?.instructions, ctx.assistant?.instructions].filter(Boolean).join("\n"),
      aboutYou: ctx.aboutYou,
      responseStyle: ctx.responseStyle,
      attachments: ctx.attachments.map(({ file }) => ({ name: file.name, mime: file.mime, text: file.extracted_text })),
      projectFiles: [...(ctx.assistant?.files ?? []), ...(ctx.project?.files ?? [])].map((f) => ({ name: f.name })),
      projectExcerpt: ctx.assistant?.topExcerpt ?? ctx.project?.topExcerpt ?? null,
      assistantName: ctx.assistant?.name ?? null,
      memory: ctx.memory ?? null,
      pastChats: ctx.pastChats?.map((c) => ({ title: c.title })) ?? [],
      webSearch: ctx.webSearch ?? "off",
      appNote: ctx.appNote ?? null,
      model: ctx.model,
    });
    if (plan.search) yield { type: "searching", query: plan.search.query };
    await new Promise((r) => setTimeout(r, ctx.model.includes("opus") ? 900 : 350));
    let sent = 0;
    for (const tok of tokenize(plan.text)) {
      if (signal.aborted) return;
      if (plan.failAfterChars !== undefined && sent >= plan.failAfterChars) throw new ModelError("The model stopped responding.", true);
      sent += tok.length;
      yield { type: "text", text: tok };
      await new Promise((r) => setTimeout(r, plan.delayMs));
    }
    if (plan.search) yield { type: "web_sources", items: plan.search.sources };
    yield { type: "usage", input_tokens: 0, output_tokens: 0, web_searches: plan.search ? 1 : 0 };
    return;
  }

  yield* claudeAnswer(ctx, signal);
}

/**
 * The Claude path. With web search on, the API runs searches itself (server tool) and the answer's
 * text blocks carry citations. Each cited block gets clickable [n] markers after it, and the cited
 * pages come back as web_sources in the same numbering. Long search turns can pause (pause_turn);
 * the paused content is sent back unchanged to continue, up to a few times.
 */
async function* claudeAnswer(ctx: AnswerContext, signal: AbortSignal): AsyncGenerator<Chunk> {
  let search = ctx.webSearch && ctx.webSearch !== "off" && webSearchAvailable();
  const sources: { title: string; url: string }[] = [];
  const numberFor = (url: string, title: string) => {
    let i = sources.findIndex((x) => x.url === url);
    if (i < 0) i = sources.push({ title: title || url, url }) - 1;
    return i + 1;
  };
  let messages = messagesWithSteps(ctx);
  let input = 0;
  let output = 0;
  let searches = 0;
  let toolCalls: Extract<Chunk, { type: "tool_calls" }> | null = null;
  try {
    for (let round = 0; round < 4; round++) {
      const stream = anthropic().messages.stream(
        {
          model: ctx.model,
          max_tokens: 8192,
          system: [{ type: "text", text: systemPrompt(ctx), cache_control: { type: "ephemeral" } }],
          messages,
          ...(search || ctx.tools?.length
            ? {
                tools: [
                  ...(search ? [{ type: "web_search_20250305" as const, name: "web_search" as const, max_uses: WEB_SEARCH_MAX_USES }] : []),
                  ...(ctx.tools ?? []).map((t) => ({ name: t.name, description: t.description, input_schema: t.input_schema as Anthropic.Messages.Tool.InputSchema })),
                ],
              }
            : {}),
        },
        { signal },
      );
      const blockCites = new Map<number, Set<number>>();
      const toolJson = new Map<number, string>();
      try {
        for await (const ev of stream) {
          if (ev.type === "message_start") input += ev.message.usage?.input_tokens ?? 0;
          else if (ev.type === "content_block_start" && ev.content_block.type === "server_tool_use") toolJson.set(ev.index, "");
          else if (ev.type === "content_block_delta") {
            if (ev.delta.type === "text_delta") yield { type: "text", text: ev.delta.text };
            else if (ev.delta.type === "input_json_delta" && toolJson.has(ev.index)) toolJson.set(ev.index, toolJson.get(ev.index)! + ev.delta.partial_json);
            else if (ev.delta.type === "citations_delta" && ev.delta.citation.type === "web_search_result_location") {
              const c = ev.delta.citation;
              if (!blockCites.has(ev.index)) blockCites.set(ev.index, new Set());
              blockCites.get(ev.index)!.add(numberFor(c.url, c.title ?? ""));
            }
          } else if (ev.type === "content_block_stop") {
            const n = blockCites.get(ev.index);
            if (n?.size) yield { type: "text", text: [...n].map((k) => ` [[${k}]](${sources[k - 1].url})`).join("") };
            if (toolJson.has(ev.index)) {
              searches++;
              let query = "";
              try {
                query = (JSON.parse(toolJson.get(ev.index) || "{}") as { query?: string }).query ?? "";
              } catch {}
              yield { type: "searching", query };
            }
          } else if (ev.type === "message_delta") output += ev.usage?.output_tokens ?? 0;
        }
      } catch (e) {
        // An org can turn web search off in the Console: answer without it instead of failing.
        if (search && e instanceof Anthropic.APIError && e.status === 400 && /web.?search/i.test(e.message) && round === 0) {
          search = false;
          round--;
          continue;
        }
        throw e;
      }
      const final = await stream.finalMessage();
      if (final.stop_reason === "tool_use") {
        const calls = final.content.flatMap((b) => (b.type === "tool_use" ? [{ id: b.id, name: b.name, input: (b.input ?? {}) as Record<string, unknown> }] : []));
        if (calls.length) {
          toolCalls = { type: "tool_calls", calls, assistantContent: final.content };
          break;
        }
      }
      if (final.stop_reason !== "pause_turn") break;
      messages = [...messages, { role: "assistant", content: final.content as Anthropic.Messages.ContentBlockParam[] }];
    }
  } catch (e) {
    if (signal.aborted) return;
    throw friendly(e);
  }
  if (sources.length) yield { type: "web_sources", items: sources };
  yield { type: "usage", input_tokens: input, output_tokens: output, web_searches: searches };
  if (toolCalls) yield toolCalls;
}

/** A short chat title. Falls back to the first words of the prompt. */
export async function makeTitle(prompt: string): Promise<string> {
  if (modelProvider() === "demo") return titleFor(prompt);
  try {
    const res = await anthropic().messages.create({
      model: process.env.TITLE_MODEL || "claude-haiku-5-5",
      max_tokens: 30,
      system: "Write a title of 3 to 6 words for a chat that starts with the user's message. Reply with the title only, no quotes or punctuation at the end.",
      messages: [{ role: "user", content: prompt.slice(0, 2000) }],
    });
    const text = res.content.find((b) => b.type === "text");
    const t = text && "text" in text ? text.text.trim().replace(/^["']|["'.]$/g, "") : "";
    return t ? t.slice(0, 80) : titleFor(prompt);
  } catch {
    return titleFor(prompt);
  }
}

/* ------------------------------------------------------------------ memory */

const MEMORY_SYSTEM =
  "You keep a short memory of durable facts about one person using Dhanz GPT, so future answers can use them. " +
  "You get the current memory (which may include their own corrections) and things they wrote in recent chats, newest first. " +
  "Return the updated memory as 3 to 15 short bullet points starting with \"- \". Keep: their role, what they work on, " +
  "ongoing projects and products, stated preferences for tone and format, and facts they asked to be remembered. " +
  "Keep their own corrections unless a newer message clearly replaces them. Drop one-off requests and anything outdated. " +
  "Never record health, finances, family matters, beliefs or other sensitive personal details. " +
  "If there's nothing durable, return the current memory unchanged. Reply with the bullets only.";

/** Rewrites the memory summary from the current one plus recent messages. */
export async function summarizeMemory(current: string, messages: string[]): Promise<string> {
  if (modelProvider() === "demo") return demoMemory(current, messages);
  const res = await anthropic().messages.create({
    model: process.env.MEMORY_MODEL || "claude-haiku-5-5",
    max_tokens: 900,
    system: MEMORY_SYSTEM,
    messages: [{
      role: "user",
      content: `<current_memory>\n${current || "(empty)"}\n</current_memory>\n<recent_messages>\n${messages.map((m) => `<message>${m}</message>`).join("\n")}\n</recent_messages>`,
    }],
  });
  const text = res.content.find((b) => b.type === "text");
  const out = text && "text" in text ? text.text.trim() : "";
  return out.startsWith("-") ? out : current;
}

/** Demo: first-person statements become bullets, merged after the existing memory. */
function demoMemory(current: string, messages: string[]): string {
  const lines = current.split("\n").map((l) => l.trim()).filter(Boolean);
  const seen = new Set(lines.map((l) => l.replace(/^-\s*/, "").toLowerCase()));
  const facts: string[] = [];
  for (const m of [...messages].reverse()) {
    for (const match of m.matchAll(/(?:^|[.!?]\s+)((?:I'm|I am|I work|I run|I lead|I own|my|our|we're|we are|remember that)\b[^.!?\n]{5,160})/gi)) {
      const fact = match[1].trim().replace(/^remember that\s+/i, "");
      const sentence = fact[0].toUpperCase() + fact.slice(1);
      if (!seen.has(sentence.toLowerCase())) {
        seen.add(sentence.toLowerCase());
        facts.push(`- ${sentence}.`);
      }
    }
  }
  return [...lines, ...facts].slice(0, 15).join("\n");
}

/* ------------------------------------------------------------------ demo app actions */

/**
 * The offline model's version of app use, deterministic so tests can drive it: it picks actions from
 * the question's wording, one round at a time, then answers from what came back.
 */
async function* demoToolTurn(ctx: AnswerContext, signal: AbortSignal): AsyncGenerator<Chunk> {
  const p = ctx.prompt.toLowerCase();
  const has = (n: string) => ctx.tools!.some((t) => t.name === n);
  const done = (ctx.steps ?? []).flatMap((s) => s.calls.map((c, i) => ({ call: c, result: s.results[i] })));
  const ran = (n: string) => done.find((d) => d.call.name === n);
  const quoted = /["“](.+?)["”]/.exec(ctx.prompt)?.[1];
  const about = (/\b(?:for|about|called|named)\s+(?:the\s+)?(.+?)(?:\s+and\s+|[.?!]|$)/i.exec(ctx.prompt.replace(/@[\w ]+?(?=\s)/g, ""))?.[1] ?? "brief").trim();
  const firstId = (r?: ToolResult) => {
    try {
      const j = JSON.parse(r?.content ?? "[]");
      return (Array.isArray(j) ? j[0]?.id : j?.id) ?? null;
    } catch {
      return null;
    }
  };
  let next: ToolCall | null = null;
  const mk = (name: string, input: Record<string, unknown>): ToolCall => ({ id: `toolu_demo_${done.length + 1}`, name, input });

  if (has("drive_create_doc") && /\b(create|make|save|draft)\b.*\bdoc\b/.test(p) && !ran("drive_create_doc")) {
    next = mk("drive_create_doc", { title: quoted ?? `Notes from ${BRAND.name}`, content: "Drop plan\n\n1. Lock colourways\n2. Shoot lookbook\n3. Write copy" });
  } else if (has("drive_search") && /@(google\s*)?drive/i.test(ctx.prompt) && !ran("drive_search") && !/\bdoc\b.*\b(create|make)\b/.test(p)) {
    next = mk("drive_search", { query: about });
  } else if (has("drive_read_file") && ran("drive_search") && !ran("drive_read_file") && /\b(read|summar\w*|what does|open)\b/.test(p)) {
    const id = firstId(ran("drive_search")!.result);
    if (id) next = mk("drive_read_file", { file_id: id });
  } else if (has("slack_post_message") && /@slack/i.test(ctx.prompt) && /\b(post|send|share|tell)\b/.test(p) && !ran("slack_post_message")) {
    next = mk("slack_post_message", { channel: /#([\w-]+)/.exec(ctx.prompt)?.[1] ?? "general", text: quoted ?? `Update from ${BRAND.name}` });
  } else if (has("slack_search") && /@slack/i.test(ctx.prompt) && !/\b(post|send|share|tell)\b/.test(p) && !ran("slack_search")) {
    next = mk("slack_search", { query: about });
  } else if (has("shopify_search_products") && /@shopify/i.test(ctx.prompt) && !ran("shopify_search_products")) {
    next = mk("shopify_search_products", { query: about });
  } else if (has("shopify_update_product_description") && ran("shopify_search_products") && /\b(update|rewrite|change|improve)\b/.test(p) && !ran("shopify_update_product_description")) {
    const r = ran("shopify_search_products")!.result;
    const id = firstId(r);
    let title = "";
    try {
      title = JSON.parse(r.content)[0]?.title ?? "";
    } catch {}
    if (id) next = mk("shopify_update_product_description", { product_id: id, product_title: title, description_html: "<p>Structured six-panel crown in washed cotton twill. Built to wear in.</p>" });
  }

  const say = async function* (text: string) {
    await new Promise((r) => setTimeout(r, 150));
    for (const tok of tokenize(text)) {
      if (signal.aborted) return;
      yield { type: "text" as const, text: tok };
      await new Promise((r) => setTimeout(r, 8));
    }
  };

  if (next) {
    const lead = done.length ? "" : "On it. ";
    if (lead) yield* say(lead);
    yield { type: "usage", input_tokens: 0, output_tokens: 0 };
    yield { type: "tool_calls", calls: [next], assistantContent: [{ type: "text", text: lead }, { type: "tool_use", id: next.id, name: next.name, input: next.input }] };
    return;
  }
  // Answer from what the actions returned.
  const lines = done.map(({ call, result }) => {
    if (result?.is_error) return `- ${call.name.replace(/_/g, " ")}: ${result.content}`;
    let body = result?.content ?? "";
    try {
      const j = JSON.parse(body);
      body = Array.isArray(j)
        ? j.slice(0, 3).map((x: Record<string, unknown>) => x.name ?? x.title ?? x.text).filter(Boolean).join("; ") || "nothing found"
        : String(j.text ?? j.title ?? j.name ?? (j.ok ? "done" : body)).slice(0, 200);
    } catch {}
    return `- ${call.name.replace(/_/g, " ")}: ${body}`;
  });
  const declined = done.some((d) => d.result?.is_error && /declined/i.test(d.result.content));
  yield* say(`${declined ? "Okay, I didn't do that." : "Here's what I got:"}\n\n${lines.join("\n")}`);
  yield { type: "usage", input_tokens: 0, output_tokens: 0 };
}
