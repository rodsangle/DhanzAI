import { z } from "zod";
import { deletePage, getPage, savePage } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

type Ctx = { params: Promise<{ id: string }> };
const Save = z.object({
  title: z.string().max(400).optional(),
  doc: z.looseObject({ type: z.literal("doc") }).optional(),
  text: z.string().max(600_000).optional(),
  base_version: z.int().positive().optional(),
  force: z.boolean().optional(),
});

export const GET = route(async (_req: Request, ctx: Ctx) => getPage(await requireUser(), idParam((await ctx.params).id)));
export const PATCH = route(async (req: Request, ctx: Ctx) => savePage(await requireUser(), idParam((await ctx.params).id), await body(req, Save)));
export const DELETE = route(async (_req: Request, ctx: Ctx) => deletePage(await requireUser(), idParam((await ctx.params).id)));
