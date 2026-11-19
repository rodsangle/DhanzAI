import "server-only";
import { cookies } from "next/headers";
import { asService } from "./db";
import { authMode, DEV_SESSION_COOKIE, supabaseServer } from "./auth";
import { HttpError } from "@/lib/data/errors";

/**
 * S28 Settings → Security: where you're signed in.
 *
 * Sessions live in Supabase's own auth.sessions table (a local stand-in with the same columns in dev mode).
 * Signing a device out deletes its row, which also removes its refresh tokens. The app checks every request
 * with the auth server (auth.getUser()), which refuses tokens whose session no longer exists, so the device
 * is signed out on its next request rather than when its access token expires.
 */
export type SessionRow = {
  id: string;
  created_at: string;
  last_active: string;
  device: string;
  ip_hint: string | null;
  current: boolean;
};

/** The id of the session making this request. */
export async function currentSessionId(): Promise<string | null> {
  if (authMode() === "dev") return (await cookies()).get(DEV_SESSION_COOKIE)?.value ?? null;
  const { data } = await (await supabaseServer()).auth.getClaims();
  const sid = (data?.claims as { session_id?: string } | undefined)?.session_id;
  return sid ?? null;
}

/** "Chrome on macOS" from a user agent. Coarse on purpose: enough to recognise your own device. */
export function describeDevice(ua: string | null | undefined): string {
  if (!ua) return "Unknown device";
  const browser =
    /Edg\//.test(ua) ? "Edge" :
    /OPR\/|Opera/.test(ua) ? "Opera" :
    /Firefox\//.test(ua) ? "Firefox" :
    /Chrome\/|CriOS\//.test(ua) ? "Chrome" :
    /Safari\//.test(ua) ? "Safari" :
    /HeadlessChrome/.test(ua) ? "Chrome" : null;
  const os =
    /iPhone|iPad|iPod/.test(ua) ? (/iPad/.test(ua) ? "iPad" : "iPhone") :
    /Android/.test(ua) ? "Android" :
    /Mac OS X|Macintosh/.test(ua) ? "macOS" :
    /Windows/.test(ua) ? "Windows" :
    /CrOS/.test(ua) ? "ChromeOS" :
    /Linux/.test(ua) ? "Linux" : null;
  if (!browser) return os ? `Browser on ${os}` : "Other app or browser";
  return os ? `${browser} on ${os}` : browser;
}

/** Only the start of the address: enough to tell home from office, not a full address on screen. */
export function ipHint(ip: string | null): string | null {
  if (!ip) return null;
  if (ip.includes(":")) return `${ip.split(":").slice(0, 2).join(":")}:…`;
  const p = ip.split(".");
  return p.length === 4 ? `${p[0]}.${p[1]}.x.x` : null;
}

export async function listSessions(userId: string): Promise<SessionRow[]> {
  const current = await currentSessionId();
  const rows = await asService((q) => q<{ id: string; created_at: Date; last_active: Date; user_agent: string | null; ip: string | null }[]>`
    select id, created_at, greatest(updated_at, coalesce(refreshed_at at time zone 'UTC', updated_at)) as last_active,
           user_agent, host(ip) as ip
    from auth.sessions
    where user_id = ${userId} and (not_after is null or not_after > now())
    order by last_active desc
    limit 50`);
  const out = rows.map((r) => ({
    id: r.id,
    created_at: new Date(r.created_at).toISOString(),
    last_active: new Date(r.last_active).toISOString(),
    device: describeDevice(r.user_agent),
    ip_hint: ipHint(r.ip),
    current: r.id === current,
  }));
  // This device first.
  return out.sort((a, b) => Number(b.current) - Number(a.current));
}

export async function revokeSession(userId: string, sessionId: string) {
  if (sessionId === (await currentSessionId())) {
    throw new HttpError(400, "That's this device. Use Sign out instead.");
  }
  const rows = await asService((q) => q`delete from auth.sessions where id = ${sessionId} and user_id = ${userId} returning id`);
  if (!rows.length) throw new HttpError(404, "That session has already ended.");
}

export async function revokeOtherSessions(userId: string) {
  const current = await currentSessionId();
  const rows = await asService((q) => q`
    delete from auth.sessions where user_id = ${userId} and (${current}::uuid is null or id <> ${current}::uuid) returning id`);
  return { signed_out: rows.length };
}
