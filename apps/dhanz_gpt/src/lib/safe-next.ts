/**
 * Where to send someone after sign-in. Only same-site paths are allowed.
 * Browsers treat "\" like "/" and drop tabs and newlines inside URLs, so "/\evil.example" or
 * "/<tab>/evil.example" would become "//evil.example", a link to another site. Rather than list
 * tricks, resolve the value against a dummy origin and accept it only if it stays on that origin.
 */
const BASE = "https://same-site.invalid";

export function safeNext(next: string | null | undefined, fallback = "/") {
  if (!next || !next.startsWith("/") || /[\\\u0000-\u001f\u007f]/.test(next)) return fallback;
  try {
    const url = new URL(next, BASE);
    if (url.origin !== BASE) return fallback;
    return url.pathname + url.search + url.hash;
  } catch {
    return fallback;
  }
}
