import { deleteSpace, updateSpace } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";
import { SpacePatch } from "../schema";

type Ctx = { params: Promise<{ id: string }> };
export const PATCH = route(async (req: Request, ctx: Ctx) =>
  updateSpace(await requireUser(), idParam((await ctx.params).id), await body(req, SpacePatch)));
export const DELETE = route(async (_req: Request, ctx: Ctx) => {
  await deleteSpace(await requireUser(), idParam((await ctx.params).id));
  return { ok: true };
});
