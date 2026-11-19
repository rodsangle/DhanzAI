import { createAssistant, listAssistants } from "@/lib/data";
import { body, requireUser, route } from "@/lib/server/http";
import { AssistantBody } from "./schema";


// S21: your assistants and the team's. S22: create one.
export const GET = route(async () => listAssistants(await requireUser()));
export const POST = route(async (req: Request) => createAssistant(await requireUser(), await body(req, AssistantBody)));
