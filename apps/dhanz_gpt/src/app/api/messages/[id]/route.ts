import { z } from "zod";
import { getMessage, setFeedback } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

type Ctx = { params: Promise<{ id: string }> };

export const GET = route(async (_req: Request, { params }: Ctx) => getMessage(await requireUser(), idParam((await params).id)));

export const PATCH = route(async (req: Request, { params }: Ctx) => {
  const userId = await requireUser();
  const { feedback } = await body(req, z.object({ feedback: z.union([z.literal(1), z.literal(-1), z.null()]) }));
  return setFeedback(userId, idParam((await params).id), feedback);
});
