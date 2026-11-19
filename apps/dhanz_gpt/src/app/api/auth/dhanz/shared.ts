import { NextResponse } from "next/server";
import { headers } from "next/headers";
import { authMode, DEV_COOKIE, DEV_SESSION_COOKIE, sessionCookie } from "@/lib/server/auth";
import { HttpError } from "@/lib/data/errors";
import type { LoginResult } from "@/lib/server/dhanz-auth";

/** The visitor as Caddy saw them (first X-Forwarded-For hop), and their browser. */
export async function visitor() {
  const h = await headers();
  const ip = h.get("x-forwarded-for")?.split(",")[0]?.trim() || h.get("x-real-ip") || null;
  return { ip: ip && /^[0-9a-f.:]{3,45}$/i.test(ip) ? ip : null, ua: h.get("user-agent") };
}

// Our own brake on sign-in attempts per address (DHANZ has its own per-account lockout too).
const attempts = new Map<string, number[]>();
export function limitAttempts(ip: string | null) {
  const key = ip ?? "unknown";
  const now = Date.now();
  const recent = (attempts.get(key) ?? []).filter((t) => now - t < 10 * 60_000);
  if (recent.length >= 20) throw new HttpError(429, "Too many sign-in attempts. Wait a few minutes and try again.");
  recent.push(now);
  attempts.set(key, recent);
  if (attempts.size > 10_000) attempts.clear();
}

export function requireDhanzMode() {
  if (authMode() !== "dhanz") throw new HttpError(404, "Not found.");
}

export function respond(r: LoginResult) {
  if (r.kind === "challenge") {
    return NextResponse.json({ mfa_required: true, mfa_token: r.mfa_token, method: r.method, email_hint: r.email_hint, expires_in: r.expires_in });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set(DEV_COOKIE, r.userId, sessionCookie());
  res.cookies.set(DEV_SESSION_COOKIE, r.sessionId, sessionCookie());
  return res;
}
