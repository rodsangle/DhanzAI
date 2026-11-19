import { z } from "zod";
import { deleteProject, getProjectDetail, updateProject } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

type Ctx = { params: Promise<{ id: string }> };
const Patch = z.object({
  name: z.string().max(500).optional(),
  instructions: z.string().max(20000).optional(),
  memory_mode: z.enum(["default", "project_only"]).optional(),
});

export const GET = route(async (_req: Request, { params }: Ctx) => getProjectDetail(await requireUser(), idParam((await params).id)));

export const PATCH = route(async (req: Request, { params }: Ctx) => {
  const userId = await requireUser();
  return updateProject(userId, idParam((await params).id), await body(req, Patch));
});

export const DELETE = route(async (_req: Request, { params }: Ctx) => {
  await deleteProject(await requireUser(), idParam((await params).id));
  return { ok: true };
});
