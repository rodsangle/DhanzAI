import { createTask, listTasks } from "@/lib/data";
import { body, requireUser, route } from "@/lib/server/http";
import { TaskBody } from "./schema";

// S18: the person's scheduled tasks with their recent runs; create one.
export const GET = route(async () => listTasks(await requireUser()));
export const POST = route(async (req: Request) => createTask(await requireUser(), await body(req, TaskBody)));
