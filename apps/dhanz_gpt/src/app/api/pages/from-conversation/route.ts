import { randomUUID } from "node:crypto";
import { z } from "zod";
import { checkSendRate, createPage, getConversationDetail, HttpError, recordUsage, usageToday } from "@/lib/data";
import { LIMITS } from "@/lib/data/types";
import { body, requireUser, route } from "@/lib/server/http";
import { draftPageFromChat } from "@/lib/ai/pages";
import { markdownToDoc } from "@/lib/server/page-doc";

export const maxDuration = 120;

const FromChat = z.object({ conversation_id: z.uuid(), space_id: z.uuid().optional() });

// F13: "Save as a page" from a chat. The assistant drafts the page from the visible thread, and it's saved as a
// page in your space (or the space given), linked back to the chat.
export const POST = route(async (req: Request) => {
  const userId = await requireUser();
  const { conversation_id, space_id } = await body(req, FromChat);
  const detail = await getConversationDetail(userId, conversation_id);
  if (detail.conversation.is_temporary) throw new HttpError(400, "Temporary chats can't be saved as pages.");
  // The thread you see: walk up from the current leaf.
  const byId = new Map(detail.messages.map((m) => [m.id, m]));
  const thread: typeof detail.messages = [];
  for (let m = byId.get(detail.conversation.current_leaf_id ?? ""); m; m = m.parent_id ? byId.get(m.parent_id) : undefined) thread.unshift(m);
  const transcript = thread
    .filter((m) => (m.role === "user" || m.role === "assistant") && m.status !== "error" && m.text.trim())
    .map((m) => ({ role: m.role as "user" | "assistant", text: m.text }));
  if (!transcript.some((m) => m.role === "assistant")) throw new HttpError(400, "There's no answer in this chat to save yet.");

  await checkSendRate(userId);
  if ((await usageToday(userId, "message")) >= LIMITS.messagesPerDay) {
    throw new HttpError(429, "You've reached today's message limit. It resets at midnight.");
  }
  let draft: { title: string; markdown: string };
  try {
    draft = await draftPageFromChat(transcript);
  } catch (e) {
    const status = (e as { status?: number }).status;
    throw new HttpError(status === 429 || status === 529 ? 503 : 502, "The page couldn't be drafted just now. Try again.");
  }
  await recordUsage(userId, "message", `page-draft-${randomUUID()}`, { model: process.env.PAGE_MODEL || "claude-sonnet-5-5" });
  const title = draft.title || detail.conversation.title || "From a chat";
  const page = await createPage(userId, { space_id, title, doc: markdownToDoc(draft.markdown), text: draft.markdown, source_conversation_id: conversation_id });
  return { id: page.id, title };
});
