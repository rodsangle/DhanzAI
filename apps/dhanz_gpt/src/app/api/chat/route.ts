import { after } from "next/server";
import { z } from "zod";
import {
  attachFiles, checkAttachments, checkSendRate, createConversation, getConversationDetail, HttpError, insertUserMessage, messageRow, patchMessage,
  updateConversation, usageToday,
} from "@/lib/data";
import { DEFAULT_MODEL, LIMITS, MODELS, type ContentBlock } from "@/lib/data/types";
import { sseFor, startAssistantReply } from "@/lib/ai/generation";
import { body, requireUser, route } from "@/lib/server/http";

const ChatBody = z.object({
  conversation_id: z.uuid().optional(),
  project_id: z.uuid().nullish(),
  assistant_id: z.uuid().nullish(),
  /** Omit to append to the current branch. `null` = new root (editing the first message). */
  parent_id: z.uuid().nullish(),
  text: z.string().max(100_000, "That message is too long. Attach it as a file instead."),
  file_ids: z.array(z.uuid()).max(LIMITS.attachmentsPerMessage).default([]),
  model: z.string().max(100).optional(),
  temporary: z.boolean().optional(),
  tools: z.object({ image: z.boolean().optional(), search: z.boolean().optional() }).optional(),
});

export const POST = route(async (req: Request) => {
  const userId = await requireUser();
  // Whether parent_id was sent at all matters (absent = append, null = new root), so peek at the raw body.
  const raw = (await req.clone().json().catch(() => ({}))) as Record<string, unknown>;
  const b = await body(req, ChatBody);
  const text = b.text.trim();
  if (!text && b.file_ids.length === 0) throw new HttpError(400, "Type a message or attach a file.");
  await checkSendRate(userId);
  if ((await usageToday(userId, "message")) >= LIMITS.messagesPerDay) {
    throw new HttpError(429, "You've reached today's message limit. It resets at midnight.");
  }
  if (b.tools?.image && (await usageToday(userId, "image")) >= LIMITS.imagesPerDay) {
    throw new HttpError(429, "You've reached today's image limit. It resets at midnight.");
  }
  await checkAttachments(userId, b.file_ids);
  const model = MODELS.some((m) => m.id === b.model) ? b.model! : DEFAULT_MODEL;

  let conversation = b.conversation_id
    ? (await getConversationDetail(userId, b.conversation_id)).conversation
    : await createConversation(userId, { project_id: b.project_id ?? null, assistant_id: b.assistant_id ?? null, model, is_temporary: b.temporary });
  if (conversation.user_id !== userId) throw new HttpError(403, "Only the person who started this chat can add to it.");
  if (conversation.model !== model) conversation = await updateConversation(userId, conversation.id, { model });

  // parent_id absent → reply to the latest message (checked under a lock); explicit null → new root.
  let parent: "leaf" | string | null;
  if (!("parent_id" in raw)) parent = "leaf";
  else if (b.parent_id === null || b.parent_id === undefined) parent = null;
  else {
    const p = await messageRow(b.parent_id);
    if (!p || p.conversation_id !== conversation.id) throw new HttpError(400, "That message isn't part of this chat.");
    parent = p.id;
  }
  const user = await insertUserMessage({ conversation_id: conversation.id, user_id: userId, text, parent });
  if (b.file_ids.length) {
    const files = await attachFiles(userId, user.id, b.file_ids);
    const content: ContentBlock[] = [
      ...files.map((f): ContentBlock => (f.mime.startsWith("image/") ? { type: "image", file_id: f.id, alt: f.name } : { type: "file_ref", file_id: f.id, name: f.name, mime: f.mime })),
      { type: "text", text },
    ];
    await patchMessage(user.id, { content });
  }
  const { assistant, done } = await startAssistantReply(userId, conversation, user, { forceImage: !!b.tools?.image, forceSearch: !!b.tools?.search && !b.tools?.image });
  after(done);
  return sseFor(assistant, [
    { type: "meta", conversation_id: conversation.id, user_message_id: user.id, assistant_message_id: assistant.id, title: conversation.title },
  ]);
});
