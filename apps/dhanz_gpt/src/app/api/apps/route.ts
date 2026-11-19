import { listApps } from "@/lib/apps/store";
import { requireUser, route } from "@/lib/server/http";

// S20: the apps you can connect, and your connections.
export const GET = route(async () => listApps(await requireUser()));
