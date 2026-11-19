import "server-only";
import { asService } from "./db";
import { HttpError } from "@/lib/data/errors";
import { open, seal } from "@/lib/apps/crypto";

/**
 * Sign-in with DHANZ AI accounts (NEXT_PUBLIC_AUTH_MODE=dhanz).
 *
 * Dhanz GPT never sees or stores a password beyond passing it once to the DHANZ API:
 *   POST {DHANZ_API_URL}/auth/login        → tokens, or a two-step challenge (mfa_token)
 *   POST {DHANZ_API_URL}/auth/mfa/verify   → tokens
 *   GET  {DHANZ_API_URL}/users/me          → still signed in? (bearer access token)
 *   POST {DHANZ_API_URL}/auth/refresh      → new tokens (DHANZ rotates refresh tokens; reusing one ends
 *                                             the whole DHANZ session, so refreshes are serialised per session)
 *   POST {DHANZ_API_URL}/auth/logout       → ends the DHANZ session
 *
 * A successful sign-in creates a Dhanz GPT session (auth.sessions) with the DHANZ tokens sealed in
 * dhanz_sessions. Every few minutes a request re-checks the account with DHANZ; if DHANZ says the session
 * is over (signed out on another device, password changed, account deleted), the Dhanz GPT session ends too.
 */

export const DHANZ_RECHECK_SECONDS = 5 * 60;
/** If the DHANZ API can't be reached, keep people signed in this long since the last good check. */
const OFFLINE_GRACE_SECONDS = 60 * 60;

type DhanzUser = { id: string; email: string; display_name: string; email_verified?: boolean };
type Tokens = { access_token: string; refresh_token: string; expires_in: number; user: DhanzUser };
type Challenge = { mfa_required: true; mfa_token: string; expires_in: number; method?: "totp" | "email"; email_hint?: string | null };

export function dhanzApiUrl() {
  const u = process.env.DHANZ_API_URL;
  if (!u) throw new Error("DHANZ_API_URL is not set");
  return u.replace(/\/$/, "");
}

async function call(path: string, init: { method?: string; body?: unknown; token?: string; ip?: string | null; ua?: string | null }) {
  let res: Response;
  try {
    res = await fetch(`${dhanzApiUrl()}${path}`, {
      method: init.method ?? "POST",
      headers: {
        Accept: "application/json",
        ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(init.token ? { Authorization: `Bearer ${init.token}` } : {}),
        ...(init.ip ? { "X-Forwarded-For": init.ip } : {}),
        ...(init.ua ? { "User-Agent": `${init.ua.slice(0, 300)} (via Dhanz GPT)` } : { "User-Agent": "Dhanz GPT" }),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: AbortSignal.timeout(15_000),
      cache: "no-store",
    });
  } catch {
    return { ok: false as const, status: 0, json: {} as Record<string, unknown> };
  }
  const json = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  return { ok: res.ok, status: res.status, json };
}

/** DHANZ's own wording when it's safe to show (lockouts, rate limits), else ours. */
function failure(status: number, json: Record<string, unknown>, fallback: string): never {
  const detail = typeof json.detail === "string" ? json.detail : null;
  if (status === 0) throw new HttpError(503, "DHANZ AI sign-in isn't reachable right now. Try again in a minute.");
  if (status === 401 || status === 400 || status === 422) throw new HttpError(401, fallback);
  if (status === 403 && detail) throw new HttpError(403, detail);
  if ((status === 423 || status === 429) && detail) throw new HttpError(429, detail);
  if (status === 429) throw new HttpError(429, "Too many attempts. Wait a minute and try again.");
  throw new HttpError(502, "DHANZ AI sign-in had a problem. Try again.");
}

function isTokens(j: Record<string, unknown>): j is Tokens & Record<string, unknown> {
  return typeof j.access_token === "string" && typeof j.refresh_token === "string" && !!j.user;
}

export type LoginResult = { kind: "session"; sessionId: string; userId: string } | { kind: "challenge"; mfa_token: string; method: "totp" | "email"; email_hint: string | null; expires_in: number };

export async function dhanzLogin(email: string, password: string, ip: string | null, ua: string | null): Promise<LoginResult> {
  const r = await call("/auth/login", { body: { email, password }, ip, ua });
  if (!r.ok) failure(r.status, r.json, "That email and password don't match a DHANZ AI account.");
  if ((r.json as Partial<Challenge>).mfa_required) {
    const c = r.json as unknown as Challenge;
    return { kind: "challenge", mfa_token: c.mfa_token, method: c.method ?? "totp", email_hint: c.email_hint ?? null, expires_in: c.expires_in };
  }
  if (!isTokens(r.json)) failure(502, {}, "");
  return startSession(r.json as unknown as Tokens, ip, ua);
}

export async function dhanzVerify(mfaToken: string, code: string, ip: string | null, ua: string | null): Promise<LoginResult> {
  const r = await call("/auth/mfa/verify", { body: { mfa_token: mfaToken, code: code.replace(/\s+/g, "") }, ip, ua });
  if (!r.ok) {
    if (r.status === 400 || r.status === 401 || r.status === 422) throw new HttpError(401, "That code didn't work. Check it and try again, or start over.");
    failure(r.status, r.json, "");
  }
  if (!isTokens(r.json)) failure(502, {}, "");
  return startSession(r.json as unknown as Tokens, ip, ua);
}

/** Mirror the DHANZ account locally (same id), then open a session holding its tokens. */
async function startSession(t: Tokens, ip: string | null, ua: string | null): Promise<LoginResult> {
  const u = t.user;
  if (!/^[0-9a-f-]{36}$/i.test(u.id) || !u.email) throw new HttpError(502, "DHANZ AI sign-in had a problem. Try again.");
  if (u.email_verified === false) throw new HttpError(403, "Verify your email in DHANZ AI first, then sign in here.");
  const email = u.email.toLowerCase();
  const sessionId = await asService(async (q) => {
    const [clash] = await q<{ id: string }[]>`select id from auth.users where lower(email) = ${email} and id <> ${u.id}`;
    if (clash) throw new HttpError(409, "This email belongs to an older account here. Contact DHANZ AI support to move it.");
    await q`
      insert into auth.users (id, email, raw_user_meta_data)
      values (${u.id}, ${email}, ${q.json({ full_name: u.display_name || email.split("@")[0] })})
      on conflict (id) do update set email = excluded.email`;
    // Keep the display name in step with DHANZ.
    if (u.display_name) await q`update profiles set name = ${u.display_name.slice(0, 120)} where id = ${u.id} and name is distinct from ${u.display_name.slice(0, 120)}`;
    const [s] = await q<{ id: string }[]>`
      insert into auth.sessions (user_id, user_agent, ip)
      values (${u.id}, ${ua?.slice(0, 500) ?? null}, ${ip && /^[0-9a-f.:]+$/i.test(ip) ? ip : null}::inet) returning id`;
    await q`
      insert into dhanz_sessions (session_id, user_id, access_token, refresh_token, access_expires_at)
      values (${s.id}, ${u.id}, ${seal(t.access_token)}, ${seal(t.refresh_token)}, now() + make_interval(secs => ${Math.max(60, t.expires_in)}))`;
    return s.id;
  });
  return { kind: "session", sessionId, userId: u.id };
}

/**
 * Is this session still good with DHANZ? Cheap most of the time (a recent check is trusted); every few
 * minutes it asks DHANZ, refreshing the tokens when they've expired. Refreshes are serialised per session
 * with an advisory lock, because DHANZ treats a reused refresh token as theft and ends the session.
 */
export async function dhanzSessionValid(sessionId: string, userId: string): Promise<boolean> {
  const [row] = await asService((q) => q<{ fresh: boolean }[]>`
    select checked_at > now() - make_interval(secs => ${DHANZ_RECHECK_SECONDS}) as fresh
    from dhanz_sessions where session_id = ${sessionId} and user_id = ${userId}`);
  if (!row) return false;
  if (row.fresh) return true;

  return asService(async (q) => {
    await q`select pg_advisory_xact_lock(hashtext(${"dhanz-session:" + sessionId}))`;
    const [s] = await q<{ access_token: Buffer; refresh_token: Buffer; access_expires_at: Date; checked_at: Date; fresh: boolean }[]>`
      select access_token, refresh_token, access_expires_at, checked_at,
             checked_at > now() - make_interval(secs => ${DHANZ_RECHECK_SECONDS}) as fresh
      from dhanz_sessions where session_id = ${sessionId} and user_id = ${userId}`;
    if (!s) return false;
    if (s.fresh) return true; // another request checked while we waited

    let access = open(s.access_token);
    let me = new Date(s.access_expires_at).getTime() - Date.now() > 30_000 ? await call("/users/me", { method: "GET", token: access }) : { ok: false, status: 401, json: {} };
    if (!me.ok && me.status === 401) {
      const r = await call("/auth/refresh", { body: { refresh_token: open(s.refresh_token) } });
      if (r.ok && isTokens(r.json)) {
        const t = r.json as unknown as Tokens;
        access = t.access_token;
        await q`
          update dhanz_sessions set access_token = ${seal(t.access_token)}, refresh_token = ${seal(t.refresh_token)},
            access_expires_at = now() + make_interval(secs => ${Math.max(60, t.expires_in)})
          where session_id = ${sessionId}`;
        me = { ok: true, status: 200, json: t.user as unknown as Record<string, unknown> };
      } else if (r.status === 0 || r.status >= 500) {
        me = { ok: false, status: 0, json: {} };
      } else {
        me = { ok: false, status: 401, json: {} };
      }
    }
    if (me.ok) {
      const u = me.json as unknown as DhanzUser;
      if (u.id !== userId) {
        await q`delete from auth.sessions where id = ${sessionId}`;
        return false;
      }
      await q`update dhanz_sessions set checked_at = now() where session_id = ${sessionId}`;
      if (u.email && u.email.toLowerCase() !== "") await q`update auth.users set email = ${u.email.toLowerCase()} where id = ${userId} and email <> ${u.email.toLowerCase()}`;
      return true;
    }
    if (me.status === 0 || me.status >= 500) {
      // DHANZ unreachable: don't sign everyone out for a blip, but not forever either.
      return Date.now() - new Date(s.checked_at).getTime() < OFFLINE_GRACE_SECONDS * 1000;
    }
    // DHANZ says this session is over.
    await q`delete from auth.sessions where id = ${sessionId}`;
    return false;
  });
}

/** Sign out here and end the matching DHANZ session. */
export async function dhanzLogout(sessionId: string) {
  const [s] = await asService((q) => q<{ refresh_token: Buffer }[]>`select refresh_token from dhanz_sessions where session_id = ${sessionId}`);
  if (s) await call("/auth/logout", { body: { refresh_token: open(s.refresh_token) } });
}
