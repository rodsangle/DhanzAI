import "server-only";
import { asService, asUser, type Tx } from "@/lib/server/db";
import { HttpError } from "./errors";

/**
 * Space (S12): spaces hold a tree of pages. Access granted on a space or a page flows down to every subpage
 * (page_access_level in 0009); the space owner always edits; a space can be opened to the whole workspace.
 * Every read and write runs as the user, so RLS decides what they see and change.
 */

import type { AccessEntry, CommentRow, Level, PageDetail, PageDoc, PageNode, SpaceSummary } from "./space-types";
export type { AccessEntry, CommentRow, Level, PageDetail, PageDoc, PageNode, SpaceSummary };

export const SPACE_LIMITS = { name: 120, title: 300, text: 500_000, docBytes: 2_000_000, comment: 10_000, quote: 1000, depth: 8 } as const;
const notFound = (what = "This page doesn't exist or isn't shared with you.") => new HttpError(404, what);
const LEVELS: Level[] = ["view", "comment", "edit"];

async function workspaceOf(q: Tx, userId: string) {
  const [m] = await q<{ workspace_id: string }[]>`select workspace_id from memberships where user_id = ${userId} limit 1`;
  if (!m) throw new HttpError(403, "You're not in a workspace.");
  return m.workspace_id;
}

/** Everyone has a personal space; make it if sign-in didn't (older accounts). */
async function ensurePersonalSpace(userId: string) {
  await asService(async (q) => {
    const ws = await workspaceOf(q, userId);
    await q`insert into spaces (workspace_id, owner_id, name, is_personal)
            values (${ws}, ${userId}, 'My pages', true) on conflict (owner_id) where is_personal do nothing`;
  });
}

/* ------------------------------------------------------------------ spaces and the tree */

export async function listSpaces(userId: string): Promise<{ spaces: SpaceSummary[]; pages: PageNode[] }> {
  await ensurePersonalSpace(userId);
  return asUser(userId, async (q) => {
    const spaces = await q<SpaceSummary[]>`
      select s.id, s.name, s.is_personal, s.owner_id = ${userId} as is_owner, p.name as owner_name,
             s.everyone_level, space_access_level(s.id) as level
      from spaces s join profiles p on p.id = s.owner_id
      order by s.is_personal desc, (s.owner_id = ${userId}) desc, s.name`;
    const pages = await q<PageNode[]>`
      select pg.id, pg.space_id, pg.parent_page_id, pg.title, pg.position, page_access_level(pg.id) as level
      from pages pg order by pg.position, pg.created_at limit 2000`;
    return { spaces, pages };
  });
}

function cleanName(name: string) {
  const n = name.trim();
  if (!n) throw new HttpError(400, "Give the space a name.");
  if (n.length > SPACE_LIMITS.name) throw new HttpError(400, `Keep the name under ${SPACE_LIMITS.name} characters.`);
  return n;
}

export async function createSpace(userId: string, input: { name: string; everyone_level?: Level | null }) {
  return asUser(userId, async (q) => {
    const ws = await workspaceOf(q, userId);
    const [s] = await q<{ id: string }[]>`
      insert into spaces (workspace_id, owner_id, name, everyone_level)
      values (${ws}, ${userId}, ${cleanName(input.name)}, ${input.everyone_level ?? null}) returning id`;
    return s;
  });
}

export async function updateSpace(userId: string, id: string, patch: { name?: string; everyone_level?: Level | null }) {
  return asUser(userId, async (q) => {
    const [s] = await q<{ owner_id: string; is_personal: boolean; name: string; everyone_level: Level | null }[]>`
      select owner_id, is_personal, name, everyone_level from spaces where id = ${id}`;
    if (!s) throw notFound("This space doesn't exist or isn't shared with you.");
    if (s.owner_id !== userId) throw new HttpError(403, "Only the space's owner can change it.");
    if (s.is_personal && patch.everyone_level) throw new HttpError(400, "Your personal space stays private. Make a team space to share with everyone.");
    const [row] = await q`
      update spaces set name = ${patch.name !== undefined ? cleanName(patch.name) : s.name},
        everyone_level = ${patch.everyone_level !== undefined ? patch.everyone_level : s.everyone_level}
      where id = ${id} returning id, name, everyone_level`;
    return row;
  });
}

export async function deleteSpace(userId: string, id: string) {
  return asUser(userId, async (q) => {
    const [s] = await q<{ owner_id: string; is_personal: boolean }[]>`select owner_id, is_personal from spaces where id = ${id}`;
    if (!s) throw notFound("This space doesn't exist or isn't shared with you.");
    if (s.owner_id !== userId) throw new HttpError(403, "Only the space's owner can delete it.");
    if (s.is_personal) throw new HttpError(400, "Your personal space can't be deleted.");
    await q`delete from spaces where id = ${id}`;
  });
}

/* ------------------------------------------------------------------ pages */

function checkDoc(doc: unknown): PageDoc {
  if (!doc || typeof doc !== "object" || (doc as { type?: unknown }).type !== "doc") throw new HttpError(400, "That page content isn't valid.");
  if (JSON.stringify(doc).length > SPACE_LIMITS.docBytes) throw new HttpError(413, "This page is too long. Split it into subpages.");
  return doc as PageDoc;
}
function checkText(text: string) {
  if (text.length > SPACE_LIMITS.text) throw new HttpError(413, "This page is too long. Split it into subpages.");
  return text;
}
function checkTitle(title: string) {
  const t = title.replace(/\s+/g, " ").trim();
  if (t.length > SPACE_LIMITS.title) throw new HttpError(400, `Keep the title under ${SPACE_LIMITS.title} characters.`);
  return t;
}

/** After the last sibling. Positions are short sortable strings; inserts only ever append. */
function nextPosition(last: string | undefined) {
  if (!last) return "a0";
  const n = parseInt(last.slice(1), 36);
  return `a${(Number.isFinite(n) ? n + 1 : 0).toString(36).padStart(4, "0")}`;
}

export async function createPage(
  userId: string,
  input: { space_id?: string; parent_page_id?: string | null; title?: string; doc?: unknown; text?: string; source_conversation_id?: string | null },
) {
  return asUser(userId, async (q) => {
    let spaceId = input.space_id;
    const parent = input.parent_page_id ?? null;
    if (parent) {
      const [p] = await q<{ space_id: string; level: Level | null; depth: number }[]>`
        with recursive up as (select id, parent_page_id, 1 as d from pages where id = ${parent}
          union all select pg.id, pg.parent_page_id, up.d + 1 from pages pg join up on pg.id = up.parent_page_id)
        select pg.space_id, page_access_level(pg.id) as level, (select max(d) from up)::int as depth from pages pg where pg.id = ${parent}`;
      if (!p) throw notFound();
      if (p.level !== "edit") throw new HttpError(403, "You can view this page but not add to it.");
      if (p.depth >= SPACE_LIMITS.depth) throw new HttpError(400, `Pages can nest ${SPACE_LIMITS.depth} levels deep.`);
      spaceId = p.space_id;
    }
    if (!spaceId) {
      const [mine] = await q<{ id: string }[]>`select id from spaces where owner_id = ${userId} and is_personal`;
      spaceId = mine?.id;
    }
    if (!spaceId) throw new HttpError(400, "Choose a space for the page.");
    const [s] = await q<{ level: Level | null }[]>`select space_access_level(${spaceId}) as level from spaces where id = ${spaceId}`;
    if (!parent && (!s || s.level !== "edit")) throw new HttpError(s ? 403 : 404, s ? "You can't add pages to this space." : "This space doesn't exist or isn't shared with you.");
    const [last] = await q<{ position: string }[]>`
      select position from pages where space_id = ${spaceId} and parent_page_id is not distinct from ${parent} order by position desc limit 1`;
    const doc = input.doc !== undefined ? checkDoc(input.doc) : { type: "doc", content: [] };
    const [page] = await q<{ id: string }[]>`
      insert into pages (space_id, parent_page_id, title, doc, text, position, created_by, updated_by, source_conversation_id)
      values (${spaceId}, ${parent}, ${checkTitle(input.title ?? "")}, ${q.json(doc as never)}, ${checkText(input.text ?? "")},
              ${nextPosition(last?.position)}, ${userId}, ${userId}, ${input.source_conversation_id ?? null})
      returning id`;
    return page;
  });
}

export async function getPage(userId: string, id: string): Promise<PageDetail> {
  return asUser(userId, async (q) => {
    const [page] = await q<(PageDetail["page"] & { level: Level })[]>`
      select pg.id, pg.space_id, pg.parent_page_id, pg.title, pg.doc, pg.text, pg.version, pg.updated_at,
             pr.name as updated_by_name, pg.source_conversation_id, page_access_level(pg.id) as level
      from pages pg left join profiles pr on pr.id = pg.updated_by where pg.id = ${id}`;
    if (!page) throw notFound();
    // The space row may be hidden when only this page was shared; read its name as the server.
    const [space] = await asService((s) => s<PageDetail["space"][]>`
      select id, name, is_personal, owner_id = ${userId} as is_owner from spaces where id = ${page.space_id}`);
    // Ancestors you can see (a page shared on its own shows no parents above it).
    const crumbs = await q<{ id: string; title: string; d: number }[]>`
      with recursive up as (select id, parent_page_id, 0 as d from pages where id = ${id}
        union all select pg.id, pg.parent_page_id, up.d + 1 from pages pg join up on pg.id = up.parent_page_id)
      select pg.id, pg.title, up.d from up join pages pg on pg.id = up.id where up.d > 0 order by up.d desc`;
    const children = await q<{ id: string; title: string }[]>`
      select id, title from pages where parent_page_id = ${id} order by position, created_at`;
    const { level, ...rest } = page;
    return {
      page: { ...rest, updated_at: new Date(rest.updated_at).toISOString() },
      space,
      level,
      breadcrumbs: crumbs.map(({ id, title }) => ({ id, title })),
      children,
    };
  });
}

/**
 * Save title and/or content. Content needs the version it was based on: if someone saved in between,
 * nothing is written and a 409 carries their version, so the editor can offer to reload or keep yours.
 */
export async function savePage(userId: string, id: string, patch: { title?: string; doc?: unknown; text?: string; base_version?: number; force?: boolean }) {
  return asUser(userId, async (q) => {
    const [cur] = await q<{ version: number; level: Level | null; title: string; updated_by_name: string | null }[]>`
      select pg.version, page_access_level(pg.id) as level, pg.title, pr.name as updated_by_name
      from pages pg left join profiles pr on pr.id = pg.updated_by where pg.id = ${id}`;
    if (!cur) throw notFound();
    if (cur.level !== "edit") throw new HttpError(403, "You can view this page but not edit it.");
    const title = patch.title !== undefined ? checkTitle(patch.title) : undefined;
    if (patch.doc !== undefined) {
      const doc = checkDoc(patch.doc);
      const text = checkText(patch.text ?? "");
      if (!patch.force && patch.base_version === undefined) throw new HttpError(400, "Say which version the edit is based on.");
      const rows = await q<{ version: number; updated_at: Date }[]>`
        update pages set doc = ${q.json(doc as never)}, text = ${text}, updated_by = ${userId},
          title = ${title ?? cur.title}
        where id = ${id} and (${!!patch.force} or version = ${patch.base_version ?? -1})
        returning version, updated_at`;
      if (!rows.length) {
        const [latest] = await q`
          select pg.version, pg.doc, pg.text, pg.title, pr.name as updated_by_name, pg.updated_at
          from pages pg left join profiles pr on pr.id = pg.updated_by where pg.id = ${id}`;
        throw new HttpError(409, `${latest.updated_by_name ?? "Someone"} changed this page while you were editing.`, { latest });
      }
      return { version: rows[0].version, updated_at: new Date(rows[0].updated_at).toISOString() };
    }
    if (title !== undefined) {
      const [row] = await q<{ version: number; updated_at: Date }[]>`
        update pages set title = ${title}, updated_by = ${userId} where id = ${id} returning version, updated_at`;
      return { version: row.version, updated_at: new Date(row.updated_at).toISOString() };
    }
    return { version: cur.version };
  });
}

export async function deletePage(userId: string, id: string) {
  return asUser(userId, async (q) => {
    const [p] = await q<{ level: Level | null; parent_page_id: string | null; space_id: string; n: number }[]>`
      with recursive down as (select id from pages where id = ${id} union all select pg.id from pages pg join down on pg.parent_page_id = down.id)
      select page_access_level(pg.id) as level, pg.parent_page_id, pg.space_id, (select count(*) from down)::int as n
      from pages pg where pg.id = ${id}`;
    if (!p) throw notFound();
    if (p.level !== "edit") throw new HttpError(403, "You can view this page but not delete it.");
    await q`delete from pages where id = ${id}`;
    return { deleted: p.n, parent_page_id: p.parent_page_id, space_id: p.space_id };
  });
}

/** Light polling state: version for live updates, who else is here. Also records that you're here. */
export async function pageState(userId: string, id: string, here?: { editing: boolean }) {
  return asUser(userId, async (q) => {
    const [p] = await q<{ version: number; title: string; level: Level | null; updated_by_name: string | null }[]>`
      select pg.version, pg.title, page_access_level(pg.id) as level, pr.name as updated_by_name
      from pages pg left join profiles pr on pr.id = pg.updated_by where pg.id = ${id}`;
    if (!p || !p.level) throw notFound();
    if (here) {
      await q`insert into page_presence (page_id, user_id, editing, seen_at) values (${id}, ${userId}, ${here.editing && p.level === "edit"}, now())
              on conflict (page_id, user_id) do update set editing = excluded.editing, seen_at = now()`;
    }
    const people = await q<{ user_id: string; name: string; editing: boolean }[]>`
      select pp.user_id, pr.name, pp.editing from page_presence pp join profiles pr on pr.id = pp.user_id
      where pp.page_id = ${id} and pp.user_id <> ${userId} and pp.seen_at > now() - interval '45 seconds' order by pr.name`;
    const [{ open }] = await q<{ open: number }[]>`select count(*)::int as open from comments where page_id = ${id} and resolved_at is null`;
    return { version: p.version, title: p.title, updated_by_name: p.updated_by_name, people, open_comments: open };
  });
}

export async function leavePage(userId: string, id: string) {
  await asUser(userId, (q) => q`delete from page_presence where page_id = ${id} and user_id = ${userId}`);
}

/* ------------------------------------------------------------------ sharing */

type Target = { space_id: string } | { page_id: string };

export async function listAccess(userId: string, t: Target) {
  return asUser(userId, async (q) => {
    if ("space_id" in t) {
      const [s] = await q<{ id: string; owner_id: string; owner_name: string; owner_email: string; everyone_level: Level | null; is_personal: boolean; level: Level | null }[]>`
        select s.id, s.owner_id, p.name as owner_name, p.email as owner_email, s.everyone_level, s.is_personal, space_access_level(s.id) as level
        from spaces s join profiles p on p.id = s.owner_id where s.id = ${t.space_id}`;
      if (!s || !s.level) throw notFound("This space doesn't exist or isn't shared with you.");
      const people = await q<AccessEntry[]>`
        select pa.id, pa.user_id, p.name, p.email, pa.level, null as inherited_from
        from page_access pa join profiles p on p.id = pa.user_id where pa.space_id = ${t.space_id} order by p.name`;
      return { owner: { id: s.owner_id, name: s.owner_name, email: s.owner_email }, everyone_level: s.everyone_level, is_personal: s.is_personal, can_share: s.level === "edit", people };
    }
    const [pg] = await q<{ space_id: string; level: Level | null }[]>`select space_id, page_access_level(id) as level from pages where id = ${t.page_id}`;
    if (!pg || !pg.level) throw notFound();
    // Grants on this page and the pages above it (inherited), plus the space's own people.
    const people = await q<AccessEntry[]>`
      with recursive up as (select id, parent_page_id, title, 0 as d from pages where id = ${t.page_id}
        union all select pg.id, pg.parent_page_id, pg.title, up.d + 1 from pages pg join up on pg.id = up.parent_page_id)
      select pa.id, pa.user_id, p.name, p.email, pa.level,
             case when up.d = 0 then null else coalesce(nullif(up.title, ''), 'Untitled') end as inherited_from
      from page_access pa join up on up.id = pa.page_id join profiles p on p.id = pa.user_id
      union all
      select pa.id, pa.user_id, p.name, p.email, pa.level, 'the space' as inherited_from
      from page_access pa join profiles p on p.id = pa.user_id where pa.space_id = ${pg.space_id}
      order by name`;
    const [s] = await asService((sq) => sq<{ owner_id: string; owner_name: string; owner_email: string; everyone_level: Level | null; is_personal: boolean }[]>`
      select s.owner_id, p.name as owner_name, p.email as owner_email, s.everyone_level, s.is_personal
      from spaces s join profiles p on p.id = s.owner_id where s.id = ${pg.space_id}`);
    return { owner: { id: s.owner_id, name: s.owner_name, email: s.owner_email }, everyone_level: s.everyone_level, is_personal: s.is_personal, can_share: pg.level === "edit", people };
  });
}

export async function grantAccess(userId: string, t: Target, input: { user_id: string; level: Level }) {
  if (!LEVELS.includes(input.level)) throw new HttpError(400, "Choose view, comment or edit.");
  return asUser(userId, async (q) => {
    const [ok] = "space_id" in t
      ? await q<{ level: Level | null }[]>`select space_access_level(${t.space_id}) as level`
      : await q<{ level: Level | null }[]>`select page_access_level(${t.page_id}) as level from pages where id = ${t.page_id}`;
    if (!ok?.level) throw notFound("space_id" in t ? "This space doesn't exist or isn't shared with you." : undefined);
    if (ok.level !== "edit") throw new HttpError(403, "Only people who can edit can share.");
    if (input.user_id === userId) throw new HttpError(400, "You already have access.");
    const [teammate] = await q<{ ok: boolean }[]>`select shares_workspace(${input.user_id}) as ok`;
    if (!teammate?.ok) throw new HttpError(400, "You can share only with people in your workspace.");
    const spaceId = "space_id" in t ? t.space_id : null;
    const pageId = "page_id" in t ? t.page_id : null;
    const [existing] = spaceId
      ? await q<{ id: string }[]>`select id from page_access where space_id = ${spaceId} and user_id = ${input.user_id}`
      : await q<{ id: string }[]>`select id from page_access where page_id = ${pageId} and user_id = ${input.user_id}`;
    if (existing) {
      const [row] = await q`update page_access set level = ${input.level}, granted_by = ${userId} where id = ${existing.id} returning id, level`;
      return row;
    }
    const [row] = await q`
      insert into page_access (space_id, page_id, user_id, level, granted_by)
      values (${spaceId}, ${pageId}, ${input.user_id}, ${input.level}, ${userId}) returning id, level`;
    return row;
  });
}

export async function revokeAccess(userId: string, accessId: string) {
  return asUser(userId, async (q) => {
    const rows = await q`delete from page_access where id = ${accessId} returning id`;
    if (!rows.length) {
      const [seen] = await q`select 1 from page_access where id = ${accessId}`;
      throw seen ? new HttpError(403, "Only people who can edit can change sharing.") : new HttpError(404, "That access was already removed.");
    }
  });
}

/* ------------------------------------------------------------------ comments */

export async function listComments(userId: string, pageId: string) {
  return asUser(userId, async (q) => {
    const [p] = await q`select 1 from pages where id = ${pageId}`;
    if (!p) throw notFound();
    const rows = await q<(Omit<CommentRow, "mine" | "created_at" | "resolved_at"> & { created_at: Date; resolved_at: Date | null })[]>`
      select c.id, c.page_id, c.parent_comment_id, c.author_id, a.name as author_name, c.quote, c.body,
             c.resolved_at, r.name as resolved_by_name, c.created_at
      from comments c left join profiles a on a.id = c.author_id left join profiles r on r.id = c.resolved_by
      where c.page_id = ${pageId} order by c.created_at`;
    return rows.map((c) => ({
      ...c,
      created_at: new Date(c.created_at).toISOString(),
      resolved_at: c.resolved_at ? new Date(c.resolved_at).toISOString() : null,
      mine: c.author_id === userId,
    }));
  });
}

export async function addComment(userId: string, pageId: string, input: { body: string; quote?: string | null; parent_comment_id?: string | null }) {
  const body = input.body.trim();
  if (!body) throw new HttpError(400, "Write a comment first.");
  if (body.length > SPACE_LIMITS.comment) throw new HttpError(400, "That comment is too long.");
  return asUser(userId, async (q) => {
    const [p] = await q<{ level: Level | null }[]>`select page_access_level(${pageId}) as level from pages where id = ${pageId}`;
    if (!p?.level) throw notFound();
    if (p.level === "view") throw new HttpError(403, "You can view this page but not comment on it.");
    if (input.parent_comment_id) {
      const [parent] = await q`select 1 from comments where id = ${input.parent_comment_id} and page_id = ${pageId} and parent_comment_id is null`;
      if (!parent) throw new HttpError(400, "You can reply only to a comment on this page.");
    }
    const [c] = await q<{ id: string }[]>`
      insert into comments (page_id, author_id, parent_comment_id, quote, body)
      values (${pageId}, ${userId}, ${input.parent_comment_id ?? null}, ${input.quote?.trim().slice(0, SPACE_LIMITS.quote) || null}, ${body})
      returning id`;
    return c;
  });
}

export async function updateComment(userId: string, id: string, patch: { body?: string; resolved?: boolean }) {
  return asUser(userId, async (q) => {
    const [c] = await q<{ author_id: string | null; level: Level | null; parent_comment_id: string | null }[]>`
      select c.author_id, page_access_level(c.page_id) as level, c.parent_comment_id from comments c where c.id = ${id}`;
    if (!c) throw new HttpError(404, "That comment was deleted.");
    if (patch.body !== undefined) {
      if (c.author_id !== userId) throw new HttpError(403, "You can edit only your own comments.");
      const body = patch.body.trim();
      if (!body || body.length > SPACE_LIMITS.comment) throw new HttpError(400, "Write a comment first.");
      await q`update comments set body = ${body} where id = ${id}`;
    }
    if (patch.resolved !== undefined) {
      if (c.parent_comment_id) throw new HttpError(400, "Resolve the thread, not a reply.");
      if (c.author_id !== userId && c.level !== "edit") throw new HttpError(403, "Only the author or an editor can resolve this.");
      await q`update comments set resolved_at = ${patch.resolved ? q`now()` : null}, resolved_by = ${patch.resolved ? userId : null} where id = ${id}`;
    }
    return { ok: true };
  });
}

export async function deleteComment(userId: string, id: string) {
  return asUser(userId, async (q) => {
    const rows = await q`delete from comments where id = ${id} returning id`;
    if (!rows.length) {
      const [seen] = await q`select 1 from comments where id = ${id}`;
      throw seen ? new HttpError(403, "You can delete only your own comments.") : new HttpError(404, "That comment was already deleted.");
    }
  });
}
