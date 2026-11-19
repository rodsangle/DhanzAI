import { z } from "zod";
import { disconnect, setPermission } from "@/lib/apps/store";
import { body, idParam, requireUser, route } from "@/lib/server/http";

type P = { params: Promise<{ id: string }> };

export const PATCH = route(async (req: Request, { params }: P) => {
  const { permission_level } = await body(req, z.object({ permission_level: z.enum(["always_ask", "any_changes", "important", "never_ask"]) }));
  await setPermission(await requireUser(), idParam((await params).id), permission_level);
  return { ok: true };
});
export const DELETE = route(async (_req: Request, { params }: P) => {
  await disconnect(await requireUser(), idParam((await params).id));
  return { ok: true };
});
