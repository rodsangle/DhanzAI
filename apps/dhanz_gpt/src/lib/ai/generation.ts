import "server-only";
import {
  assistantContext, filesForMessages, getMemory, getPersonalization, projectExcerpts, relatedExchanges, insertMessage, messageRow, messagesForConversation, patchMessage, projectContext,
  readFileBytes, recordImage, recordUsage, saveGeneratedFile, threadPath, updateConversation, conversationRow, HttpError,
} from "@/lib/data";
import { createApproval, finishApproval, takeApproval } from "@/lib/apps/approvals";
import { mentionedApps, needsApproval, provider as appProvider, toolOwner } from "@/lib/apps/registry";
import { activeConnection, allowAlways, runTool } from "@/lib/apps/store";
import type { ContentBlock, Conversation, Message, Source } from "@/lib/data/types";
import { refreshMemory } from "./memory";
import { generateImage } from "./images";
import {
  makeTitle, ModelError, PROJECT_EXCERPT_CHAR_BUDGET, PROJECT_FILES_CHAR_BUDGET, streamAnswer, webSearchMode,
  type AgentStep, type AnswerContext, type ToolCall, type ToolResult, type ToolSpec,
} from "./provider";

/**
 * Generation engine. Each answer runs as a background task that writes its text to Postgres every
 * ~400 ms. HTTP responses only subscribe:
 * - same server instance → live events from memory (lowest latency);
 * - any other instance (serverless) → the row is polled until it finishes.
 * So closing the tab never aborts an answer, a reload catches up, and Stop works from anywhere
 * (it sets messages.stop_requested, which the generator checks on every save).
 * Route handlers pass the returned promise to `after()` so the platform keeps it running.
 */

export type GenEvent =
  | { type: "meta"; conversation_id: string; user_message_id?: string; assistant_message_id: string; title?: string }
  | { type: "snapshot"; text: string; content: ContentBlock[] }
  | { type: "delta"; text: string }
  | { type: "content"; content: ContentBlock[] }
  /** What the answer is doing before or between its text, e.g. "Searching the web: …". */
  | { type: "status"; text: string }
  | { type: "title"; title: string }
  | { type: "done"; status: Message["status"]; error?: string | null };

type Live = { listeners: Set<(e: GenEvent) => void>; abort: AbortController };
const g = globalThis as unknown as { __dhanzGptLive?: Map<string, Live> };
const live = (g.__dhanzGptLive ??= new Map());

export function stopLocal(messageId: string) {
  live.get(messageId)?.abort.abort();
}

function publish(messageId: string, e: GenEvent) {
  live.get(messageId)?.listeners.forEach((fn: (e: GenEvent) => void) => fn(e));
}

const IMAGE_ASK = /^(create|make|draw|generate|design)\b.*\b(image|picture|poster|graphic|mockup|illustration|art)\b/i;

/** Inserts an assistant message under `parent` and starts answering. Returns the row and the task's promise. */
export async function startAssistantReply(userId: string, conversation: Conversation, parent: Message, opts: { forceImage?: boolean; forceSearch?: boolean } = {}) {
  const assistant = await insertMessage({
    conversation_id: conversation.id, parent_id: parent.id, user_id: null, role: "assistant", content: [], text: "",
    model: conversation.model, status: "streaming", error: null, feedback: null,
  });
  const abort = new AbortController();
  live.set(assistant.id, { listeners: new Set(), abort });
  const done = run(userId, conversation, parent, assistant, abort, opts)
    .catch(async (err) => {
      console.error("[generation]", (err as Error)?.message);
      const msg = err instanceof ModelError ? err.message : "Something went wrong while answering.";
      await patchMessage(assistant.id, { status: "error", error: msg }).catch(() => {});
      publish(assistant.id, { type: "done", status: "error", error: msg });
    })
    .finally(() => live.delete(assistant.id));
  return { assistant, done };
}

async function buildContext(userId: string, conversation: Conversation, parent: Message, opts: { forceSearch?: boolean } = {}): Promise<AnswerContext> {
  const all = await messagesForConversation(conversation.id);
  const path = threadPath(all, parent.id);
  const history = path.slice(0, -1).filter((m) => (m.role === "user" || m.role === "assistant") && m.status !== "error");
  const files = await filesForMessages(path.map((m) => m.id));
  const current = files.filter((f) => f.message_id === parent.id).map((f) => f.file);
  const attachments = await Promise.all(
    current.map(async (file) => ({
      file,
      bytes: /^image\/(png|jpeg|gif|webp)$|^application\/pdf$/.test(file.mime) ? await readFileBytes(file).catch(() => null) : null,
    })),
  );
  const pers = await getPersonalization(userId);
  const project = await projectContext(conversation);
  const assistant = conversation.assistant_id ? await assistantContext(conversation.assistant_id) : null;
  // Long files: read the parts that match this question (and the one before it, for follow-ups).
  const lastUser = history.filter((m) => m.role === "user").at(-1)?.text ?? "";
  for (const k of [project, assistant]) {
    if (!k) continue;
    const chars = k.files.reduce((n, f) => n + (f.extracted_text?.length ?? 0), 0);
    if (chars > PROJECT_FILES_CHAR_BUDGET) {
      const { excerpts, top } = await projectExcerpts(k.files.filter((f) => f.extracted_text), `${parent.text} ${lastUser}`, PROJECT_EXCERPT_CHAR_BUDGET);
      Object.assign(k, { excerpts, topExcerpt: top });
    }
  }
  // Memory and chat history: never in temporary chats, and history only when memory is on.
  const useMemory = pers.memory_enabled && !conversation.is_temporary;
  const memory = useMemory ? (await getMemory(userId)).body : "";
  const pastChats = useMemory && pers.reference_chat_history ? await relatedExchanges(userId, conversation.id, parent.text) : [];
  // Apps the person @mentioned in this thread: their actions, if connected; a note if not.
  const tools: ToolSpec[] = [];
  const appNames: string[] = [];
  const missing: string[] = [];
  for (const id of mentionedApps([...history.filter((m) => m.role === "user").map((m) => m.text), parent.text])) {
    const p = appProvider(id)!;
    if (await activeConnection(userId, id)) {
      appNames.push(p.name);
      tools.push(...p.tools.map((t) => ({ name: t.name, description: t.description, input_schema: t.input_schema })));
    } else missing.push(p.name);
  }
  const appNote = missing.length
    ? `The person mentioned ${missing.join(" and ")}, which ${missing.length > 1 ? "aren't" : "isn't"} connected. Say so, and tell them to connect it in Apps (in the sidebar) first. Don't pretend to use it.`
    : null;
  const mode = webSearchMode();
  const searchAllowed = mode !== "off" && (!assistant || assistant.capabilities.includes("web_search"));
  return {
    tools,
    appNames,
    appNote,
    assistant,
    webSearch: !searchAllowed ? "off" : opts.forceSearch ? "forced" : mode === "auto" ? "auto" : "off",
    memory: memory || null,
    pastChats,
    model: conversation.model,
    prompt: parent.text,
    attachments,
    history: history.map((m) => ({
      role: m.role as "user" | "assistant",
      text: m.text,
      attachmentNames: files.filter((f) => f.message_id === m.id).map((f) => f.file.name),
    })),
    aboutYou: pers.about_you,
    responseStyle: pers.response_style,
    project,
  };
}

/** What's needed to pick an answer back up after an approval: tool rounds, the paused round, and what's shown. */
export type ResumeState = {
  steps: AgentStep[];
  turn: { assistantContent: unknown[]; calls: ToolCall[] };
  results: ToolResult[];
  index: number;
  text: string;
  activity: ActivityItem[];
  approvals: ApprovalBlock[];
  sources: Source[];
};
type ActivityItem = { app: string; text: string; ok: boolean };
type ApprovalBlock = Extract<ContentBlock, { type: "approval" }>;

/** The message's blocks: what the apps did, the text, approval cards, then sources. */
function compose(text: string, activity: ActivityItem[], approvals: ApprovalBlock[], sources: Source[]): ContentBlock[] {
  return [
    ...(activity.length ? [{ type: "tool_activity" as const, items: activity }] : []),
    { type: "text" as const, text },
    ...approvals,
    ...(sources.length && text ? [{ type: "sources" as const, items: sources }] : []),
  ];
}

const MAX_TOOL_ROUNDS = 8;

async function run(
  userId: string,
  conversation: Conversation,
  parent: Message,
  assistant: Message,
  abort: AbortController,
  opts: { forceImage?: boolean; forceSearch?: boolean; resume?: { state: ResumeState; decision: "approve" | "always" | "deny"; approvalId: string } },
) {
  let text = opts.resume?.state.text ?? "";
  let blocks: ContentBlock[] = [];
  let lastSave = 0;
  let stopped = false;
  let usage: { input_tokens: number; output_tokens: number; web_searches?: number } = { input_tokens: 0, output_tokens: 0 };
  const activity: ActivityItem[] = [...(opts.resume?.state.activity ?? [])];
  const approvals: ApprovalBlock[] = [...(opts.resume?.state.approvals ?? [])];

  // Persist progress; the returned row tells us if someone pressed Stop on another instance.
  const save = async (force = false) => {
    if (!force && Date.now() - lastSave < 400) return;
    lastSave = Date.now();
    const row = await patchMessage(assistant.id, { text, content: compose(text, activity, approvals, []) });
    if (row?.stop_requested && !abort.signal.aborted) abort.abort();
  };

  // An assistant can have image creation turned off; then image requests get a text answer.
  const setup = conversation.assistant_id ? await assistantContext(conversation.assistant_id) : null;
  const imagesOff = !!setup && !setup.capabilities.includes("image_generation");
  const wantsImage = !opts.resume && !imagesOff && (opts.forceImage || IMAGE_ASK.test(parent.text.trim()));
  if (wantsImage) {
    const prompt = parent.text.replace(/^\/image\s*/i, "").trim();
    const result = await generateImage(prompt, abort.signal);
    if (abort.signal.aborted) {
      stopped = true;
    } else if (result.ok) {
      const ext = result.mime === "image/svg+xml" ? "svg" : "png";
      const file = await saveGeneratedFile(userId, {
        name: `${prompt.slice(0, 40).replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "") || "image"}.${ext}`,
        mime: result.mime,
        bytes: result.bytes,
      });
      text = result.provider === "placeholder"
        ? `Here's a first pass at **${prompt.slice(0, 80)}**.\n\nThis is a placeholder render from the demo image generator. Once an image model is connected, the same request returns a real image. Tell me what to change: colours, layout, or the text on it.`
        : `Here's **${prompt.slice(0, 80)}**. Tell me what to change: colours, layout, framing, or the text on it.`;
      blocks = [{ type: "text", text }, { type: "image", file_id: file.id, alt: prompt.slice(0, 300) }];
      publish(assistant.id, { type: "delta", text });
      publish(assistant.id, { type: "content", content: blocks });
      await recordImage(userId, { conversation_id: conversation.id, message_id: assistant.id, prompt, output_file_id: file.id, provider: result.provider, status: "succeeded" });
      await recordUsage(userId, "image", `image:${assistant.id}`);
    } else {
      await recordImage(userId, { conversation_id: conversation.id, message_id: assistant.id, prompt, output_file_id: null, provider: result.provider, status: result.refused ? "refused" : "failed" });
      throw new ModelError(result.message, !result.refused);
    }
  } else {
    const ctx = await buildContext(userId, conversation, parent, { forceSearch: opts.forceSearch });
    let web: { title: string; url: string }[] = [];
    const sources: Source[] = opts.resume?.state.sources ?? [
      ...(ctx.memory ? [{ kind: "memory" } as const] : []),
      ...(ctx.pastChats ?? []).map((c): Source => ({ kind: "chat", conversation_id: c.conversation_id, title: c.title })),
    ];
    const steps: AgentStep[] = [...(opts.resume?.state.steps ?? [])];
    const showContent = () => publish(assistant.id, { type: "content", content: compose(text, activity, approvals, []) });

    /**
     * Runs a round's app actions from `from`, in order. Pauses (returns false) at the first one that
     * needs the person's go-ahead, saving everything needed to continue.
     */
    const runCalls = async (turn: ResumeState["turn"], results: ToolResult[], from: number): Promise<boolean> => {
      for (let i = from; i < turn.calls.length; i++) {
        const call = turn.calls[i];
        const owner = toolOwner(call.name);
        const conn = owner ? await activeConnection(userId, owner.provider.id) : null;
        if (owner && conn && needsApproval(conn.permission_level, owner.tool.importance, conn.always_allowed, call.name)) {
          const card: Omit<ApprovalBlock, "approval_id"> = {
            type: "approval", app: owner.provider.name, action: owner.tool.describe(call.input).replace(/^(\w+ed)/, (w) => ACTION_ASK[w] ?? w),
            fields: owner.tool.preview(call.input), status: "pending",
          };
          const id = await createApproval({
            user_id: userId, connection_id: conn.id, message_id: assistant.id, action: call.name, importance: owner.tool.importance,
            payload_preview: { app: card.app, action: card.action, fields: card.fields }, tool_use_id: call.id, tool_name: call.name,
            state: { steps, turn, results, index: i, text, activity, approvals: [], sources } satisfies ResumeState,
          });
          approvals.push({ ...card, approval_id: id });
          return false;
        }
        publish(assistant.id, { type: "status", text: owner ? `Using ${owner.provider.name}` : "Working" });
        const r = await runTool(userId, call.name, call.input);
        results.push({ tool_use_id: call.id, content: r.result, is_error: !r.ok });
        activity.push({ app: owner?.provider.name ?? "App", text: r.ok ? owner!.tool.describe(call.input) : r.summary, ok: r.ok });
        showContent();
      }
      steps.push({ assistantContent: turn.assistantContent, calls: turn.calls, results });
      return true;
    };

    let paused = false;
    if (opts.resume) {
      // The decision on the paused action, then the rest of that round.
      const { state, decision } = opts.resume;
      const call = state.turn.calls[state.index];
      const owner = toolOwner(call.name);
      const results = [...state.results];
      if (decision === "deny") {
        results.push({ tool_use_id: call.id, content: "The person declined this action. Don't retry it; say it wasn't done.", is_error: true });
        activity.push({ app: owner?.provider.name ?? "App", text: `Declined: ${owner?.tool.describe(call.input) ?? call.name}`, ok: false });
      } else {
        const r = await runTool(userId, call.name, call.input);
        results.push({ tool_use_id: call.id, content: r.result, is_error: !r.ok });
        activity.push({ app: owner?.provider.name ?? "App", text: r.ok ? owner!.tool.describe(call.input) : r.summary, ok: r.ok });
        await finishApproval(opts.resume.approvalId, r.summary);
      }
      showContent();
      paused = !(await runCalls(state.turn, results, state.index + 1));
    }

    for (let round = 0; !paused && round < MAX_TOOL_ROUNDS; round++) {
      let turn: ResumeState["turn"] | null = null;
      if (text && !/\n\n$/.test(text) && steps.length) {
        text += "\n\n";
        publish(assistant.id, { type: "delta", text: "\n\n" });
      }
      for await (const chunk of streamAnswer({ ...ctx, steps }, abort.signal)) {
        if (chunk.type === "usage") {
          usage = {
            input_tokens: usage.input_tokens + chunk.input_tokens,
            output_tokens: usage.output_tokens + chunk.output_tokens,
            web_searches: (usage.web_searches ?? 0) + (chunk.web_searches ?? 0),
          };
          continue;
        }
        if (chunk.type === "searching") {
          publish(assistant.id, { type: "status", text: chunk.query ? `Searching the web: ${chunk.query}` : "Searching the web" });
          continue;
        }
        if (chunk.type === "web_sources") {
          web = chunk.items;
          continue;
        }
        if (chunk.type === "tool_calls") {
          turn = { assistantContent: chunk.assistantContent, calls: chunk.calls };
          continue;
        }
        text += chunk.text;
        publish(assistant.id, { type: "delta", text: chunk.text });
        await save();
      }
      if (abort.signal.aborted || !turn) break;
      paused = !(await runCalls(turn, [], 0));
    }
    stopped = abort.signal.aborted;
    // Web sources first, in citation order ([1], [2], …).
    sources.unshift(...web.filter((w) => !sources.some((x) => x.kind === "web" && x.url === w.url)).map((w): Source => ({ kind: "web", title: w.title, url: w.url })));
    blocks = compose(text, activity, approvals, sources);
    if (blocks.length > 1) publish(assistant.id, { type: "content", content: blocks });
  }

  if (!stopped) {
    const row = await messageRow(assistant.id);
    stopped = !!row?.stop_requested;
  }
  const status: Message["status"] = stopped ? "stopped" : "complete";
  await patchMessage(assistant.id, { text, content: blocks, status });
  // A continuation after an approval is part of the same message: counted once, at the start.
  if (!opts.resume) await recordUsage(userId, "message", `message:${assistant.id}`, { model: conversation.model, ...usage });

  if (conversation.title === "New chat") {
    const first = threadPath(await messagesForConversation(conversation.id), parent.id).find((m) => m.role === "user");
    const title = await makeTitle(first?.text ?? parent.text);
    await updateConversation(userId, conversation.id, { title });
    publish(assistant.id, { type: "title", title });
  }
  publish(assistant.id, { type: "done", status });
  // Keep memory current (at most hourly). Failures never affect the answer.
  if (!conversation.is_temporary) await refreshMemory(userId).catch((e) => console.error("[memory]", (e as Error)?.message));
}

/** "Searched …" → "Search …" for the approval card's question. */
const ACTION_ASK: Record<string, string> = {
  Searched: "Search", Read: "Read", Created: "Create", Posted: "Post", Updated: "Update",
};

/**
 * The person decided on an approval card: record it, then continue the same answer from where it paused.
 * Returns the message (for its stream) and the task's promise.
 */
export async function resumeAfterApproval(userId: string, approvalId: string, decision: "approve" | "always" | "deny") {
  const a = await takeApproval(userId, approvalId, decision);
  const assistant = await messageRow(a.message_id);
  if (!assistant) throw new HttpError(404, "That answer no longer exists.");
  const conversation = await conversationRow(assistant.conversation_id);
  const parent = assistant.parent_id ? await messageRow(assistant.parent_id) : null;
  if (!conversation || !parent) throw new HttpError(404, "That chat no longer exists.");
  if (decision === "always") await allowAlways(userId, a.connection_id, a.tool_name);
  const state = a.state as ResumeState;
  // The card shows the decision; the answer streams on below it.
  const status: ApprovalBlock["status"] = decision === "deny" ? "denied" : "approved";
  const approvals = (assistant.content.filter((b) => b.type === "approval") as ApprovalBlock[]).map((b) => (b.approval_id === approvalId ? { ...b, status } : b));
  const resumeState: ResumeState = { ...state, approvals };
  await patchMessage(assistant.id, { status: "streaming", content: compose(state.text, state.activity, approvals, []) });
  const abort = new AbortController();
  live.set(assistant.id, { listeners: new Set(), abort });
  const done = run(userId, conversation, parent, assistant, abort, { resume: { state: resumeState, decision, approvalId } })
    .catch(async (err) => {
      console.error("[generation]", (err as Error)?.message);
      const msg = err instanceof ModelError ? err.message : "Something went wrong while answering.";
      await patchMessage(assistant.id, { status: "error", error: msg }).catch(() => {});
      publish(assistant.id, { type: "done", status: "error", error: msg });
    })
    .finally(() => live.delete(assistant.id));
  return { assistant: { ...assistant, status: "streaming" as const }, done };
}

const enc = new TextEncoder();
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** SSE: the message's current state, then live updates until it finishes. Works on any instance. */
export function sseFor(message: Message, prelude: GenEvent[] = []) {
  let closed = false;
  let unsubscribe = () => {};
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (e: GenEvent) => {
        if (!closed) controller.enqueue(enc.encode(`event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`));
      };
      const finish = () => {
        if (!closed) {
          closed = true;
          controller.close();
        }
      };
      prelude.forEach(send);
      const current = (await messageRow(message.id)) ?? message;
      send({ type: "snapshot", text: current.text, content: current.content });

      const l = live.get(message.id);
      if (l) {
        const fn = (e: GenEvent) => {
          send(e);
          if (e.type === "done") {
            l.listeners.delete(fn);
            finish();
          }
        };
        l.listeners.add(fn);
        unsubscribe = () => l.listeners.delete(fn);
        return;
      }
      if (current.status !== "streaming") {
        send({ type: "done", status: current.status, error: current.error });
        return finish();
      }
      // Generated on another instance: follow the row.
      let seen = current.text;
      const deadline = Date.now() + 15 * 60_000;
      while (!closed && Date.now() < deadline) {
        await sleep(500);
        const row = await messageRow(message.id);
        if (!row) break;
        if (row.text.startsWith(seen) && row.text.length > seen.length) send({ type: "delta", text: row.text.slice(seen.length) });
        else if (!row.text.startsWith(seen)) send({ type: "snapshot", text: row.text, content: row.content });
        seen = row.text;
        if (row.status !== "streaming") {
          if (row.content.some((b) => b.type === "image" || b.type === "sources")) send({ type: "content", content: row.content });
          send({ type: "done", status: row.status, error: row.error });
          break;
        }
      }
      finish();
    },
    cancel() {
      closed = true;
      unsubscribe();
    },
  });
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no" },
  });
}
