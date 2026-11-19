import { z } from "zod";
import { createProject, listProjects } from "@/lib/data";
import { body, requireUser, route } from "@/lib/server/http";

export const GET = route(async () => listProjects(await requireUser()));

export const POST = route(async (req: Request) => {
  const userId = await requireUser();
  return createProject(userId, await body(req, z.object({ name: z.string().max(500), instructions: z.string().max(20000).optional() })));
});
