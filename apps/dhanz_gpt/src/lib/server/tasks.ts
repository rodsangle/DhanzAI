import "server-only";
import { createConversation, finishRun, getProfile, insertUserMessage, messageRow, type DueRun } from "@/lib/data";
import { DEFAULT_MODEL } from "@/lib/data/types";
import { startAssistantReply } from "@/lib/ai/generation";
import { appUrl, layout, sendEmail } from "./email";
import { pushTo } from "./push";

/**
 * Runs one claimed task run: a new chat titled after the task, the task's instructions as the
 * message, the usual answer (memory, web search and all), then the notifications the task asks for.
 */
export async function executeRun(run: DueRun) {
  let conversationId: string | null = null;
  try {
    const conversation = await createConversation(run.user_id, { model: run.model ?? DEFAULT_MODEL, kind: "task_run", title: run.title.slice(0, 200) });
    conversationId = conversation.id;
    const user = await insertUserMessage({ conversation_id: conversation.id, user_id: run.user_id, text: run.prompt, parent: null });
    const { assistant, done } = await startAssistantReply(run.user_id, conversation, user);
    await done;
    const answer = await messageRow(assistant.id);
    const ok = answer?.status === "complete";
    const summary = ok ? plain(answer.text) : answer?.error ?? "The answer didn't finish.";
    await finishRun(run.run_id, { status: ok ? "succeeded" : "failed", conversation_id: conversationId, summary });
    await notify(run, conversationId, ok, summary);
  } catch (e) {
    console.error("[task]", (e as Error).message);
    await finishRun(run.run_id, { status: "failed", conversation_id: conversationId, summary: "The task couldn't run. It will try again at its next time." });
    await notify(run, conversationId, false, "The task couldn't run. It will try again at its next time.").catch(() => {});
  }
}

/** Markdown to a short plain preview for notifications. */
function plain(md: string) {
  return md
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/\[\[(\d+)\]\]\([^)]*\)/g, "")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[#*_>`|]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 300);
}

async function notify(run: DueRun, conversationId: string | null, ok: boolean, summary: string) {
  const url = conversationId ? `/c/${conversationId}` : "/scheduled";
  const heading = ok ? run.title : `${run.title} didn't finish`;
  if (run.notify.includes("push")) await pushTo(run.user_id, { title: heading, body: summary.slice(0, 160), url, tag: `task-${run.task_id}` });
  if (run.notify.includes("email")) {
    const profile = await getProfile(run.user_id);
    if (profile?.email)
      await sendEmail({
        to: profile.email,
        subject: ok ? `Scheduled: ${run.title}` : `Scheduled task didn't finish: ${run.title}`,
        idempotencyKey: `task-run/${run.run_id}`,
        ...layout({
          heading,
          lines: [summary + (summary.length >= 300 ? "…" : "")],
          button: { label: ok ? "Read the full answer" : "Open Scheduled", href: appUrl(url) },
          footer: "You get this because the task is set to email you. Change it in Scheduled.",
        }),
      });
  }
}
