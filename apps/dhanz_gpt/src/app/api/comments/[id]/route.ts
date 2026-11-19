import { z } from "zod";
import { deleteComment, updateComment } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

type Ctx = { params: Promise<{ id: string }> };
export const PATCH = route(async (req: Request, ctx: Ctx) =>
  updateComment(await requireUser(), idParam((await ctx.params).id), await body(req, z.object({ body: z.string().max(12_000).optional(), resolved: z.boolean().optional() }))));
export const DELETE = route(async (_req: Request, ctx: Ctx) => {
  await deleteComment(await requireUser(), idParam((await ctx.params).id));
  return { ok: true };
});
