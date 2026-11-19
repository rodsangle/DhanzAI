import { after } from "next/server";
import { z } from "zod";
import { getOwnMessage, HttpError, messageOptions, messageRow, updateConversation } from "@/lib/data";
import { MODELS } from "@/lib/data/types";
import { replyOptions, sseFor, startAssistantReply } from "@/lib/ai/generation";
import { idParam, requireUser, route } from "@/lib/server/http";

const Body = z.object({ model: z.string().max(100).optional() });

// Adds a new assistant sibling under the same user message (a new branch), optionally with another model.
export const POST = route(async (req: Request, { params }: { params: Promise<{ id: string }> }) => {
  const userId = await requireUser();
  const { message, conversation } = await getOwnMessage(userId, idParam((await params).id));
  if (message.role !== "assistant" || !message.parent_id) throw new HttpError(400, "Only answers can be regenerated.");
  if (message.status === "streaming") throw new HttpError(409, "Stop the current answer first.");
  const parsed = Body.safeParse(await req.json().catch(() => ({})));
  const model = parsed.success ? parsed.data.model : undefined;
  const parent = await messageRow(message.parent_id);
  if (!parent) throw new HttpError(404, "Not found");
  const conv = model && MODELS.some((m) => m.id === model) ? await updateConversation(userId, conversation.id, { model }) : conversation;
  // Retry asks the same way the person did: image mode and shape, web search, think longer.
  const { assistant, done } = await startAssistantReply(userId, conv, parent, replyOptions(await messageOptions(parent.id)));
  after(done);
  return sseFor(assistant, [{ type: "meta", conversation_id: conv.id, assistant_message_id: assistant.id }]);
});
