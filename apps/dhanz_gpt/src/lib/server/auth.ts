import "server-only";
import { cookies, headers } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import { getProfile } from "@/lib/data";
import { asService } from "./db";
import { HttpError } from "@/lib/data/errors";
import { dhanzSessionValid } from "./dhanz-auth";

/**
 * Who is signed in.
 * - NEXT_PUBLIC_AUTH_MODE=supabase (default when NEXT_PUBLIC_SUPABASE_URL is set): Supabase Auth session cookies,
 *   verified with the auth server on each request (`auth.getUser()`), Google sign-in only.
 * - NEXT_PUBLIC_AUTH_MODE=dev: a cookie set by /api/auth/dev-login. Only honoured on localhost, so it can't be
 *   switched on by accident in a deployment.
 * - NEXT_PUBLIC_AUTH_MODE=dhanz: DHANZ AI accounts (email, password, two-step) checked by the DHANZ API
 *   (see dhanz-auth.ts). Same session cookies as dev mode, Secure in production, re-checked with DHANZ.
 */
export const DEV_COOKIE = "dg_uid";
/** Dev mode's session id: a row in auth.sessions, like Supabase's, so per-device sign-out works locally too. */
export const DEV_SESSION_COOKIE = "dg_sid";

export function authMode(): "supabase" | "dev" | "dhanz" {
  // AUTH_MODE is read at run time (one image, any mode); NEXT_PUBLIC_AUTH_MODE is baked in at build time.
  const m = process.env.AUTH_MODE ?? process.env.NEXT_PUBLIC_AUTH_MODE ?? (process.env.NEXT_PUBLIC_SUPABASE_URL ? "supabase" : "dev");
  if (m !== "supabase" && m !== "dev" && m !== "dhanz") throw new Error(`Unknown AUTH_MODE ${m}`);
  return m;
}

/** Session cookie options: Secure whenever the app is served over https. */
export function sessionCookie() {
  const secure = (process.env.APP_URL ?? "").startsWith("https://");
  return { httpOnly: true, secure, sameSite: "lax" as const, path: "/", maxAge: 60 * 60 * 24 * 30 };
}

export async function isLocalRequest() {
  const h = await headers();
  const host = (h.get("x-forwarded-host") ?? h.get("host") ?? "").split(":")[0];
  return host === "localhost" || host === "127.0.0.1" || host === "[::1]";
}

export async function supabaseServer() {
  const jar = await cookies();
  return createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, {
    cookies: {
      getAll: () => jar.getAll(),
      setAll: (list) => {
        try {
          for (const { name, value, options } of list) jar.set(name, value, options);
        } catch {
          // Called from a place that can't set cookies; the proxy refreshes the session instead.
        }
      },
    },
  });
}

export async function currentUserId(): Promise<string | null> {
  const mode = authMode();
  if (mode === "dev" || mode === "dhanz") {
    if (mode === "dev" && !(await isLocalRequest())) return null;
    const jar = await cookies();
    const id = jar.get(DEV_COOKIE)?.value ?? null;
    const sid = jar.get(DEV_SESSION_COOKIE)?.value ?? null;
    const uuid = /^[0-9a-f-]{36}$/i;
    if (!id || !sid || !uuid.test(id) || !uuid.test(sid)) return null;
    // The session must still exist (not signed out from another device). Touch it at most once a minute.
    const [row] = await asService((q) => q`
      update auth.sessions set refreshed_at = case when refreshed_at is null or refreshed_at < (now() at time zone 'UTC') - interval '1 minute'
        then now() at time zone 'UTC' else refreshed_at end
      where id = ${sid} and user_id = ${id} returning id`);
    if (!row) return null;
    if (mode === "dhanz" && !(await dhanzSessionValid(sid, id))) return null;
    return (await getProfile(id)) ? id : null;
  }
  const { data, error } = await (await supabaseServer()).auth.getUser();
  if (error || !data.user) return null;
  return data.user.id;
}

/** Dev mode: start a session for this browser (Supabase does this itself when you sign in with Google). */
export async function startDevSession(userId: string, userAgent: string | null, ip: string | null) {
  const [row] = await asService((q) => q<{ id: string }[]>`
    insert into auth.sessions (user_id, user_agent, ip) values (${userId}, ${userAgent?.slice(0, 500) ?? null}, ${ip}::inet) returning id`);
  return row.id;
}

export async function requireUser(): Promise<string> {
  const id = await currentUserId();
  if (!id) throw new HttpError(401, "Sign in to continue.");
  return id;
}
