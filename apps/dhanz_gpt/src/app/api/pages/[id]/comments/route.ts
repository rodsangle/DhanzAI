import { z } from "zod";
import { addComment, listComments } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

type Ctx = { params: Promise<{ id: string }> };
const NewComment = z.object({ body: z.string().max(12_000), quote: z.string().max(5000).nullable().optional(), parent_comment_id: z.uuid().nullable().optional() });

export const GET = route(async (_req: Request, ctx: Ctx) => listComments(await requireUser(), idParam((await ctx.params).id)));
export const POST = route(async (req: Request, ctx: Ctx) => addComment(await requireUser(), idParam((await ctx.params).id), await body(req, NewComment)));
