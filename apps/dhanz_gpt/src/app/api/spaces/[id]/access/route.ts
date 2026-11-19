import { grantAccess, listAccess } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";
import { Grant } from "../../schema";

type Ctx = { params: Promise<{ id: string }> };
export const GET = route(async (_req: Request, ctx: Ctx) => listAccess(await requireUser(), { space_id: idParam((await ctx.params).id) }));
export const POST = route(async (req: Request, ctx: Ctx) =>
  grantAccess(await requireUser(), { space_id: idParam((await ctx.params).id) }, await body(req, Grant)));
