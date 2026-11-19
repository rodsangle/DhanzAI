import { createSpace, listSpaces } from "@/lib/data";
import { body, requireUser, route } from "@/lib/server/http";
import { SpaceBody } from "./schema";

// S12: spaces you can see and the page tree inside them.
export const GET = route(async () => listSpaces(await requireUser()));
export const POST = route(async (req: Request) => createSpace(await requireUser(), await body(req, SpaceBody)));
