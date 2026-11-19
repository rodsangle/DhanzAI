import { z } from "zod";
import { setProjectMember } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

export const POST = route(async (req: Request, { params }: { params: Promise<{ id: string }> }) => {
  const { user_id, role } = await body(req, z.object({ user_id: z.uuid(), role: z.enum(["viewer", "editor"]).nullable() }));
  await setProjectMember(await requireUser(), idParam((await params).id), user_id, role);
  return { ok: true };
});
