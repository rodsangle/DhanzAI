import { requestStopFlag } from "@/lib/data";
import { stopLocal } from "@/lib/ai/generation";
import { idParam, requireUser, route } from "@/lib/server/http";

// Sets the stop flag in the database (seen by whichever instance is generating) and aborts locally if it's here.
export const POST = route(async (_req: Request, { params }: { params: Promise<{ id: string }> }) => {
  const userId = await requireUser();
  const id = idParam((await params).id);
  const stopping = await requestStopFlag(userId, id);
  stopLocal(id);
  return { stopping };
});
