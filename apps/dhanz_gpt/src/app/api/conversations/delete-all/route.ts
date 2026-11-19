import { z } from "zod";
import { deleteAllConversations } from "@/lib/data";
import { body, requireUser, route } from "@/lib/server/http";

const Body = z.object({ confirm: z.literal(true) });

// Settings → Data controls → Delete all chats (the dialog sends confirm: true).
export const POST = route(async (req: Request) => {
  const userId = await requireUser();
  await body(req, Body);
  return { deleted: await deleteAllConversations(userId) };
});
