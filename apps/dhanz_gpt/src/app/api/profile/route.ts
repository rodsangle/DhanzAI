import { z } from "zod";
import { updateProfile } from "@/lib/data";
import { body, requireUser, route } from "@/lib/server/http";

const Patch = z.object({
  theme: z.enum(["system", "light", "dark"]).optional(),
  locale: z.enum(["en", "es"]).optional(),
  name: z.string().min(1).max(100).optional(),
});

export const PATCH = route(async (req: Request) => updateProfile(await requireUser(), await body(req, Patch)));
