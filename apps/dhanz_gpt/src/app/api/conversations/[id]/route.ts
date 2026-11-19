import { z } from "zod";
import { deleteConversation, getConversationDetail, updateConversation } from "@/lib/data";
import { MODELS } from "@/lib/data/types";
import { body, idParam, requireUser, route } from "@/lib/server/http";

type Ctx = { params: Promise<{ id: string }> };
const Patch = z.object({
  title: z.string().max(500).optional(),
  archived: z.boolean().optional(),
  project_id: z.uuid().nullable().optional(),
  current_leaf_id: z.uuid().optional(),
  model: z.enum(MODELS.map((m) => m.id) as [string, ...string[]]).optional(),
});

export const GET = route(async (_req: Request, { params }: Ctx) => getConversationDetail(await requireUser(), idParam((await params).id)));

export const PATCH = route(async (req: Request, { params }: Ctx) => {
  const userId = await requireUser();
  return updateConversation(userId, idParam((await params).id), await body(req, Patch));
});

export const DELETE = route(async (_req: Request, { params }: Ctx) => {
  await deleteConversation(await requireUser(), idParam((await params).id));
  return { ok: true };
});
