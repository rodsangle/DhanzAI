import { revokeAccess } from "@/lib/data";
import { idParam, requireUser, route } from "@/lib/server/http";

export const DELETE = route(async (_req: Request, ctx: { params: Promise<{ id: string }> }) => {
  await revokeAccess(await requireUser(), idParam((await ctx.params).id));
  return { ok: true };
});
