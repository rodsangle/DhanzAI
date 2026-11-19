import { randomUUID } from "node:crypto";
import { z } from "zod";
import { checkSendRate, getPage, HttpError, recordUsage, usageToday } from "@/lib/data";
import { LIMITS } from "@/lib/data/types";
import { body, idParam, requireUser, route } from "@/lib/server/http";
import { editPage } from "@/lib/ai/pages";
import { markdownToHtml } from "@/lib/server/markdown-html";

export const maxDuration = 120;

const Ask = z.object({ instruction: z.string().min(1).max(4000), selection: z.string().max(40_000).nullable().optional() });

// S12 "Ask AI" on a page: a proposed rewrite of the selection (or the whole page). Nothing is saved here;
// the editor shows the proposal and applies it only if the person accepts.
export const POST = route(async (req: Request, ctx: { params: Promise<{ id: string }> }) => {
  const userId = await requireUser();
  const id = idParam((await ctx.params).id);
  const { instruction, selection } = await body(req, Ask);
  const detail = await getPage(userId, id);
  if (detail.level !== "edit") throw new HttpError(403, "You can view this page but not edit it.");
  await checkSendRate(userId);
  if ((await usageToday(userId, "message")) >= LIMITS.messagesPerDay) {
    throw new HttpError(429, "You've reached today's message limit. It resets at midnight.");
  }
  let markdown: string;
  try {
    ({ markdown } = await editPage({ title: detail.page.title, text: detail.page.text, selection: selection?.trim() || undefined, instruction: instruction.trim() }));
  } catch (e) {
    const status = (e as { status?: number }).status;
    throw new HttpError(status === 429 || status === 529 ? 503 : 502, "The assistant couldn't edit the page just now. Try again.");
  }
  await recordUsage(userId, "message", `page-ai-${randomUUID()}`, { model: process.env.PAGE_MODEL || "claude-sonnet-5-5" });
  if (!markdown) throw new HttpError(502, "The assistant returned nothing. Try rewording the request.");
  return { markdown, html: markdownToHtml(markdown), scope: selection?.trim() ? "selection" : "page", base_version: detail.page.version };
});
