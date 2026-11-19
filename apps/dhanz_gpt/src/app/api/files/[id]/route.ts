import { z } from "zod";
import { trashFile } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

export const PATCH = route(async (req: Request, { params }: { params: Promise<{ id: string }> }) => {
  const { trashed } = await body(req, z.object({ trashed: z.boolean() }));
  return trashFile(await requireUser(), idParam((await params).id), trashed);
});
