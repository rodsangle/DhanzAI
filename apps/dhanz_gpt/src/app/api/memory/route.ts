import { z } from "zod";
import { deleteMemory, getMemory, MEMORY_MAX, saveMemory } from "@/lib/data";
import { body, requireUser, route } from "@/lib/server/http";

const Put = z.object({ body: z.string().max(MEMORY_MAX) });

// The signed-in person's memory summary: view, correct, or delete it (which also turns memory off).
export const GET = route(async () => getMemory(await requireUser()));
export const PUT = route(async (req: Request) => saveMemory(await requireUser(), (await body(req, Put)).body));
export const DELETE = route(async () => {
  await deleteMemory(await requireUser());
  return { ok: true };
});
