import { z } from "zod";
import { createPage } from "@/lib/data";
import { body, requireUser, route } from "@/lib/server/http";

const NewPage = z.object({
  space_id: z.uuid().optional(),
  parent_page_id: z.uuid().nullable().optional(),
  title: z.string().max(400).optional(),
});

export const POST = route(async (req: Request) => createPage(await requireUser(), await body(req, NewPage)));
