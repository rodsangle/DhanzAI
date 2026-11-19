import { z } from "zod";
import { restoreAssistantVersion } from "@/lib/data";
import { body, idParam, requireUser, route } from "@/lib/server/http";

// Restoring saves the old version as the newest one, so nothing is lost.
export const POST = route(async (req: Request, { params }: { params: Promise<{ id: string }> }) =>
  restoreAssistantVersion(await requireUser(), idParam((await params).id), (await body(req, z.object({ version: z.number().int().min(1) }))).version),
);
