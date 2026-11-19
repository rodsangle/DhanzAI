import { revokeSession } from "@/lib/server/sessions";
import { idParam, requireUser, route } from "@/lib/server/http";

// S28: sign one device out.
export const DELETE = route(async (_req: Request, ctx: { params: Promise<{ id: string }> }) => {
  const userId = await requireUser();
  await revokeSession(userId, idParam((await ctx.params).id));
  return { ok: true };
});
