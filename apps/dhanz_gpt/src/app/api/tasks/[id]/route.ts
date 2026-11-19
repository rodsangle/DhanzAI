import { deleteTask, updateTask } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";
import { TaskBody } from "../schema";

type P = { params: Promise<{ id: string }> };

export const PUT = route(async (req: Request, { params }: P) => updateTask(await requireUser(), idParam((await params).id), await body(req, TaskBody)));
export const DELETE = route(async (_req: Request, { params }: P) => {
  await deleteTask(await requireUser(), idParam((await params).id));
  return { ok: true };
});
