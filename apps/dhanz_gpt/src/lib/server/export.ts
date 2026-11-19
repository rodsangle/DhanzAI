import "server-only";
import { BRAND } from "@/lib/brand";
import { strToU8, zipSync, type Zippable } from "fflate";
import { getMemory, getPersonalization, getProfile, threadPath } from "@/lib/data";
import { HttpError } from "@/lib/data/errors";
import type { Message } from "@/lib/data/types";
import { asService, asUser } from "./db";
import { appUrl, layout, sendEmail } from "./email";
import { putObject, readObject } from "./storage";

/**
 * "Export your data" (S27). A background job zips everything the person owns: chats (readable HTML,
 * plus JSON with every branch), projects, personalization, memory, assistants, scheduled tasks and
 * their files. The download needs their sign-in and expires after 24 hours; an email says when it's ready.
 */

const FILES_MAX_BYTES = Number(process.env.EXPORT_FILES_MAX_BYTES ?? 200 * 1024 * 1024);
const PER_DAY = 3;

export type ExportRow = { id: string; status: "queued" | "running" | "ready" | "failed" | "expired"; created_at: string; expires_at: string | null };

export async function latestExport(userId: string): Promise<ExportRow | null> {
  const [row] = await asUser(userId, (q) => q<ExportRow[]>`
    select id, case when status = 'ready' and expires_at < now() then 'expired' else status end as status, created_at, expires_at
    from data_exports where user_id = ${userId} order by created_at desc limit 1`);
  return row ?? null;
}

export async function requestExport(userId: string): Promise<ExportRow> {
  return asService(async (q) => {
    await q`select pg_advisory_xact_lock(hashtext(${"export:" + userId}))`;
    const [busy] = await q<ExportRow[]>`
      select id, status, created_at, expires_at from data_exports
      where user_id = ${userId} and status in ('queued','running') order by created_at desc limit 1`;
    if (busy) return busy;
    const [{ n }] = await q<{ n: number }[]>`
      select count(*)::int as n from data_exports where user_id = ${userId} and created_at > now() - interval '24 hours'`;
    if (n >= PER_DAY) throw new HttpError(429, `You can export ${PER_DAY} times a day. Try again tomorrow.`);
    const [row] = await q<ExportRow[]>`
      insert into data_exports (user_id) values (${userId}) returning id, status, created_at, expires_at`;
    await q`insert into security_events (user_id, kind) values (${userId}, 'export_requested')`;
    return row;
  });
}

/** The zip, for its owner only, while it hasn't expired. */
export async function exportForDownload(userId: string, id: string) {
  const [row] = await asUser(userId, (q) => q<{ storage_path: string | null; status: string; expires_at: string | null }[]>`
    select storage_path, status, expires_at from data_exports where id = ${id}`);
  if (!row || row.status !== "ready" || !row.storage_path) throw new HttpError(404, "That export isn't available.");
  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) throw new HttpError(410, "That export has expired. Request a new one in Settings → Data controls.");
  return { storagePath: row.storage_path };
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

type ConvRow = { id: string; title: string; project_id: string | null; project_name: string | null; model: string; current_leaf_id: string | null; archived_at: string | null; created_at: string };

/** Runs one queued export. Safe to call twice: only the call that claims it does the work. */
export async function runExport(exportId: string) {
  const [claimed] = await asService((q) => q<{ user_id: string }[]>`
    update data_exports set status = 'running', updated_at = now() where id = ${exportId} and status = 'queued' returning user_id`);
  if (!claimed) return;
  const userId = claimed.user_id;
  try {
    const profile = await getProfile(userId);
    const data = await asUser(userId, async (q) => {
      const convs = await q<ConvRow[]>`
        select c.id, c.title, c.project_id, p.name as project_name, c.model, c.current_leaf_id, c.archived_at, c.created_at
        from conversations c left join projects p on p.id = c.project_id
        where c.user_id = ${userId} and not c.is_temporary order by c.created_at`;
      const messages = convs.length
        ? await q<(Message & { conversation_id: string })[]>`
            select id, conversation_id, parent_id, role, text, content, model, status, created_at from messages
            where conversation_id = any(${convs.map((c) => c.id)}::uuid[]) order by created_at`
        : [];
      const projects = await q`select id, name, instructions, created_at from projects where owner_id = ${userId} order by created_at`;
      const projectFiles = await q`
        select pf.project_id, f.name from project_files pf join files f on f.id = pf.file_id join projects p on p.id = pf.project_id
        where p.owner_id = ${userId}`;
      const assistants = await q`select id, name, description, instructions, starters, visibility, created_at from assistants where owner_id = ${userId}`;
      const tasks = await q`select id, title, prompt, kind, run_at, rrule, timezone, status, created_at from scheduled_tasks where user_id = ${userId}`;
      const files = await q<{ id: string; name: string; mime: string; bytes: string; storage_path: string; source: string; created_at: string }[]>`
        select id, name, mime, bytes, storage_path, source, created_at from files
        where owner_id = ${userId} and deleted_at is null and status = 'ready' and not is_temporary order by created_at`;
      // Pages you wrote (in any space you can still open).
      const pages = await q<{ id: string; title: string; text: string; space: string | null; parent_page_id: string | null; created_at: string; updated_at: string }[]>`
        select pg.id, pg.title, pg.text, s.name as space, pg.parent_page_id, pg.created_at, pg.updated_at
        from pages pg left join spaces s on s.id = pg.space_id where pg.created_by = ${userId} order by pg.created_at`;
      return { convs, messages, projects, projectFiles, assistants, tasks, files, pages };
    });
    const [pers, memory] = await Promise.all([getPersonalization(userId), getMemory(userId)]);

    // Files, newest-first priority up to the size cap; the rest are listed, not packed.
    const zip: Zippable = {};
    const used = new Set<string>();
    let packed = 0;
    const fileList = [];
    for (const f of data.files) {
      const size = Number(f.bytes);
      let included = false;
      let zipName: string | null = null;
      if (packed + size <= FILES_MAX_BYTES) {
        const bytes = await readObject(f.storage_path).catch(() => null);
        if (bytes) {
          zipName = f.name;
          for (let i = 2; used.has(zipName.toLowerCase()); i++) zipName = f.name.replace(/(\.[^.]*)?$/, ` (${i})$1`);
          used.add(zipName.toLowerCase());
          zip[`files/${zipName}`] = [new Uint8Array(bytes), { level: 0 }];
          packed += size;
          included = true;
        }
      }
      fileList.push({ name: f.name, mime: f.mime, bytes: size, source: f.source, created_at: f.created_at, in_export: included ? `files/${zipName}` : null });
    }

    const chats = data.convs.map((c) => {
      const all = data.messages.filter((m) => m.conversation_id === c.id);
      return {
        id: c.id, title: c.title, project: c.project_name, model: c.model, created_at: c.created_at, archived: !!c.archived_at,
        visible_thread: threadPath(all, c.current_leaf_id).map((m) => m.id),
        messages: all.map((m) => ({ id: m.id, parent_id: m.parent_id, role: m.role, text: m.text, status: m.status, model: m.model, created_at: m.created_at })),
      };
    });

    const html =
      `<!doctype html><meta charset="utf-8"><title>Your chats</title>` +
      `<style>body{font:15px/1.55 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#1a1714;background:#fbf9f5}h2{margin-top:2.5rem;border-top:1px solid #e3dccf;padding-top:1rem}.m{white-space:pre-wrap;margin:.6rem 0}.u{background:#ece6dc;padding:.5rem .8rem;border-radius:10px}small{color:#5e554a}</style>` +
      `<h1>Your ${BRAND.name} chats</h1><p><small>${chats.length} chats, exported ${new Date().toISOString().slice(0, 10)}. Each chat shows the version you were last looking at; chats.json has every version.</small></p>` +
      chats
        .map((c) => {
          const thread = c.visible_thread.map((id) => c.messages.find((m) => m.id === id)!).filter((m) => m.role === "user" || m.role === "assistant");
          return `<h2>${esc(c.title)}</h2><small>${esc(c.created_at.toString().slice(0, 10))}${c.project ? ` · ${esc(c.project)}` : ""}${c.archived ? " · archived" : ""}</small>` +
            thread.map((m) => `<div class="m ${m.role === "user" ? "u" : ""}"><b>${m.role === "user" ? "You" : "Assistant"}:</b> ${esc(m.text)}</div>`).join("");
        })
        .join("");

    const json = (v: unknown) => strToU8(JSON.stringify(v, null, 2));
    zip["README.txt"] = strToU8(
      [
        `${BRAND.name} export for ${profile?.email ?? "you"}, ${new Date().toISOString()}`,
        "",
        "chats.html       your chats, easy to read in a browser",
        "chats.json       every chat with every version of every message (parent_id links them)",
        "projects.json    projects you own, their instructions and file names",
        "assistants.json  assistants you made",
        "tasks.json       your scheduled tasks",
        "pages.json       pages you wrote in Space; pages/ has each one as a text file",
        "settings.json    your personalization settings",
        "memory.md        what the assistant remembered about you",
        "files.json       your Library; files/ holds the ones that fit in this export",
        "",
        packed < data.files.reduce((n, f) => n + Number(f.bytes), 0)
          ? `Files over the ${Math.round(FILES_MAX_BYTES / 1024 / 1024)} MB export limit are listed in files.json with in_export: null. Download them from the Library.`
          : "All your files are included.",
      ].join("\n"),
    );
    zip["chats.html"] = strToU8(html);
    zip["chats.json"] = json(chats);
    zip["projects.json"] = json(data.projects.map((p) => ({ ...p, files: data.projectFiles.filter((f) => f.project_id === p.id).map((f) => f.name) })));
    zip["assistants.json"] = json(data.assistants);
    zip["tasks.json"] = json(data.tasks);
    zip["pages.json"] = json(data.pages);
    for (const pg of data.pages) {
      const name = (pg.title.trim() || "Untitled").replace(/[^\w\- ]+/g, "").trim().slice(0, 60) || "Untitled";
      zip[`pages/${name} (${pg.id.slice(0, 8)}).md`] = strToU8(`# ${pg.title.trim() || "Untitled"}\n\n${pg.text}\n`);
    }
    zip["settings.json"] = json({ about_you: pers.about_you, response_style: pers.response_style, memory_enabled: pers.memory_enabled, reference_chat_history: pers.reference_chat_history });
    zip["memory.md"] = strToU8(memory.body || "(nothing remembered)\n");
    zip["files.json"] = json(fileList);

    const out = Buffer.from(zipSync(zip, { level: 6 }));
    const storagePath = `${userId}/exports/${exportId}.zip`;
    await putObject(storagePath, out, "application/zip");
    await asService((q) => q`
      update data_exports set status = 'ready', storage_path = ${storagePath}, expires_at = now() + interval '24 hours', updated_at = now()
      where id = ${exportId}`);
    if (profile?.email) {
      await sendEmail({
        to: profile.email,
        subject: `Your ${BRAND.name} export is ready`,
        idempotencyKey: `export-ready/${exportId}`,
        ...layout({
          heading: "Your export is ready",
          lines: [`It has ${chats.length} chats, ${data.projects.length} projects and ${fileList.length} files.`, "The link works for 24 hours, and you'll need to be signed in."],
          button: { label: "Download your data", href: appUrl(`/api/account/export/${exportId}/download`) },
        }),
      });
    }
  } catch (e) {
    console.error("[export]", (e as Error).message);
    await asService((q) => q`update data_exports set status = 'failed', updated_at = now() where id = ${exportId}`);
  }
}
