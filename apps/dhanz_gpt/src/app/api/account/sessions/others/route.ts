import { revokeOtherSessions } from "@/lib/server/sessions";
import { requireUser, route } from "@/lib/server/http";

// S28: keep this device, sign out the rest.
export const POST = route(async () => revokeOtherSessions(await requireUser()));
