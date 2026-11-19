import { z } from "zod";
import { getPersonalization, savePersonalization } from "@/lib/data";
import { body, requireUser, route } from "@/lib/server/http";

const Patch = z.object({
  about_you: z.string().max(3000).optional(),
  response_style: z.string().max(3000).optional(),
  personality: z.string().max(40).optional(),
  memory_enabled: z.boolean().optional(),
  reference_chat_history: z.boolean().optional(),
});

export const GET = route(async () => getPersonalization(await requireUser()));
export const PUT = route(async (req: Request) => savePersonalization(await requireUser(), await body(req, Patch)));
