import { listConversations } from "@/lib/data";
import { requireUser, route } from "@/lib/server/http";

export const GET = route(async (req: Request) => {
  const userId = await requireUser();
  const archived = new URL(req.url).searchParams.get("archived") === "1";
  return listConversations(userId, { archived });
});
