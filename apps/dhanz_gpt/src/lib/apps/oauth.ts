import "server-only";
import crypto from "node:crypto";
import { safeEqual, sign } from "./crypto";

/** The OAuth round trip's state, PKCE verifier and store name, in a signed, httpOnly, 10-minute cookie. */
export const OAUTH_COOKIE = "dg_app_oauth";

export type OAuthState = { p: string; s: string; v: string; shop: string | null; uid: string; exp: number };

export function newState(providerId: string, uid: string, shop: string | null) {
  const st: OAuthState = {
    p: providerId,
    s: crypto.randomBytes(24).toString("base64url"),
    v: crypto.randomBytes(32).toString("base64url"),
    shop,
    uid,
    exp: Date.now() + 10 * 60_000,
  };
  const payload = Buffer.from(JSON.stringify(st)).toString("base64url");
  return { state: st, cookie: `${payload}.${sign(payload)}`, challenge: crypto.createHash("sha256").update(st.v).digest("base64url") };
}

export function readState(cookie: string | undefined): OAuthState | null {
  if (!cookie) return null;
  const [payload, sig] = cookie.split(".");
  if (!payload || !sig || !safeEqual(sig, sign(payload))) return null;
  try {
    const st = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as OAuthState;
    return st.exp > Date.now() ? st : null;
  } catch {
    return null;
  }
}
