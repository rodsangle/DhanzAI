import postgres from "postgres";
import { randomUUID } from "node:crypto";

// Test-only access to the local database, for setting up states the UI can't create quickly.
export const sql = postgres(process.env.DATABASE_URL ?? "postgres://postgres@localhost:5499/rodrech", { max: 2, onnotice: () => {} });

/** A throwaway RODRECH member (the sign-up trigger creates profile + membership). */
export async function tempUser(prefix = "test") {
  const email = `${prefix}-${randomUUID().slice(0, 8)}@rodrech.com`;
  const [u] = await sql`insert into auth.users (email, raw_user_meta_data) values (${email}, ${sql.json({ full_name: `Test ${prefix}` })}) returning id`;
  return { id: u.id as string, email };
}

export async function fillDailyUsage(userId: string, metric: "message" | "image", n: number) {
  await sql`
    insert into usage_events (workspace_id, user_id, metric, idempotency_key)
    select m.workspace_id, ${userId}, ${metric}, 'seed-' || ${userId} || '-' || g
    from memberships m, generate_series(1, ${n}) g where m.user_id = ${userId}`;
}

export async function countUserMessages(conversationId: string) {
  const [r] = await sql`select count(*)::int as n from messages where conversation_id = ${conversationId} and role = 'user'`;
  return r.n as number;
}

/** Runs a query as a signed-in user, so row level security applies (mirrors asUser in the app). */
export async function asUserCount(userId: string, query: (q: postgres.TransactionSql) => Promise<{ n: number }[]>) {
  return sql.begin(async (q) => {
    await q`select set_config('request.jwt.claims', ${JSON.stringify({ sub: userId, role: "authenticated" })}, true),
                   set_config('request.jwt.claim.sub', ${userId}, true)`;
    await q`set local role authenticated`;
    const [r] = await query(q);
    return r.n;
  }) as Promise<number>;
}

export async function userIdFor(email: string) {
  const [r] = await sql`select id from profiles where email = ${email}`;
  return r.id as string;
}
