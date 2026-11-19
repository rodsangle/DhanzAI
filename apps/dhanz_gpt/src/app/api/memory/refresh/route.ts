import { refreshMemory } from "@/lib/ai/memory";
import { requireUser, route } from "@/lib/server/http";

// Rebuilds the summary from recent chats now (rate limited inside).
export const POST = route(async () => refreshMemory(await requireUser(), { manual: true }));
