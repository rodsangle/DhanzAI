import { markRunsSeen } from "@/lib/data";
import { requireUser, route } from "@/lib/server/http";

// Opening Scheduled clears the unread count.
export const POST = route(async () => {
  await markRunsSeen(await requireUser());
  return { ok: true };
});
