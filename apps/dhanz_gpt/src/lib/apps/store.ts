import "server-only";
import { asService, asUser } from "@/lib/server/db";
import { HttpError } from "@/lib/data/errors";
import { open, seal } from "./crypto";
import { PROVIDERS, provider, toolOwner } from "./registry";
import { AppError, type Account, type PermissionLevel, type ProviderId, type TokenSet } from "./types";

/**
 * App connections (S20). One per person and app account. Tokens live in app_tokens, encrypted; the
 * table has no policies for signed-in users, so only the server reads them. Connections are owner-only (RLS).
 */

export interface AppItem {
  id: ProviderId;
  name: string;
  description: string;
  can: string[];
  mentions: string[];
  needs_shop: boolean;
  configured: boolean;
  connection: { id: string; account: string; permission_level: PermissionLevel; status: string; always_allowed: string[]; created_at: string } | null;
}

type ConnRow = {
  id: string; user_id: string; provider: ProviderId; external_account_id: string; external_account_label: string | null;
  permission_level: PermissionLevel; status: string; always_allowed: string[]; created_at: string;
};

export async function listApps(userId: string): Promise<AppItem[]> {
  const rows = await asUser(userId, (q) => q<ConnRow[]>`select * from app_connections where user_id = ${userId} order by created_at`);
  return PROVIDERS.map((p) => {
    const c = rows.find((r) => r.provider === p.id && r.status === "active") ?? rows.find((r) => r.provider === p.id);
    return {
      id: p.id, name: p.name, description: p.description, can: p.can, mentions: p.mentions, needs_shop: !!p.needsShop, configured: p.configured(),
      connection: c
        ? { id: c.id, account: c.external_account_label ?? c.external_account_id, permission_level: c.permission_level, status: c.status, always_allowed: c.always_allowed, created_at: c.created_at }
        : null,
    };
  });
}

export async function saveConnection(userId: string, providerId: ProviderId, account: Account, tokens: TokenSet) {
  const [m] = await asService((q) => q<{ workspace_id: string }[]>`select workspace_id from memberships where user_id = ${userId} limit 1`);
  return asService(async (q) => {
    // One active account per app: connecting again replaces the old one.
    await q`delete from app_connections where user_id = ${userId} and provider = ${providerId} and external_account_id <> ${account.id}`;
    const [c] = await q<{ id: string }[]>`
      insert into app_connections (workspace_id, user_id, provider, external_account_id, external_account_label, scopes, status)
      values (${m.workspace_id}, ${userId}, ${providerId}, ${account.id}, ${account.label}, ${tokens.scopes}, 'active')
      on conflict (user_id, provider, external_account_id) do update set
        external_account_label = excluded.external_account_label, scopes = excluded.scopes, status = 'active', updated_at = now()
      returning id`;
    const expires = tokens.expires_in ? new Date(Date.now() + tokens.expires_in * 1000) : null;
    await q`
      insert into app_tokens (connection_id, access_token_enc, refresh_token_enc, expires_at)
      values (${c.id}, ${seal(tokens.access_token)}, ${tokens.refresh_token ? seal(tokens.refresh_token) : null}, ${expires})
      on conflict (connection_id) do update set access_token_enc = excluded.access_token_enc,
        refresh_token_enc = coalesce(excluded.refresh_token_enc, app_tokens.refresh_token_enc), expires_at = excluded.expires_at, updated_at = now()`;
    return c.id;
  });
}

export async function setPermission(userId: string, id: string, level: PermissionLevel) {
  const rows = await asUser(userId, (q) => q`
    update app_connections set permission_level = ${level}, always_allowed = '{}', updated_at = now() where id = ${id} returning id`);
  if (!rows.length) throw new HttpError(404, "That connection doesn't exist.");
}

export async function allowAlways(userId: string, connectionId: string, tool: string) {
  await asUser(userId, (q) => q`
    update app_connections set always_allowed = array(select distinct unnest(always_allowed || ${[tool]}::text[])), updated_at = now()
    where id = ${connectionId}`);
}

/** Disconnect: revoke at the provider when it supports that, then forget the tokens. */
export async function disconnect(userId: string, id: string) {
  const [c] = await asUser(userId, (q) => q<ConnRow[]>`select * from app_connections where id = ${id}`);
  if (!c) throw new HttpError(404, "That connection doesn't exist.");
  const p = provider(c.provider);
  const token = await accessToken(c.id).catch(() => null);
  if (token && p?.revoke) await p.revoke(token.token, token.shop).catch(() => {});
  await asUser(userId, (q) => q`delete from app_connections where id = ${id}`);
}

/** The connection the person has for an app, if active. */
export async function activeConnection(userId: string, providerId: ProviderId) {
  const [c] = await asService((q) => q<ConnRow[]>`
    select * from app_connections where user_id = ${userId} and provider = ${providerId} and status = 'active' limit 1`);
  return c ?? null;
}

/** A usable access token, refreshed first if it's about to expire. Marks the connection expired if that fails. */
export async function accessToken(connectionId: string): Promise<{ token: string; shop: string | null }> {
  const [row] = await asService((q) => q<{ provider: ProviderId; external_account_id: string; access_token_enc: Buffer; refresh_token_enc: Buffer | null; expires_at: string | null }[]>`
    select c.provider, c.external_account_id, t.access_token_enc, t.refresh_token_enc, t.expires_at
    from app_connections c join app_tokens t on t.connection_id = c.id where c.id = ${connectionId}`);
  if (!row) throw new AppError("That app isn't connected.", 401);
  const shop = row.provider === "shopify" ? row.external_account_id : null;
  const soon = row.expires_at && new Date(row.expires_at).getTime() < Date.now() + 60_000;
  if (!soon) return { token: open(row.access_token_enc), shop };
  const p = provider(row.provider);
  if (!p?.refresh || !row.refresh_token_enc) {
    await asService((q) => q`update app_connections set status = 'expired', updated_at = now() where id = ${connectionId}`);
    throw new AppError(`${p?.name ?? "The app"} needs reconnecting. Open Apps to reconnect it.`, 401);
  }
  try {
    const t = await p.refresh(open(row.refresh_token_enc));
    await asService((q) => q`
      update app_tokens set access_token_enc = ${seal(t.access_token)},
        refresh_token_enc = coalesce(${t.refresh_token ? seal(t.refresh_token) : null}, refresh_token_enc),
        expires_at = ${t.expires_in ? new Date(Date.now() + t.expires_in * 1000) : null}, updated_at = now()
      where connection_id = ${connectionId}`);
    return { token: t.access_token, shop };
  } catch {
    await asService((q) => q`update app_connections set status = 'expired', updated_at = now() where id = ${connectionId}`);
    throw new AppError(`${p.name} needs reconnecting. Open Apps to reconnect it.`, 401);
  }
}

/** Runs one app action for a person. Errors come back as text for the model, never thrown into the answer. */
export async function runTool(userId: string, name: string, input: Record<string, unknown>) {
  const owner = toolOwner(name);
  if (!owner) return { ok: false, result: `Unknown action ${name}.`, summary: "Unknown action" };
  const conn = await activeConnection(userId, owner.provider.id);
  if (!conn) return { ok: false, result: `${owner.provider.name} isn't connected. Ask the person to connect it in Apps.`, summary: `${owner.provider.name} isn't connected` };
  try {
    const t = await accessToken(conn.id);
    const r = await owner.tool.run(t, input);
    return { ok: true, ...r };
  } catch (e) {
    if (e instanceof AppError && e.status === 401) await asService((q) => q`update app_connections set status = 'expired', updated_at = now() where id = ${conn.id}`);
    const msg = e instanceof AppError ? e.message : `${owner.provider.name} didn't respond as expected.`;
    if (!(e instanceof AppError)) console.error("[apps]", name, (e as Error).message);
    return { ok: false, result: msg, summary: msg };
  }
}
