import { z } from "zod";
import { addProjectFile, removeProjectFile } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

type Ctx = { params: Promise<{ id: string }> };

export const POST = route(async (req: Request, { params }: Ctx) => {
  const { file_id } = await body(req, z.object({ file_id: z.uuid() }));
  await addProjectFile(await requireUser(), idParam((await params).id), file_id);
  return { ok: true };
});

export const DELETE = route(async (req: Request, { params }: Ctx) => {
  const fileId = idParam(new URL(req.url).searchParams.get("file_id") ?? "");
  await removeProjectFile(await requireUser(), idParam((await params).id), fileId);
  return { ok: true };
});
