import { getProfile, getWorkspaceFor, unseenRunCount, usageToday } from "@/lib/data";
import { LIMITS } from "@/lib/data/types";
import { requireUser, route } from "@/lib/server/http";
import { webSearchMode } from "@/lib/ai/provider";
import { emailProvider } from "@/lib/server/email";
import { pushConfigured } from "@/lib/server/push";
import { transcribeProvider } from "@/lib/ai/transcribe";

export const GET = route(async () => {
  const userId = await requireUser();
  const [profile, { workspace, role }, messages, images, unseenTasks] = await Promise.all([
    getProfile(userId), getWorkspaceFor(userId), usageToday(userId, "message"), usageToday(userId, "image"), unseenRunCount(userId),
  ]);
  return {
    profile, workspace, role,
    usage: { messages, images, limits: { messages: LIMITS.messagesPerDay, images: LIMITS.imagesPerDay } },
    features: { webSearch: webSearchMode(), email: emailProvider() !== "off", push: pushConfigured(), dictation: transcribeProvider() !== "off" },
    unseen_task_runs: unseenTasks,
  };
});
