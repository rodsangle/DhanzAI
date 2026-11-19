import "server-only";
import postgres, { type TransactionSql } from "postgres";
import { HttpError } from "@/lib/data/errors";

/**
 * One Postgres pool for the app.
 *
 * - `asUser(uid, fn)` runs `fn` in a transaction as the `authenticated` role with the user's id in the
 *   JWT-claim settings Supabase's `auth.uid()` reads. Every row-level-security policy in schema.sql applies,
 *   exactly as it would for a Supabase client holding that user's token.
 * - `asService(fn)` runs as the connecting role (bypasses RLS) for system writes: assistant messages,
 *   usage, file rows after upload, jobs. Only server code can reach it.
 *
 * On Supabase use the pooled connection string (Supavisor, transaction mode). `prepare: false` is required there.
 */

const g = globalThis as unknown as { __dhanzGptSql?: postgres.Sql };

function pool() {
  if (!g.__dhanzGptSql) {
    const url = process.env.DATABASE_URL;
    if (!url) throw new Error("DATABASE_URL is not set. See .env.example.");
    g.__dhanzGptSql = postgres(url, {
      max: Number(process.env.DATABASE_POOL_MAX ?? 5),
      prepare: false,
      idle_timeout: 20,
      onnotice: false,
      transform: {
        // timestamptz → ISO strings, so rows serialise the same everywhere.
        value: { from: (v: unknown) => (v instanceof Date ? v.toISOString() : v) },
      },
    });
  }
  return g.__dhanzGptSql;
}

export type Tx = TransactionSql;

function mapError(e: unknown): never {
  const err = e as { code?: string; message?: string; hint?: string };
  if (e instanceof HttpError) throw e;
  switch (err.code) {
    case "42501": // RLS / privilege
      throw new HttpError(403, "You don't have access to this.");
    case "22P02": // bad uuid in a URL
      throw new HttpError(404, "Not found");
    case "23505":
      throw new HttpError(409, "That already exists.");
    case "23503":
      throw new HttpError(400, "That refers to something that no longer exists.");
    case "23514":
      throw new HttpError(400, "That value isn't allowed.");
    case "P0001":
      throw new HttpError(400, err.message ?? "That isn't allowed.");
    default:
      throw e;
  }
}

export async function asUser<T>(userId: string, fn: (q: Tx) => Promise<T>): Promise<T> {
  try {
    return (await pool().begin(async (q) => {
      await q`select set_config('request.jwt.claims', ${JSON.stringify({ sub: userId, role: "authenticated" })}, true),
                     set_config('request.jwt.claim.sub', ${userId}, true)`;
      await q`set local role authenticated`;
      return fn(q);
    })) as T;
  } catch (e) {
    mapError(e);
  }
}

export async function asService<T>(fn: (q: Tx) => Promise<T>): Promise<T> {
  try {
    return (await pool().begin((q) => fn(q))) as T;
  } catch (e) {
    mapError(e);
  }
}

export async function closePool() {
  await g.__dhanzGptSql?.end();
  g.__dhanzGptSql = undefined;
}
