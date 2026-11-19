import "server-only";
import { getMemory, getPersonalization, memorySourceMessages, saveMemory } from "@/lib/data";
import { HttpError } from "@/lib/data/errors";
import { friendly, summarizeMemory } from "./provider";

const AUTO_REFRESH_EVERY_MS = 60 * 60 * 1000;
const MANUAL_REFRESH_EVERY_MS = 20 * 1000;

/**
 * Updates the memory summary from recent chats. Runs after answers (at most hourly) and from
 * the Refresh button (at most every 20 s). Does nothing when memory is off.
 */
export async function refreshMemory(userId: string, opts: { manual?: boolean } = {}) {
  const pers = await getPersonalization(userId);
  if (!pers.memory_enabled) {
    if (opts.manual) throw new HttpError(409, "Memory is off. Turn it on to refresh it.");
    return null;
  }
  const mem = await getMemory(userId);
  const since = mem.refreshed_at ? Date.now() - new Date(mem.refreshed_at).getTime() : Infinity;
  if (since < (opts.manual ? MANUAL_REFRESH_EVERY_MS : AUTO_REFRESH_EVERY_MS)) {
    if (opts.manual) throw new HttpError(429, "Memory was just refreshed. Try again in a moment.");
    return mem;
  }
  const messages = (await memorySourceMessages(userId)).map((m) => m.text);
  let body: string;
  try {
    body = await summarizeMemory(mem.body, messages);
  } catch (e) {
    // The Refresh button gets a plain reason (e.g. the model is busy); background refreshes just log it.
    throw new HttpError(503, friendly(e).message);
  }
  return saveMemory(userId, body, { refreshed: true });
}
