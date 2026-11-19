import "server-only";

export type ProviderId = "google_drive" | "slack" | "shopify";
export type Importance = "read" | "change" | "important";
export type PermissionLevel = "always_ask" | "any_changes" | "important" | "never_ask";

export type TokenSet = { access_token: string; refresh_token?: string | null; expires_in?: number | null; scopes: string[] };
export type Account = { id: string; label: string };

export interface AppTool {
  /** The name Claude calls, e.g. drive_search. */
  name: string;
  description: string;
  input_schema: { type: "object"; properties: Record<string, unknown>; required?: string[] };
  importance: Importance;
  /** A line for the chat: "Searched Google Drive for “lookbook”". */
  describe(input: Record<string, unknown>): string;
  /** What the approval card shows. */
  preview(input: Record<string, unknown>): { label: string; value: string }[];
  /** Runs the action. Returns text for the model (JSON is fine) and a short line for the person. */
  run(c: { token: string; shop: string | null }, input: Record<string, unknown>): Promise<{ result: string; summary: string }>;
}

export interface AppProvider {
  id: ProviderId;
  name: string;
  /** How people refer to it after @. The first is what the composer inserts. */
  mentions: string[];
  description: string;
  /** What it can do, in plain words, for the Apps page. */
  can: string[];
  needsShop?: boolean;
  configured(): boolean;
  authorizeUrl(o: { state: string; redirectUri: string; codeChallenge: string; shop: string | null }): string;
  exchange(o: { code: string; redirectUri: string; codeVerifier: string; shop: string | null; query: URLSearchParams }): Promise<{ tokens: TokenSet; account: Account }>;
  refresh?(refreshToken: string): Promise<TokenSet>;
  revoke?(token: string, shop: string | null): Promise<void>;
  tools: AppTool[];
}

export class AppError extends Error {
  constructor(message: string, public status = 502) {
    super(message);
  }
}

/** Test-only: every provider's API at one stand-in host (tests/mock-api/server.mjs). Never set in production. */
export const testBase = () => process.env.APPS_TEST_BASE?.replace(/\/+$/, "") || null;

export async function call(url: string, init: RequestInit & { what: string }) {
  let res: Response;
  try {
    res = await fetch(url, { ...init, signal: AbortSignal.timeout(20_000) });
  } catch {
    throw new AppError(`${init.what} didn't respond. Try again in a moment.`);
  }
  if (res.status === 401 || res.status === 403) throw new AppError(`${init.what} said the connection isn't allowed anymore. Reconnect it in Apps.`, 401);
  if (res.status === 429) throw new AppError(`${init.what} is rate limiting requests. Try again in a minute.`, 429);
  if (!res.ok) throw new AppError(`${init.what} returned an error (${res.status}).`);
  return res;
}

export const str = (v: unknown, max = 500) => (typeof v === "string" ? v.slice(0, max) : "");
