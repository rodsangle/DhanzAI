import { deleteAssistant, getAssistant, updateAssistant } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";
import { AssistantBody } from "../schema";

type P = { params: Promise<{ id: string }> };

export const GET = route(async (_req: Request, { params }: P) => getAssistant(await requireUser(), idParam((await params).id)));
export const PUT = route(async (req: Request, { params }: P) =>
  updateAssistant(await requireUser(), idParam((await params).id), await body(req, AssistantBody)),
);
export const DELETE = route(async (_req: Request, { params }: P) => {
  await deleteAssistant(await requireUser(), idParam((await params).id));
  return { ok: true };
});
