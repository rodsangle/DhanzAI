import { storageUsage } from "@/lib/data";
import { requireUser, route } from "@/lib/server/http";

/** GET /api/files/usage → { used, quota } in bytes, for the Library's storage bar. */
export const GET = route(async () => storageUsage(await requireUser()));
