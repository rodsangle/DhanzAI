import { z } from "zod";
import { createUpload, listFiles } from "@/lib/data";
import { body, requireUser, route } from "@/lib/server/http";

export const GET = route(async (req: Request) => {
  const trashed = new URL(req.url).searchParams.get("trashed") === "1";
  return listFiles(await requireUser(), { trashed });
});

// Step 1 of an upload: validate, reserve the row, return where to send the bytes.
export const POST = route(async (req: Request) => {
  const userId = await requireUser();
  const b = await body(req, z.object({ name: z.string().min(1).max(1000), mime: z.string().max(200), bytes: z.number().int().positive(), temporary: z.boolean().optional() }));
  return createUpload(userId, b);
});
