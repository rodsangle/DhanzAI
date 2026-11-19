import "server-only";
import { asService } from "@/lib/server/db";
import { HttpError } from "@/lib/data/errors";
import type { Importance } from "./types";

/**
 * Approval cards (action_approvals). An answer pauses on one; the person approves, always allows,
 * or declines. Only its owner can decide, once, within 24 hours.
 */
export async function createApproval(a: {
  user_id: string; connection_id: string; message_id: string; action: string; importance: Importance;
  payload_preview: unknown; tool_use_id: string; tool_name: string; state: unknown;
}) {
  const [row] = await asService((q) => q<{ id: string }[]>`
    insert into action_approvals (user_id, connection_id, message_id, action, importance, payload_preview, tool_use_id, tool_name, state)
    values (${a.user_id}, ${a.connection_id}, ${a.message_id}, ${a.action}, ${a.importance}, ${q.json(a.payload_preview as never)},
            ${a.tool_use_id}, ${a.tool_name}, ${q.json(a.state as never)})
    returning id`);
  return row.id;
}

export type TakenApproval = { id: string; message_id: string; connection_id: string; tool_name: string; state: unknown };

export async function takeApproval(userId: string, id: string, decision: "approve" | "always" | "deny"): Promise<TakenApproval> {
  return asService(async (q) => {
    const [a] = await q<(TakenApproval & { decision: string; expires_at: string })[]>`
      select id, message_id, connection_id, tool_name, state, decision, expires_at from action_approvals
      where id = ${id} and user_id = ${userId} for update`;
    if (!a) throw new HttpError(404, "That request doesn't exist.");
    if (a.decision !== "pending") throw new HttpError(409, "That request was already answered.");
    if (new Date(a.expires_at).getTime() < Date.now()) {
      await q`update action_approvals set decision = 'expired', updated_at = now() where id = ${id}`;
      throw new HttpError(410, "That request expired. Ask again in a new message.");
    }
    const d = decision === "approve" ? "approved" : decision === "always" ? "always" : "denied";
    await q`update action_approvals set decision = ${d}, decided_at = now(), updated_at = now() where id = ${id}`;
    return a;
  });
}

export async function finishApproval(id: string, summary: string) {
  await asService((q) => q`update action_approvals set result_summary = ${summary.slice(0, 500)}, updated_at = now() where id = ${id}`);
}
