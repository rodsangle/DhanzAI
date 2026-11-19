import "server-only";
import { asService, asUser, type Tx } from "@/lib/server/db";
import { HttpError } from "./errors";
import { MODELS, type Assistant, type AssistantCapability, type AssistantDetail, type AssistantListItem, type FileRow } from "./types";

/**
 * Custom assistants (S21, S22): saved presets with instructions, conversation starters, knowledge
 * files, a recommended model and capabilities. Private to their author, or shared with the team.
 * Every save keeps a version snapshot that the author can restore. RLS: authors and admins edit;
 * everyone in the workspace reads team assistants.
 */

export const ASSISTANT_LIMITS = { name: 80, description: 300, instructions: 20000, starters: 4, starter: 200, files: 20 } as const;
const CAPS: AssistantCapability[] = ["web_search", "image_generation"];

export type AssistantInput = {
  name: string;
  description?: string;
  instructions?: string;
  starters?: string[];
  recommended_model?: string | null;
  capabilities?: AssistantCapability[];
  visibility?: "private" | "workspace";
  file_ids?: string[];
};

function clean(input: AssistantInput) {
  const name = input.name.trim();
  if (!name) throw new HttpError(400, "Give the assistant a name.");
  if (name.length > ASSISTANT_LIMITS.name) throw new HttpError(400, `Keep the name under ${ASSISTANT_LIMITS.name} characters.`);
  const description = (input.description ?? "").trim();
  if (description.length > ASSISTANT_LIMITS.description) throw new HttpError(400, `Keep the description under ${ASSISTANT_LIMITS.description} characters.`);
  const instructions = input.instructions ?? "";
  if (instructions.length > ASSISTANT_LIMITS.instructions) throw new HttpError(400, "The instructions are too long.");
  const starters = (input.starters ?? []).map((s) => s.trim()).filter(Boolean);
  if (starters.length > ASSISTANT_LIMITS.starters) throw new HttpError(400, `Add up to ${ASSISTANT_LIMITS.starters} conversation starters.`);
  if (starters.some((s) => s.length > ASSISTANT_LIMITS.starter)) throw new HttpError(400, "Keep each conversation starter short.");
  const model = input.recommended_model && MODELS.some((m) => m.id === input.recommended_model) ? input.recommended_model : null;
  const capabilities = [...new Set((input.capabilities ?? CAPS).filter((c) => CAPS.includes(c)))];
  const visibility = input.visibility === "workspace" ? "workspace" : "private";
  return { name, description, instructions, starters, model, capabilities, visibility };
}

/** Knowledge files must be ones the editor can already open. */
async function checkFiles(q: Tx, fileIds: string[]) {
  if (fileIds.length > ASSISTANT_LIMITS.files) throw new HttpError(400, `Add up to ${ASSISTANT_LIMITS.files} files.`);
  if (!fileIds.length) return;
  const rows = await q<{ id: string; status: string }[]>`select id, status from files where id = any(${fileIds}::uuid[]) and deleted_at is null`;
  if (rows.length !== new Set(fileIds).size) throw new HttpError(400, "One of the files isn't available.");
  if (rows.some((r) => r.status !== "ready")) throw new HttpError(409, "Wait for the files to finish uploading.");
}

async function snapshot(q: Tx, id: string, userId: string) {
  const [a] = await q<(Assistant & { file_ids: string[] })[]>`
    select a.*, coalesce((select array_agg(file_id) from assistant_files where assistant_id = a.id), '{}') as file_ids
    from assistants a where a.id = ${id}`;
  const { name, description, instructions, starters, recommended_model, capabilities, visibility, file_ids } = a;
  await asService((s) => s`
    insert into assistant_versions (assistant_id, version, snapshot, created_by)
    values (${id}, ${a.current_version}, ${s.json({ name, description, instructions, starters, recommended_model, capabilities, visibility, file_ids } as never)}, ${userId})
    on conflict (assistant_id, version) do nothing`);
}

async function setFiles(id: string, fileIds: string[]) {
  await asService(async (s) => {
    await s`delete from assistant_files where assistant_id = ${id} and not (file_id = any(${fileIds}::uuid[]))`;
    for (const f of fileIds) await s`insert into assistant_files (assistant_id, file_id) values (${id}, ${f}) on conflict do nothing`;
  });
}

export async function listAssistants(userId: string): Promise<{ mine: AssistantListItem[]; team: AssistantListItem[] }> {
  const rows = await asUser(userId, (q) => q<(AssistantListItem & { is_admin: boolean })[]>`
    select a.id, a.name, a.description, a.visibility, a.owner_id, a.updated_at, p.name as owner_name, is_admin(a.workspace_id) as is_admin
    from assistants a left join profiles p on p.id = a.owner_id
    order by lower(a.name)`);
  const items = rows.map(({ is_admin, ...r }) => ({ ...r, can_edit: r.owner_id === userId || is_admin }));
  return { mine: items.filter((a) => a.owner_id === userId), team: items.filter((a) => a.owner_id !== userId && a.visibility === "workspace") };
}

export async function getAssistant(userId: string, id: string): Promise<AssistantDetail> {
  return asUser(userId, async (q) => {
    const [a] = await q<(Assistant & { owner_name: string | null; is_admin: boolean })[]>`
      select a.*, p.name as owner_name, is_admin(a.workspace_id) as is_admin
      from assistants a left join profiles p on p.id = a.owner_id where a.id = ${id}`;
    if (!a) throw new HttpError(404, "This assistant doesn't exist or isn't shared with you.");
    const files = await q<Pick<FileRow, "id" | "name" | "mime" | "bytes">[]>`
      select f.id, f.name, f.mime, f.bytes from assistant_files af join files f on f.id = af.file_id
      where af.assistant_id = ${id} and f.deleted_at is null order by f.name`;
    const can_edit = a.owner_id === userId || a.is_admin;
    const versions = can_edit
      ? await q<{ version: number; created_at: string; created_by_name: string | null }[]>`
          select v.version, v.created_at, p.name as created_by_name from assistant_versions v
          left join profiles p on p.id = v.created_by where v.assistant_id = ${id} order by v.version desc limit 20`
      : [];
    const { is_admin: _admin, ...rest } = a;
    void _admin;
    return { ...rest, files: files.map((f) => ({ ...f, bytes: Number(f.bytes) })), can_edit, versions };
  });
}

export async function createAssistant(userId: string, input: AssistantInput) {
  const c = clean(input);
  const fileIds = [...new Set(input.file_ids ?? [])];
  const id = await asUser(userId, async (q) => {
    await checkFiles(q, fileIds);
    const [m] = await q<{ workspace_id: string }[]>`select workspace_id from memberships where user_id = ${userId} limit 1`;
    const [a] = await q<{ id: string }[]>`
      insert into assistants (workspace_id, owner_id, name, description, instructions, starters, recommended_model, capabilities, visibility)
      values (${m.workspace_id}, ${userId}, ${c.name}, ${c.description}, ${c.instructions}, ${c.starters}, ${c.model}, ${c.capabilities}, ${c.visibility})
      returning id`;
    return a.id;
  });
  await setFiles(id, fileIds);
  await asUser(userId, (q) => snapshot(q, id, userId));
  return getAssistant(userId, id);
}

export async function updateAssistant(userId: string, id: string, input: AssistantInput) {
  const c = clean(input);
  const fileIds = [...new Set(input.file_ids ?? [])];
  await asUser(userId, async (q) => {
    // Existing knowledge files stay allowed even if the editor couldn't add them today (e.g. an admin editing).
    const [cur] = await q<{ ok: boolean }[]>`select true as ok from assistants where id = ${id}`;
    if (!cur) throw new HttpError(404, "This assistant doesn't exist or isn't shared with you.");
    const existing = (await q<{ file_id: string }[]>`select file_id from assistant_files where assistant_id = ${id}`).map((r) => r.file_id);
    await checkFiles(q, fileIds.filter((f) => !existing.includes(f)));
    const rows = await q`
      update assistants set name = ${c.name}, description = ${c.description}, instructions = ${c.instructions}, starters = ${c.starters},
        recommended_model = ${c.model}, capabilities = ${c.capabilities}, visibility = ${c.visibility},
        current_version = current_version + 1, updated_at = now()
      where id = ${id} returning id`;
    if (!rows.length) throw new HttpError(403, "Only its author or a workspace admin can change this assistant.");
  });
  await setFiles(id, fileIds);
  await asUser(userId, (q) => snapshot(q, id, userId));
  return getAssistant(userId, id);
}

export async function restoreAssistantVersion(userId: string, id: string, version: number) {
  const [v] = await asUser(userId, (q) => q<{ snapshot: AssistantInput & { file_ids: string[] } }[]>`
    select snapshot from assistant_versions where assistant_id = ${id} and version = ${version}`);
  if (!v) throw new HttpError(404, "That version doesn't exist.");
  const live = await asService((q) => q<{ id: string }[]>`
    select id from files where id = any(${v.snapshot.file_ids ?? []}::uuid[]) and deleted_at is null`);
  return updateAssistant(userId, id, { ...v.snapshot, file_ids: live.map((f) => f.id) });
}

export async function deleteAssistant(userId: string, id: string) {
  const rows = await asUser(userId, (q) => q`delete from assistants where id = ${id} returning id`);
  if (!rows.length) throw new HttpError(404, "This assistant doesn't exist, or only its author or an admin can delete it.");
}

/** System read for the generator: the assistant's setup and its readable knowledge files. */
export async function assistantContext(assistantId: string) {
  return asService(async (q) => {
    const [a] = await q<Assistant[]>`select * from assistants where id = ${assistantId}`;
    if (!a) return null;
    const files = (await q<FileRow[]>`
      select f.* from assistant_files af join files f on f.id = af.file_id
      where af.assistant_id = ${assistantId} and f.deleted_at is null and f.status = 'ready' order by f.name`).map((f) => ({ ...f, bytes: Number(f.bytes) }));
    return { name: a.name, instructions: a.instructions, capabilities: a.capabilities, files };
  });
}
