import { listSessions } from "@/lib/server/sessions";
import { requireUser, route } from "@/lib/server/http";

// S28: devices where you're signed in.
export const GET = route(async () => listSessions(await requireUser()));
