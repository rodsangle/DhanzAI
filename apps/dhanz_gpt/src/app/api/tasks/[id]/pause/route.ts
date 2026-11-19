import { z } from "zod";
import { setTaskPaused } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

export const POST = route(async (req: Request, { params }: { params: Promise<{ id: string }> }) =>
  setTaskPaused(await requireUser(), idParam((await params).id), (await body(req, z.object({ paused: z.boolean() }))).paused),
);
