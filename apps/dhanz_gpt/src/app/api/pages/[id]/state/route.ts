import { z } from "zod";
import { leavePage, pageState } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

type Ctx = { params: Promise<{ id: string }> };
// Polled every few seconds by an open page: its version (for live updates) and who else is here.
export const GET = route(async (_req: Request, ctx: Ctx) => pageState(await requireUser(), idParam((await ctx.params).id)));
// Heartbeat: "I'm here" (and whether I'm typing).
export const POST = route(async (req: Request, ctx: Ctx) =>
  pageState(await requireUser(), idParam((await ctx.params).id), await body(req, z.object({ editing: z.boolean() }))));
export const DELETE = route(async (_req: Request, ctx: Ctx) => {
  await leavePage(await requireUser(), idParam((await ctx.params).id));
  return { ok: true };
});
