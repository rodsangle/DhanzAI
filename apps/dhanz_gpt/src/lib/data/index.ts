import "server-only";
import { TRANSCRIBE_MAX_BYTES, transcribe, transcribeProvider } from "@/lib/ai/transcribe";
import { ExtractError, TOKEN_LIMITS, chunkText, estimateTokens, extractKind, extractText, formatTokens } from "@/lib/server/extract";
import { asService, asUser, type Tx } from "@/lib/server/db";
import { putObject, readObject, statObject, uploadTarget } from "@/lib/server/storage";
import { HttpError } from "./errors";
import {
  LIMITS, type ContentBlock, type Conversation, type ConversationDetail, type ConversationListItem, type FileRow, type ImageGeneration,
  type Memory, type Message, type MessageOptions, type Personalization, type Profile, type Project, type ProjectDetail, type SearchResult, type SharedLink,
  type UsageEvent, type Workspace,
} from "./types";

/**
 * Data layer on Postgres. Signatures match the demo layer the screens were built on.
 * User reads and writes run through `asUser`, so the RLS policies in schema.sql decide access;
 * the explicit checks here only turn "no row" into the right 403/404 message.
 */

export { HttpError };
export * from "./assistants";
export * from "./tasks";
export * from "./space";
const notFound = (what = "Not found") => new HttpError(404, what);
const forbidden = () => new HttpError(403, "You don't have access to this.");

/** File row for the browser: the extracted text stays on the server. */
const toFile = (r: Record<string, unknown>): FileRow => {
  const { extracted_text: _text, ...rest } = r;
  void _text;
  return { ...(rest as unknown as FileRow), bytes: Number(r.bytes) };
};
/** File row with its text, for the answer generator only. */
const toFileWithText = (r: Record<string, unknown>): FileRow => ({ ...(r as unknown as FileRow), bytes: Number(r.bytes) });

/* ------------------------------------------------------------------ people */

export async function getProfile(userId: string): Promise<Profile | null> {
  const [p] = await asService((q) => q<Profile[]>`select id, email, name, avatar_url, theme, locale from profiles where id = ${userId}`);
  return p ?? null;
}

export async function getWorkspaceFor(userId: string): Promise<{ workspace: Workspace; role: string }> {
  const [r] = await asService(
    (q) => q`select w.id, w.name, w.allowed_email_domain, w.settings, m.role
             from memberships m join workspaces w on w.id = m.workspace_id where m.user_id = ${userId} limit 1`,
  );
  if (!r) throw forbidden();
  const { role, ...workspace } = r;
  return { workspace: workspace as unknown as Workspace, role: role as string };
}

export async function listWorkspaceMembers(userId: string) {
  return asUser(userId, (q) => q<(Profile & { role: string })[]>`
    select p.id, p.email, p.name, p.avatar_url, p.theme, p.locale, m.role
    from memberships m join profiles p on p.id = m.user_id
    where m.workspace_id = (select workspace_id from memberships where user_id = ${userId} limit 1)
    order by p.name`);
}

/** Demo sign-in only (AUTH_MODE=dev). */
export async function devSignIn(email: string) {
  const [p] = await asService((q) => q<Profile[]>`select id, email, name from profiles where lower(email) = lower(${email.trim()})`);
  if (!p) throw new HttpError(403, "That email isn't part of this workspace.");
  return p;
}

/* ------------------------------------------------------------------ conversations */

const listCols = (q: Tx) => q`
  c.id, c.title, c.project_id, c.last_message_at, c.archived_at is not null as archived,
  exists (select 1 from messages m where m.conversation_id = c.id and m.status = 'streaming') as streaming`;

export async function listConversations(userId: string, opts: { archived?: boolean } = {}): Promise<ConversationListItem[]> {
  return asUser(userId, (q) => q<ConversationListItem[]>`
    select ${listCols(q)} from conversations c
    where c.user_id = ${userId} and not c.is_temporary and (c.archived_at is not null) = ${!!opts.archived}
    order by c.last_message_at desc limit 500`);
}

export async function getConversationDetail(userId: string, id: string): Promise<ConversationDetail> {
  return asUser(userId, async (q) => {
    const [c] = await q<Conversation[]>`select * from conversations where id = ${id}`;
    if (!c) throw notFound("This chat doesn't exist or isn't shared with you.");
    const messages = await q<Message[]>`
      select id, conversation_id, parent_id, user_id, role, content, text, model, status, error, feedback, created_at, updated_at
      from messages where conversation_id = ${id} order by created_at`;
    const [project] = c.project_id ? await q<{ id: string; name: string }[]>`select id, name from projects where id = ${c.project_id}` : [];
    const [share] = await q<SharedLink[]>`select slug, updated_at, visibility from shared_links where conversation_id = ${id} and owner_id = ${userId}`;
    const [assistant] = c.assistant_id
      ? await q<NonNullable<ConversationDetail["assistant"]>[]>`select id, name, starters, capabilities from assistants where id = ${c.assistant_id}`
      : [];
    return {
      conversation: c,
      messages,
      project: project ?? null,
      assistant: assistant ?? null,
      share: share ? { slug: share.slug, updated_at: share.updated_at, visibility: share.visibility } : null,
      can_edit: c.user_id === userId,
    };
  });
}

export async function createConversation(
  userId: string,
  input: { project_id?: string | null; assistant_id?: string | null; model: string; is_temporary?: boolean; kind?: Conversation["kind"]; title?: string },
) {
  const { workspace } = await getWorkspaceFor(userId);
  return asUser(userId, async (q) => {
    if (input.project_id) {
      const [{ ok }] = await q`select can_edit_project(${input.project_id}) as ok`;
      if (!ok) throw forbidden();
    }
    if (input.assistant_id) {
      // RLS: only assistants this person can see (their own, or the team's).
      const [a] = await q`select id from assistants where id = ${input.assistant_id}`;
      if (!a) throw notFound("This assistant doesn't exist or isn't shared with you.");
    }
    const [c] = await q<Conversation[]>`
      insert into conversations (workspace_id, user_id, project_id, assistant_id, model, is_temporary, kind, title)
      values (${workspace.id}, ${userId}, ${input.project_id ?? null}, ${input.assistant_id ?? null}, ${input.model}, ${!!input.is_temporary},
              ${input.kind ?? "chat"}, ${input.title ?? "New chat"})
      returning *`;
    return c;
  });
}

async function ownConversation(q: Tx, userId: string, id: string) {
  const [c] = await q<Conversation[]>`select * from conversations where id = ${id}`;
  if (!c) throw notFound("This chat doesn't exist or isn't shared with you.");
  if (c.user_id !== userId) throw forbidden();
  return c;
}

export async function updateConversation(
  userId: string,
  id: string,
  patch: { title?: string; archived?: boolean; project_id?: string | null; current_leaf_id?: string; model?: string },
) {
  return asUser(userId, async (q) => {
    await ownConversation(q, userId, id);
    if (patch.title !== undefined) {
      const title = patch.title.trim();
      if (!title) throw new HttpError(400, "Give the chat a name.");
      await q`update conversations set title = ${title.slice(0, LIMITS.titleMax)} where id = ${id}`;
    }
    if (patch.archived !== undefined) await q`update conversations set archived_at = ${patch.archived ? q`now()` : null} where id = ${id}`;
    if (patch.project_id !== undefined) {
      if (patch.project_id) {
        const [{ ok }] = await q`select can_edit_project(${patch.project_id}) as ok`;
        if (!ok) throw forbidden();
      }
      await q`update conversations set project_id = ${patch.project_id} where id = ${id}`;
    }
    if (patch.current_leaf_id) {
      const [m] = await q`select id from messages where id = ${patch.current_leaf_id} and conversation_id = ${id}`;
      if (!m) throw new HttpError(400, "That version isn't part of this chat.");
      await q`update conversations set current_leaf_id = ${patch.current_leaf_id} where id = ${id}`;
    }
    if (patch.model) await q`update conversations set model = ${patch.model} where id = ${id}`;
    const [c] = await q<Conversation[]>`select * from conversations where id = ${id}`;
    return c;
  });
}

export async function deleteConversation(userId: string, id: string) {
  await asUser(userId, async (q) => {
    await ownConversation(q, userId, id);
    await q`delete from conversations where id = ${id}`;
  });
}

/* ------------------------------------------------------------------ messages (system writes) */

export async function insertMessage(m: Omit<Message, "id" | "created_at" | "updated_at"> & { id?: string }) {
  return asService(async (q) => {
    const [row] = await q<Message[]>`
      insert into messages (conversation_id, parent_id, user_id, role, content, text, model, status, error, feedback)
      values (${m.conversation_id}, ${m.parent_id}, ${m.user_id}, ${m.role}, ${q.json(m.content as never)}, ${m.text},
              ${m.model}, ${m.status}, ${m.error}, ${m.feedback})
      returning id, conversation_id, parent_id, user_id, role, content, text, model, status, error, feedback, created_at, updated_at`;
    await q`update conversations set current_leaf_id = ${row.id}, last_message_at = ${row.created_at}::timestamptz where id = ${row.conversation_id}`;
    return row;
  });
}

/**
 * Adds the person's message to a chat. The chat row is locked so two sends at the same moment
 * (two tabs, a double submit) are serialized: the second sees the first's message as the latest
 * and is refused while that answer runs or is about to start, instead of forking the thread.
 * parent "leaf" = reply to whatever is latest now; an id = branch from there (edits); null = new root.
 */
export async function insertUserMessage(m: { conversation_id: string; user_id: string; text: string; parent: "leaf" | string | null; options?: MessageOptions }) {
  return asService(async (q) => {
    const [c] = await q<{ current_leaf_id: string | null }[]>`
      select current_leaf_id from conversations where id = ${m.conversation_id} for update`;
    if (!c) throw notFound();
    const parentId = m.parent === "leaf" ? c.current_leaf_id : m.parent;
    if (parentId) {
      // A user message as the latest means its answer is about to start; after a minute it's an orphan, not a lock.
      const [p] = await q<{ role: string; status: string; fresh: boolean }[]>`
        select role, status, created_at > now() - interval '1 minute' as fresh from messages where id = ${parentId}`;
      if (p?.status === "streaming" || (m.parent === "leaf" && p?.role === "user" && p.fresh))
        throw new HttpError(409, "Wait for the current answer to finish, or stop it first.");
    }
    const [row] = await q<Message[]>`
      insert into messages (conversation_id, parent_id, user_id, role, content, text, model, status, error, feedback, options)
      values (${m.conversation_id}, ${parentId}, ${m.user_id}, 'user', ${q.json([{ type: "text", text: m.text }] as never)}, ${m.text},
              null, 'complete', null, null, ${q.json((m.options ?? {}) as never)})
      returning id, conversation_id, parent_id, user_id, role, content, text, model, status, error, feedback, created_at, updated_at`;
    await q`update conversations set current_leaf_id = ${row.id}, last_message_at = ${row.created_at}::timestamptz where id = ${m.conversation_id}`;
    return row;
  });
}

/** The choices saved with a message (image mode, size, search, think longer). */
export async function messageOptions(id: string): Promise<MessageOptions> {
  return asService(async (q) => {
    const [row] = await q<{ options: MessageOptions }[]>`select options from messages where id = ${id}`;
    return row?.options ?? {};
  });
}

export async function patchMessage(id: string, patch: Partial<Pick<Message, "text" | "content" | "status" | "error">>) {
  return asService(async (q) => {
    const [row] = await q<(Message & { stop_requested: boolean })[]>`
      update messages set
        text = coalesce(${patch.text ?? null}, text),
        content = coalesce(${patch.content ? q.json(patch.content as never) : null}::jsonb, content),
        status = coalesce(${patch.status ?? null}, status),
        error = case when ${patch.error !== undefined} then ${patch.error ?? null} else error end
      where id = ${id}
      returning id, status, stop_requested`;
    return row ?? null;
  });
}

export async function getMessage(userId: string, id: string) {
  const [m] = await asUser(userId, (q) => q<Message[]>`
    select id, conversation_id, parent_id, user_id, role, content, text, model, status, error, feedback, created_at, updated_at
    from messages where id = ${id}`);
  if (!m) throw notFound();
  return m;
}

export async function getOwnMessage(userId: string, id: string) {
  return asUser(userId, async (q) => {
    const [m] = await q<Message[]>`
      select id, conversation_id, parent_id, user_id, role, content, text, model, status, error, feedback, created_at, updated_at
      from messages where id = ${id}`;
    if (!m) throw notFound();
    const conversation = await ownConversation(q, userId, m.conversation_id);
    return { message: m, conversation };
  });
}

export async function setFeedback(userId: string, id: string, feedback: -1 | 1 | null) {
  const { message } = await getOwnMessage(userId, id);
  if (message.role !== "assistant") throw new HttpError(400, "Only answers can be rated.");
  await asService((q) => q`update messages set feedback = ${feedback} where id = ${id}`);
  return { ...message, feedback };
}

export async function requestStopFlag(userId: string, id: string) {
  const { message } = await getOwnMessage(userId, id);
  if (message.status !== "streaming") return false;
  await asService((q) => q`update messages set stop_requested = true where id = ${id}`);
  return true;
}

/** Path from the root to `leafId` (inclusive), in order. */
export function threadPath(messages: Message[], leafId: string | null) {
  const byId = new Map(messages.map((m) => [m.id, m]));
  const out: Message[] = [];
  let cur = leafId ? byId.get(leafId) : undefined;
  while (cur) {
    out.unshift(cur);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return out;
}

/** System read for the generator: every message in a conversation. */
export async function messagesForConversation(conversationId: string) {
  return asService((q) => q<Message[]>`
    select id, conversation_id, parent_id, user_id, role, content, text, model, status, error, feedback, created_at, updated_at
    from messages where conversation_id = ${conversationId} order by created_at`);
}

/** System read of a chat row (the generator resuming an answer). */
export async function conversationRow(id: string) {
  const [c] = await asService((q) => q<Conversation[]>`select * from conversations where id = ${id}`);
  return c ?? null;
}

export async function messageRow(id: string) {
  const [m] = await asService((q) => q<(Message & { stop_requested: boolean })[]>`select * from messages where id = ${id}`);
  return m ?? null;
}

/**
 * Checks files before a message is saved: visible to the sender, finished uploading, and
 * small enough together to read in one answer. Bigger sets belong in a project.
 */
export async function checkAttachments(userId: string, fileIds: string[]) {
  if (fileIds.length > LIMITS.attachmentsPerMessage) throw new HttpError(400, `Attach up to ${LIMITS.attachmentsPerMessage} files at a time.`);
  if (!fileIds.length) return [];
  const files = await asUser(userId, (q) => q`select * from files where id = any(${fileIds}::uuid[])`);
  const rows = files.map(toFile);
  for (const id of fileIds) {
    const f = rows.find((x) => x.id === id);
    if (!f) throw new HttpError(400, "One of the attached files isn't available.");
    if (f.status !== "ready") throw new HttpError(409, `${f.name} is still uploading.`);
  }
  const total = rows.reduce((n, f) => n + (f.token_count ?? 0), 0);
  if (total > TOKEN_LIMITS.perMessage) {
    const what = rows.length === 1 ? `${rows[0].name} is` : "These files are";
    throw new HttpError(
      413,
      `${what} about ${formatTokens(total)} tokens, more than one message can read (${formatTokens(TOKEN_LIMITS.perMessage)}). ` +
        `Add ${rows.length === 1 ? "it" : "them"} to a project instead: project chats read the parts that matter to each question.`,
    );
  }
  return rows;
}

export async function attachFiles(userId: string, messageId: string, fileIds: string[]) {
  const rows = await checkAttachments(userId, fileIds);
  if (!rows.length) return [];
  await asService(async (q) => {
    for (const id of fileIds) await q`insert into message_files (message_id, file_id) values (${messageId}, ${id}) on conflict do nothing`;
  });
  return rows;
}

export async function filesForMessages(messageIds: string[]) {
  if (!messageIds.length) return [];
  const rows = await asService((q) => q`
    select mf.message_id, f.* from message_files mf join files f on f.id = mf.file_id
    where mf.message_id = any(${messageIds}::uuid[])`);
  return rows.map((r) => ({ message_id: r.message_id as string, file: toFileWithText(r) }));
}

/* ------------------------------------------------------------------ projects */

export async function listProjects(userId: string) {
  return asUser(userId, (q) => q<{ id: string; name: string; shared: boolean }[]>`
    select p.id, p.name,
      (p.owner_id <> ${userId} or exists (select 1 from project_members pm where pm.project_id = p.id)) as shared
    from projects p where p.archived_at is null order by p.updated_at desc`);
}

export async function getProjectDetail(userId: string, id: string): Promise<ProjectDetail> {
  return asUser(userId, async (q) => {
    const [project] = await q<Project[]>`select * from projects where id = ${id}`;
    if (!project) throw notFound("This project doesn't exist or isn't shared with you.");
    const conversations = await q<ConversationListItem[]>`
      select ${listCols(q)} from conversations c
      where c.project_id = ${id} and not c.is_temporary and c.archived_at is null
      order by c.last_message_at desc`;
    const files = (await q`
      select f.* from project_files pf join files f on f.id = pf.file_id
      where pf.project_id = ${id} and f.deleted_at is null order by pf.created_at`).map(toFile);
    const members = await q<ProjectDetail["members"]>`
      select pm.id, pm.project_id, pm.user_id, pm.role, p.name, p.email
      from project_members pm join profiles p on p.id = pm.user_id where pm.project_id = ${id} order by p.name`;
    const [{ can_edit }] = await q`select can_edit_project(${id}) as can_edit`;
    return { project, conversations, files, members, can_edit: !!can_edit, is_owner: project.owner_id === userId };
  });
}

function checkProjectName(name: string) {
  const n = name.trim();
  if (!n) throw new HttpError(400, "Give the project a name.");
  if (n.length > LIMITS.projectNameMax) throw new HttpError(400, `Keep the name under ${LIMITS.projectNameMax} characters.`);
  return n;
}

export async function createProject(userId: string, input: { name: string; instructions?: string }) {
  const name = checkProjectName(input.name);
  const { workspace } = await getWorkspaceFor(userId);
  const [p] = await asUser(userId, (q) => q<Project[]>`
    insert into projects (workspace_id, owner_id, name, instructions)
    values (${workspace.id}, ${userId}, ${name}, ${(input.instructions ?? "").slice(0, LIMITS.instructionsMax)}) returning *`);
  return p;
}

export async function updateProject(userId: string, id: string, patch: { name?: string; instructions?: string; memory_mode?: Project["memory_mode"] }) {
  return asUser(userId, async (q) => {
    const [p] = await q<Project[]>`select * from projects where id = ${id}`;
    if (!p) throw notFound();
    const [{ ok }] = await q`select can_edit_project(${id}) as ok`;
    if (!ok) throw forbidden();
    if (patch.instructions !== undefined && patch.instructions.length > LIMITS.instructionsMax) throw new HttpError(400, "Instructions are too long.");
    const [row] = await q<Project[]>`
      update projects set
        name = ${patch.name !== undefined ? checkProjectName(patch.name) : p.name},
        instructions = ${patch.instructions ?? p.instructions},
        memory_mode = ${patch.memory_mode ?? p.memory_mode}
      where id = ${id} returning *`;
    return row;
  });
}

export async function deleteProject(userId: string, id: string) {
  await asUser(userId, async (q) => {
    const [p] = await q<Project[]>`select * from projects where id = ${id}`;
    if (!p) throw notFound();
    if (p.owner_id !== userId) throw forbidden();
    await q`delete from projects where id = ${id}`; // chats cascade (schema.sql)
  });
}

export async function addProjectFile(userId: string, projectId: string, fileId: string) {
  await asUser(userId, async (q) => {
    const [{ ok }] = await q`select can_edit_project(${projectId}) as ok`;
    if (!ok) throw forbidden();
    const [f] = await q`select id from files where id = ${fileId} and owner_id = ${userId}`;
    if (!f) throw new HttpError(400, "You can only add your own files.");
    await q`insert into project_files (project_id, file_id, added_by) values (${projectId}, ${fileId}, ${userId}) on conflict do nothing`;
  });
}

export async function removeProjectFile(userId: string, projectId: string, fileId: string) {
  await asUser(userId, async (q) => {
    const [{ ok }] = await q`select can_edit_project(${projectId}) as ok`;
    if (!ok) throw forbidden();
    await q`delete from project_files where project_id = ${projectId} and file_id = ${fileId}`;
  });
}

export async function setProjectMember(userId: string, projectId: string, memberId: string, role: "viewer" | "editor" | null) {
  await asUser(userId, async (q) => {
    const [p] = await q<Project[]>`select * from projects where id = ${projectId}`;
    if (!p || p.owner_id !== userId) throw forbidden();
    const [{ same }] = await q`select shares_workspace(${memberId}) as same`;
    if (!same) throw new HttpError(400, "You can only share with people in your workspace.");
    await q`delete from project_members where project_id = ${projectId} and user_id = ${memberId}`;
    if (role) await q`insert into project_members (project_id, user_id, role) values (${projectId}, ${memberId}, ${role})`;
  });
}

/** System read for the generator: project name, instructions and readable files. */
export async function projectContext(conversation: Conversation) {
  if (!conversation.project_id) return null;
  return asService(async (q) => {
    const [p] = await q<Project[]>`select * from projects where id = ${conversation.project_id}`;
    if (!p) return null;
    const files = (await q`
      select f.* from project_files pf join files f on f.id = pf.file_id
      where pf.project_id = ${p.id} and f.deleted_at is null and f.status = 'ready' order by pf.created_at`).map(toFileWithText);
    return { name: p.name, instructions: p.instructions, files };
  });
}

/** Words worth searching for, as an OR query: "what does the tech pack say about crown height" → tech | pack | crown | height. */
export function searchTerms(text: string, max = 40): string | null {
  // Letters and digits only, so nothing can be read as tsquery syntax.
  const words = [...new Set(text.toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) ?? [])];
  return words.length ? words.slice(0, max).join(" | ") : null;
}

export type Excerpt = { file_id: string; name: string; chunks: { idx: number; content: string }[] };

/**
 * The parts of long project files that matter to a question: each file's opening chunk
 * (what the document is), then the best-matching chunks by full-text rank, within a budget.
 * Chunks come back in reading order per file.
 */
export async function projectExcerpts(
  files: { id: string; name: string }[],
  question: string,
  charBudget: number,
): Promise<{ excerpts: Excerpt[]; top: { name: string; content: string } | null }> {
  if (!files.length) return { excerpts: [], top: null };
  const ids = files.map((f) => f.id);
  const terms = searchTerms(question);
  const picked = await asService(async (q) => {
    const firsts = await q<{ file_id: string; idx: number; content: string }[]>`
      select file_id, idx, content from file_chunks where file_id = any(${ids}::uuid[]) and idx = 0`;
    const ranked = terms
      ? await q<{ file_id: string; idx: number; content: string }[]>`
          select file_id, idx, content from file_chunks, to_tsquery('english', ${terms}) query
          where file_id = any(${ids}::uuid[]) and idx > 0 and tsv @@ query
          order by ts_rank_cd(tsv, query) desc, idx limit 200`
      : [];
    return [...ranked.slice(0, 8), ...firsts, ...ranked.slice(8)];
  });
  // Best matches first, then openings, until the budget is spent.
  let left = charBudget;
  const chosen: typeof picked = [];
  for (const c of picked) {
    if (c.content.length > left) continue;
    left -= c.content.length;
    chosen.push(c);
  }
  const best = picked.find((c) => c.idx > 0) ?? picked[0];
  const top = best ? { name: files.find((f) => f.id === best.file_id)?.name ?? "", content: best.content } : null;
  const excerpts = files
    .map((f) => ({
      file_id: f.id,
      name: f.name,
      chunks: chosen.filter((c) => c.file_id === f.id).sort((a, b) => a.idx - b.idx).map(({ idx, content }) => ({ idx, content })),
    }))
    .filter((e) => e.chunks.length);
  return { excerpts, top };
}

/* ------------------------------------------------------------------ files */

const STORAGE_QUOTA_BYTES = Number(process.env.STORAGE_QUOTA_BYTES ?? 20 * 1024 ** 3);
const UPLOADS_PER_10_MIN = 60;

/** Storage the person's files use against their quota. Files in Recently deleted don't count. */
export async function storageUsage(userId: string) {
  const [{ used }] = await asService((q) => q`
    select coalesce(sum(bytes) filter (where deleted_at is null), 0)::bigint as used from files where owner_id = ${userId}`);
  return { used: Number(used), quota: STORAGE_QUOTA_BYTES };
}

export async function createUpload(userId: string, input: { name: string; mime: string; bytes: number; temporary?: boolean }) {
  const { workspace } = await getWorkspaceFor(userId);
  const name = input.name.trim().replace(/[/\\]/g, "_").slice(0, 255);
  if (!name) throw new HttpError(400, "The file needs a name.");
  if (!(input.bytes > 0)) throw new HttpError(400, "That file is empty.");
  if (input.bytes > LIMITS.fileBytes) throw new HttpError(413, `${name} is over the 512 MB limit.`);
  return asService(async (q) => {
    const [{ used, recent }] = await q`
      select coalesce(sum(bytes) filter (where deleted_at is null), 0)::bigint as used,
             count(*) filter (where created_at > now() - interval '10 minutes') as recent
      from files where owner_id = ${userId}`;
    if (Number(recent) >= UPLOADS_PER_10_MIN) throw new HttpError(429, "That's a lot of uploads at once. Try again in a few minutes.");
    if (Number(used) + input.bytes > STORAGE_QUOTA_BYTES) throw new HttpError(413, "Your file storage is full. Delete some files in Library to make room.");
    const [f] = await q`
      insert into files (workspace_id, owner_id, name, mime, bytes, storage_path, status, is_temporary)
      values (${workspace.id}, ${userId}, ${name}, ${input.mime || "application/octet-stream"}, ${input.bytes},
              ${userId} || '/' || gen_random_uuid() || '/' || ${name}, 'uploading', ${!!input.temporary})
      returning *`;
    const file = toFile(f);
    const target = await uploadTarget(file.id, file.storage_path);
    return { file, upload_url: target.url, upload_mode: target.mode };
  });
}

/** Local driver only: the bytes arrive through the app. */
export async function receiveUpload(userId: string, id: string, bytes: Buffer) {
  const [f] = await asService((q) => q`select * from files where id = ${id} and owner_id = ${userId}`);
  if (!f) throw notFound();
  const file = toFile(f);
  if (file.status !== "uploading") throw new HttpError(409, "This upload is already finished.");
  if (bytes.length !== file.bytes) throw new HttpError(400, "The upload was incomplete. Try again.");
  await putObject(file.storage_path, bytes, file.mime);
}

/** Audio the transcription service takes (it also reads the audio track of mp4/webm). */
function isAudio(mime: string, name: string) {
  return /^audio\//.test(mime) || /\.(mp3|m4a|wav|webm|ogg|oga|flac|mpga|mpeg)$/i.test(name);
}

export async function completeUpload(userId: string, id: string) {
  const [f] = await asService((q) => q`select * from files where id = ${id} and owner_id = ${userId}`);
  if (!f) throw notFound();
  const file = toFile(f);
  if (file.status === "ready") return file;
  const size = await statObject(file.storage_path);
  let status: FileRow["status"] = "ready";
  let error: string | null = null;
  let text: string | null = null;
  let tokens: number | null = null;
  const kind = extractKind(file.mime, file.name);
  const audio = isAudio(file.mime, file.name);
  if (size === null) {
    status = "error";
    error = "We didn't receive the file. Try again.";
  } else if (size !== file.bytes) {
    status = "error";
    error = "The upload was incomplete. Try again.";
  } else if (kind) {
    try {
      const bytes = await readObject(file.storage_path);
      text = bytes ? await extractText(bytes, kind) : null;
    } catch (e) {
      if (!(e instanceof ExtractError)) throw e;
      status = "error";
      error = e.message;
    }
  } else if (audio && transcribeProvider() !== "off" && file.bytes <= TRANSCRIBE_MAX_BYTES) {
    // A recording (meeting, voice note): its transcript is what chats and projects read.
    const bytes = await readObject(file.storage_path);
    const r = bytes
      ? await transcribe(new Blob([new Uint8Array(bytes)], { type: file.mime }), file.name, undefined, "A recording: a meeting, interview or voice note.")
      : null;
    if (r?.ok && r.text.trim()) text = `Transcript of the recording ${file.name}:\n\n${r.text.trim()}`;
  }
  if (text) {
    tokens = estimateTokens(text);
    if (tokens > TOKEN_LIMITS.file) {
      status = "error";
      error = `${file.name} is about ${formatTokens(tokens)} tokens, over the ${formatTokens(TOKEN_LIMITS.file)} limit for one file. Split it into smaller files.`;
      text = null;
      tokens = null;
    }
  }
  return asService(async (q) => {
    const [row] = await q`
      update files set status = ${status}, error = ${error}, extracted_text = ${text}, token_count = ${tokens}
      where id = ${id} returning *`;
    if (text && status === "ready") {
      const rows = chunkText(text).map((content, idx) => ({ file_id: id, idx, content }));
      for (let i = 0; i < rows.length; i += 500) await q`insert into file_chunks ${q(rows.slice(i, i + 500))} on conflict do nothing`;
    }
    return toFile(row);
  });
}

export async function saveGeneratedFile(userId: string, input: { name: string; mime: string; bytes: Buffer }) {
  const { workspace } = await getWorkspaceFor(userId);
  return asService(async (q) => {
    const [f] = await q`
      insert into files (workspace_id, owner_id, name, mime, bytes, storage_path, source, status)
      values (${workspace.id}, ${userId}, ${input.name}, ${input.mime}, ${input.bytes.length},
              ${userId} || '/' || gen_random_uuid() || '/' || ${input.name}, 'generated', 'uploading')
      returning *`;
    const file = toFile(f);
    await putObject(file.storage_path, input.bytes, input.mime);
    const [row] = await q`update files set status = 'ready' where id = ${file.id} returning *`;
    return toFile(row);
  });
}

/** Visible through RLS, or shown in a shared-link snapshot the viewer can open. */
export async function getFileForView(viewerId: string | null, id: string) {
  if (viewerId) {
    const [f] = await asUser(viewerId, (q) => q`select * from files where id = ${id}`);
    if (f) return toFile(f);
  }
  const [f] = await asService((q) => q`
    select f.* from files f
    where f.id = ${id} and f.deleted_at is null and exists (
      select 1 from shared_links s
      where jsonb_path_exists(s.snapshot, '$.messages[*].content[*] ? (@.file_id == $id)', jsonb_build_object('id', ${id}::text))
        and (s.visibility = 'public'
             or (${viewerId}::uuid is not null and exists (
                   select 1 from memberships a join memberships b on a.workspace_id = b.workspace_id
                   where a.user_id = s.owner_id and b.user_id = ${viewerId}::uuid))))`);
  if (!f) throw notFound();
  return toFile(f);
}

export async function readFileBytes(file: FileRow) {
  const bytes = await readObject(file.storage_path);
  if (!bytes) throw notFound("The file's contents are missing.");
  return bytes;
}

export async function listFiles(userId: string, opts: { trashed?: boolean } = {}) {
  const rows = await asUser(userId, (q) => q`
    select * from files where owner_id = ${userId} and not is_temporary and status = 'ready'
      and (deleted_at is not null) = ${!!opts.trashed}
    order by created_at desc limit 1000`);
  return rows.map(toFile);
}

export async function trashFile(userId: string, id: string, trashed: boolean) {
  const [f] = await asUser(userId, (q) => q`
    update files set deleted_at = ${trashed ? q`now()` : null} where id = ${id} and owner_id = ${userId} returning *`);
  if (!f) throw notFound();
  return toFile(f);
}

/* ------------------------------------------------------------------ search */

export async function search(userId: string, raw: string): Promise<SearchResult[]> {
  const q0 = raw.trim().slice(0, 200);
  if (!q0) return [];
  const like = `%${q0.replace(/[\\%_]/g, (c) => "\\" + c)}%`;
  return asUser(userId, async (q) => {
    const chats = await q<{ id: string; title: string }[]>`
      select id, title from conversations
      where not is_temporary and (title ilike ${like} or search @@ websearch_to_tsquery('english', ${q0}))
      order by last_message_at desc limit 15`;
    const msgs = await q<{ conversation_id: string; title: string; text: string }[]>`
      select distinct on (m.conversation_id) m.conversation_id, c.title, m.text
      from messages m join conversations c on c.id = m.conversation_id
      where not c.is_temporary and (m.search @@ websearch_to_tsquery('english', ${q0}) or m.text ilike ${like})
      order by m.conversation_id, m.created_at desc limit 15`;
    const projects = await q<{ id: string; name: string }[]>`select id, name from projects where name ilike ${like} limit 10`;
    const files = await q<{ id: string; name: string }[]>`
      select id, name from files where owner_id = ${userId} and deleted_at is null and status = 'ready' and not is_temporary
        and name ilike ${like} order by created_at desc limit 10`;
    // Pages you can open (RLS), by title or words in them.
    const pages = await q<{ id: string; title: string; text: string }[]>`
      select id, title, text from pages
      where title ilike ${like} or search @@ websearch_to_tsquery('english', ${q0})
      order by updated_at desc limit 10`;
    const snippet = (t: string) => {
      const i = t.toLowerCase().indexOf(q0.toLowerCase());
      const start = Math.max(0, (i < 0 ? 0 : i) - 40);
      return (start > 0 ? "…" : "") + t.slice(start, start + 140).replace(/\s+/g, " ");
    };
    return [
      ...chats.map((c): SearchResult => ({ kind: "chat", id: c.id, title: c.title, href: `/c/${c.id}` })),
      ...msgs.map((m): SearchResult => ({ kind: "message", id: m.conversation_id, title: m.title, href: `/c/${m.conversation_id}`, snippet: snippet(m.text) })),
      ...projects.map((p): SearchResult => ({ kind: "project", id: p.id, title: p.name, href: `/project/${p.id}` })),
      ...pages.map((p): SearchResult => ({ kind: "page", id: p.id, title: p.title.trim() || "Untitled", href: `/space/${p.id}`, snippet: p.text ? snippet(p.text) : undefined })),
      ...files.map((f): SearchResult => ({ kind: "file", id: f.id, title: f.name, href: `/library?file=${f.id}` })),
    ];
  });
}

/* ------------------------------------------------------------------ personalization & profile */

const DEFAULT_PERS = (userId: string): Personalization => ({
  user_id: userId, about_you: "", response_style: "", personality: "default", memory_enabled: true, reference_chat_history: true,
});

export async function getPersonalization(userId: string): Promise<Personalization> {
  const [p] = await asUser(userId, (q) => q<Personalization[]>`
    select user_id, about_you, response_style, personality, memory_enabled, reference_chat_history
    from personalization where user_id = ${userId}`);
  return p ?? DEFAULT_PERS(userId);
}

export async function savePersonalization(userId: string, patch: Partial<Omit<Personalization, "user_id">>) {
  for (const k of ["about_you", "response_style"] as const) {
    if (patch[k] !== undefined && patch[k]!.length > 3000) throw new HttpError(400, "Keep each field under 3,000 characters.");
  }
  const cur = await getPersonalization(userId);
  const defined = Object.fromEntries(Object.entries(patch).filter(([, v]) => v !== undefined));
  const next = { ...cur, ...defined, user_id: userId };
  const [row] = await asUser(userId, (q) => q<Personalization[]>`
    insert into personalization (user_id, about_you, response_style, personality, memory_enabled, reference_chat_history)
    values (${userId}, ${next.about_you}, ${next.response_style}, ${next.personality}, ${next.memory_enabled}, ${next.reference_chat_history})
    on conflict (user_id) do update set about_you = excluded.about_you, response_style = excluded.response_style,
      personality = excluded.personality, memory_enabled = excluded.memory_enabled, reference_chat_history = excluded.reference_chat_history
    returning user_id, about_you, response_style, personality, memory_enabled, reference_chat_history`);
  return row;
}

/* ------------------------------------------------------------------ memory */

export const MEMORY_MAX = 6000;

export async function getMemory(userId: string): Promise<Memory> {
  const [m] = await asUser(userId, (q) => q<Memory[]>`
    select body, refreshed_at, updated_at from memory_summaries where user_id = ${userId} and project_id is null`);
  return m ?? { body: "", refreshed_at: null, updated_at: null };
}

/** The person's own edit. Keeps refreshed_at, so the next refresh starts from their corrected text. */
export async function saveMemory(userId: string, body: string, opts: { refreshed?: boolean } = {}) {
  const text = body.trim();
  if (text.length > MEMORY_MAX) throw new HttpError(400, `Keep memory under ${MEMORY_MAX.toLocaleString()} characters.`);
  const [m] = await asUser(userId, (q) => q<Memory[]>`
    insert into memory_summaries (user_id, project_id, body, refreshed_at)
    values (${userId}, null, ${text}, ${opts.refreshed ? new Date() : null})
    on conflict (user_id, project_id) do update set body = excluded.body, updated_at = now(),
      refreshed_at = case when ${!!opts.refreshed} then excluded.refreshed_at else memory_summaries.refreshed_at end
    returning body, refreshed_at, updated_at`);
  return m;
}

/** "Delete memory and turn it off": the summary is gone, and nothing new is remembered until they turn it back on. */
export async function deleteMemory(userId: string) {
  await asUser(userId, (q) => q`delete from memory_summaries where user_id = ${userId}`);
  await savePersonalization(userId, { memory_enabled: false });
}

/** What the person said in their recent saved chats (their own words only, newest first). */
export async function memorySourceMessages(userId: string, limit = 60) {
  return asUser(userId, (q) => q<{ text: string; created_at: string }[]>`
    select left(m.text, 800) as text, m.created_at from messages m join conversations c on c.id = m.conversation_id
    where m.role = 'user' and m.user_id = ${userId} and c.user_id = ${userId} and not c.is_temporary
      and m.created_at > now() - interval '90 days' and length(trim(m.text)) > 0
    order by m.created_at desc limit ${limit}`);
}

export type PastExchange = { conversation_id: string; title: string; date: string; question: string; answer: string };

/**
 * Earlier exchanges from the person's other saved chats that share real words with the question:
 * at least two of them, or the only one when the question has a single searchable word.
 */
export async function relatedExchanges(userId: string, excludeConversationId: string, question: string, limit = 3): Promise<PastExchange[]> {
  const terms = searchTerms(question, 30);
  if (!terms) return [];
  const rows = await asUser(userId, (q) => q<{ conversation_id: string; title: string; created_at: Date; question: string; answer: string | null }[]>`
    select m.conversation_id, c.title, m.created_at, left(m.text, 600) as question, left(a.text, 900) as answer
    from messages m
    join conversations c on c.id = m.conversation_id
    cross join to_tsquery('english', ${terms}) query
    left join lateral (
      select text from messages r where r.parent_id = m.id and r.role = 'assistant' and r.status = 'complete'
      order by r.created_at desc limit 1
    ) a on true
    where m.role = 'user' and m.user_id = ${userId} and c.user_id = ${userId} and not c.is_temporary
      and c.id <> ${excludeConversationId} and m.search @@ query and m.created_at > now() - interval '180 days'
    order by ts_rank_cd(m.search, query) desc, m.created_at desc limit 20`);
  const qWords = new Set(question.toLowerCase().match(/[\p{L}\p{N}]{4,}/gu) ?? []);
  const need = Math.min(2, qWords.size);
  const out: PastExchange[] = [];
  for (const r of rows) {
    const shared = new Set((r.question.toLowerCase().match(/[\p{L}\p{N}]{4,}/gu) ?? []).filter((w) => qWords.has(w)));
    if (shared.size < need || out.some((o) => o.conversation_id === r.conversation_id)) continue;
    out.push({ conversation_id: r.conversation_id, title: r.title, date: new Date(r.created_at).toISOString().slice(0, 10), question: r.question, answer: r.answer ?? "" });
    if (out.length >= limit) break;
  }
  return out;
}

export async function updateProfile(userId: string, patch: { theme?: "system" | "light" | "dark"; locale?: string; name?: string }) {
  if (patch.theme !== undefined && !["system", "light", "dark"].includes(patch.theme)) throw new HttpError(400, "Unknown theme.");
  if (patch.name !== undefined && !patch.name.trim()) throw new HttpError(400, "Your name can't be empty.");
  const [p] = await asUser(userId, (q) => q<Profile[]>`
    update profiles set
      theme = coalesce(${patch.theme ?? null}, theme),
      locale = coalesce(${patch.locale ?? null}, locale),
      name = coalesce(${patch.name?.trim() ?? null}, name)
    where id = ${userId}
    returning id, email, name, avatar_url, theme, locale`);
  if (!p) throw notFound();
  return p;
}

/* ------------------------------------------------------------------ sharing */

function shareableContent(content: ContentBlock[]): ContentBlock[] {
  return content.flatMap((b): ContentBlock[] => {
    if (b.type !== "sources") return [b];
    const items = b.items.filter((i) => i.kind === "web");
    return items.length ? [{ type: "sources", items }] : [];
  });
}

export async function shareConversation(userId: string, id: string) {
  return asUser(userId, async (q) => {
    const c = await ownConversation(q, userId, id);
    if (c.is_temporary) throw new HttpError(400, "Temporary chats can't be shared.");
    const all = await q<Message[]>`select id, parent_id, role, content, text, status from messages where conversation_id = ${id}`;
    const path = threadPath(all, c.current_leaf_id);
    if (path.some((m) => m.status === "streaming")) throw new HttpError(409, "Wait for the answer to finish, then share.");
    const snapshot: SharedLink["snapshot"] = {
      title: c.title,
      // Memory and earlier-chat sources are private to the owner; web sources are fine to share.
      messages: path.map(({ id, role, content, text }) => ({ id, role, content: shareableContent(content), text })),
      shared_at: new Date().toISOString(),
    };
    const leaf = path.at(-1)?.id ?? null;
    const [link] = await q<SharedLink[]>`
      insert into shared_links (owner_id, conversation_id, snapshot, snapshot_message_id)
      values (${userId}, ${id}, ${q.json(snapshot as never)}, ${leaf})
      on conflict (conversation_id) where conversation_id is not null
      do update set snapshot = excluded.snapshot, snapshot_message_id = excluded.snapshot_message_id, updated_at = now()
      returning slug, updated_at, visibility`;
    return link;
  });
}

export async function deleteShare(userId: string, slug: string) {
  const rows = await asUser(userId, (q) => q`delete from shared_links where slug = ${slug} and owner_id = ${userId} returning id`);
  if (!rows.length) throw notFound();
}

export async function listShares(userId: string) {
  return asUser(userId, (q) => q<{ slug: string; title: string; updated_at: string; conversation_id: string }[]>`
    select slug, snapshot->>'title' as title, updated_at, conversation_id from shared_links
    where owner_id = ${userId} order by updated_at desc`);
}

/** Workspace links need a signed-in member; public links need the workspace to allow them. */
export async function getShare(viewerId: string | null, slug: string) {
  return asService(async (q) => {
    const [link] = await q`
      select s.*, p.name as owner_name, w.settings as ws_settings, m.workspace_id
      from shared_links s join profiles p on p.id = s.owner_id
      join memberships m on m.user_id = s.owner_id join workspaces w on w.id = m.workspace_id
      where s.slug = ${slug}`;
    if (!link) throw notFound("This link was deleted or never existed.");
    if (link.visibility === "public" && !(link.ws_settings as { public_links_allowed?: boolean })?.public_links_allowed) {
      throw notFound("This link was deleted or never existed.");
    }
    if (link.visibility === "workspace") {
      if (!viewerId) throw new HttpError(401, "Sign in to view this chat.");
      const [ok] = await q`select 1 from memberships where user_id = ${viewerId} and workspace_id = ${link.workspace_id}`;
      if (!ok) throw notFound("This link was deleted or never existed.");
    }
    return { snapshot: link.snapshot as SharedLink["snapshot"], owner_name: link.owner_name as string, is_owner: viewerId === link.owner_id };
  });
}

/* ------------------------------------------------------------------ usage, rate limits, images */

export async function recordUsage(
  userId: string,
  metric: UsageEvent["metric"],
  key: string,
  extra: { model?: string; input_tokens?: number; output_tokens?: number; web_searches?: number; quantity?: number } = {},
) {
  await asService((q) => q`
    insert into usage_events (workspace_id, user_id, metric, idempotency_key, model, input_tokens, output_tokens, web_searches, quantity)
    select m.workspace_id, ${userId}, ${metric}, ${key}, ${extra.model ?? null}, ${extra.input_tokens ?? null}, ${extra.output_tokens ?? null}, ${extra.web_searches || null}, ${extra.quantity ?? 1}
    from memberships m where m.user_id = ${userId} limit 1
    on conflict (idempotency_key) do nothing`);
}

/** Count since midnight in the workspace's time zone. */
export async function usageToday(userId: string, metric: UsageEvent["metric"]) {
  const [r] = await asService((q) => q`
    select count(*)::int as n from usage_events u
    join memberships m on m.user_id = u.user_id join workspaces w on w.id = m.workspace_id
    where u.user_id = ${userId} and u.metric = ${metric}
      and u.created_at >= (date_trunc('day', now() at time zone coalesce(w.settings->>'timezone', 'UTC')) at time zone coalesce(w.settings->>'timezone', 'UTC'))`);
  return Number(r?.n ?? 0);
}

/** Simple sliding-window limit on sends, on top of the daily caps. */
export async function checkSendRate(userId: string, perMinute = 20) {
  const [r] = await asService((q) => q`
    select count(*)::int as n from messages where user_id = ${userId} and role = 'user' and created_at > now() - interval '1 minute'`);
  if (Number(r.n) >= perMinute) throw new HttpError(429, "You're sending messages very fast. Wait a moment and try again.");
}

export async function recordImage(
  userId: string,
  row: { conversation_id: string; message_id: string; prompt: string; output_file_id: string | null; provider: string; status: ImageGeneration["status"] },
) {
  await asService((q) => q`
    insert into image_generations (workspace_id, user_id, conversation_id, message_id, prompt, output_file_id, provider, status)
    select m.workspace_id, ${userId}, ${row.conversation_id}, ${row.message_id}, ${row.prompt.slice(0, 8000)}, ${row.output_file_id}, ${row.provider}, ${row.status}
    from memberships m where m.user_id = ${userId} limit 1`);
}

export async function listImages(userId: string) {
  return asUser(userId, (q) => q<ImageGeneration[]>`
    select * from image_generations where user_id = ${userId} and output_file_id is not null and status = 'succeeded'
    order by created_at desc limit 500`);
}

/* ------------------------------------------------------------------ account & jobs */

export async function storagePathsOwnedBy(userId: string) {
  const rows = await asService((q) => q<{ storage_path: string }[]>`select storage_path from files where owner_id = ${userId}`);
  return rows.map((r) => r.storage_path);
}

/** Answers stuck in "streaming" (crashed instance) become errors the user can retry. */
export async function sweepStuckStreams(olderThanMinutes = 10) {
  const rows = await asService((q) => q`
    update messages set status = 'error', error = 'The answer was interrupted. Try again.'
    where status = 'streaming' and updated_at < now() - make_interval(mins => ${olderThanMinutes}) returning id`);
  return rows.length;
}

/** Exports a crashed instance left behind: queued ones are handed back to run again, long-running ones fail. */
export async function sweepExports() {
  return asService(async (q) => {
    const failed = await q`
      update data_exports set status = 'failed', updated_at = now()
      where status = 'running' and updated_at < now() - interval '15 minutes' returning id`;
    const queued = await q<{ id: string }[]>`
      select id from data_exports where status = 'queued' and created_at < now() - interval '2 minutes'`;
    return { failed: failed.length, queued: queued.map((r) => r.id) };
  });
}

/** "Delete all chats": every chat the person owns, in projects and archived ones too. Library files and memory stay. */
export async function deleteAllConversations(userId: string) {
  const rows = await asUser(userId, (q) => q`delete from conversations where user_id = ${userId} returning id`);
  return rows.length;
}

/** Hard-deletes files trashed 30+ days ago and temporary chats older than 30 days. Returns storage paths to remove. */
export async function purgeExpired() {
  return asService(async (q) => {
    const files = await q<{ storage_path: string }[]>`
      delete from files where (deleted_at < now() - interval '30 days')
        or (is_temporary and created_at < now() - interval '30 days')
        or (status = 'uploading' and created_at < now() - interval '1 day')
      returning storage_path`;
    const chats = await q`delete from conversations where is_temporary and created_at < now() - interval '30 days' returning id`;
    const exports = await q<{ storage_path: string | null }[]>`
      update data_exports set status = 'expired', updated_at = now()
      where status = 'ready' and expires_at < now() returning storage_path`;
    return {
      paths: [...files.map((f) => f.storage_path), ...exports.flatMap((e) => (e.storage_path ? [e.storage_path] : []))],
      chats: chats.length,
      exports: exports.length,
    };
  });
}
