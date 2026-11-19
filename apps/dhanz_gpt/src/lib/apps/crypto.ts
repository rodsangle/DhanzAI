import "server-only";
import crypto from "node:crypto";

/**
 * App tokens are encrypted at rest with AES-256-GCM. APP_TOKEN_KEY is 32 random bytes, base64
 * (`openssl rand -base64 32`). Rotating it means everyone reconnects their apps.
 * The same key signs the short-lived OAuth state cookie.
 */
function key() {
  const k = Buffer.from(process.env.APP_TOKEN_KEY ?? "", "base64");
  if (k.length !== 32) throw new Error("APP_TOKEN_KEY must be 32 bytes, base64");
  return k;
}
export const appKeyConfigured = () => Buffer.from(process.env.APP_TOKEN_KEY ?? "", "base64").length === 32;

export function seal(plain: string): Buffer {
  const iv = crypto.randomBytes(12);
  const c = crypto.createCipheriv("aes-256-gcm", key(), iv);
  const body = Buffer.concat([c.update(plain, "utf8"), c.final()]);
  return Buffer.concat([iv, c.getAuthTag(), body]);
}

export function open(sealed: Buffer): string {
  const d = crypto.createDecipheriv("aes-256-gcm", key(), sealed.subarray(0, 12));
  d.setAuthTag(sealed.subarray(12, 28));
  return Buffer.concat([d.update(sealed.subarray(28)), d.final()]).toString("utf8");
}

export function sign(value: string) {
  return crypto.createHmac("sha256", key()).update(value).digest("base64url");
}

export function safeEqual(a: string, b: string) {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}
