import { getMessage, HttpError } from "@/lib/data";
import { speakable, speechParts, speechProvider, synthesize } from "@/lib/ai/speech";
import { idParam, requireUser, route } from "@/lib/server/http";

// Per person, in memory: enough to listen to long answers, not enough to run up the voice bill.
const recent = new Map<string, number[]>();
function limit(userId: string) {
  const now = Date.now();
  const hits = (recent.get(userId) ?? []).filter((t) => now - t < 10 * 60_000);
  if (hits.length >= 60) throw new HttpError(429, "That's a lot of reading aloud. Try again in a few minutes.");
  hits.push(now);
  recent.set(userId, hits);
}

/**
 * GET /api/messages/:id/speech?part=0 → audio for one part of an answer. The X-Speech-Parts header
 * says how many parts there are; the player fetches the next one while the current one plays.
 * Anyone who can see the chat can listen.
 */
export const GET = route(async (req: Request, { params }: { params: Promise<{ id: string }> }) => {
  const userId = await requireUser();
  if (speechProvider() === "off") throw new HttpError(404, "Read aloud isn't set up.");
  const message = await getMessage(userId, idParam((await params).id));
  if (message.role !== "assistant" || message.status === "streaming") throw new HttpError(400, "Only finished answers can be read aloud.");
  const parts = speechParts(speakable(message.text));
  if (!parts.length) throw new HttpError(400, "There's no text to read in this answer.");
  const part = Number(new URL(req.url).searchParams.get("part") ?? 0);
  if (!Number.isInteger(part) || part < 0 || part >= parts.length) throw new HttpError(400, "That part doesn't exist.");
  limit(userId);
  const result = await synthesize(parts[part], req.signal);
  if (!result.ok) throw new HttpError(502, result.message);
  return new Response(new Uint8Array(result.bytes), {
    headers: {
      "Content-Type": result.mime,
      "X-Speech-Parts": String(parts.length),
      "Cache-Control": "private, max-age=3600",
    },
  });
});
