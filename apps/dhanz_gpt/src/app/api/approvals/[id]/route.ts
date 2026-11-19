import { after } from "next/server";
import { z } from "zod";
import { resumeAfterApproval, sseFor } from "@/lib/ai/generation";
import { body, idParam, requireUser, route } from "@/lib/server/http";

// The person's answer on an approval card. The paused answer continues, streamed back here.
export const POST = route(async (req: Request, { params }: { params: Promise<{ id: string }> }) => {
  const userId = await requireUser();
  const { decision } = await body(req, z.object({ decision: z.enum(["approve", "always", "deny"]) }));
  const { assistant, done } = await resumeAfterApproval(userId, idParam((await params).id), decision);
  after(done);
  return sseFor(assistant, [{ type: "meta", conversation_id: assistant.conversation_id, assistant_message_id: assistant.id }]);
});
