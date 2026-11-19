import { randomUUID } from "node:crypto";
import { HttpError, recordUsage } from "@/lib/data";
import { asService } from "@/lib/server/db";
import { requireUser, route } from "@/lib/server/http";
import { DICTATION_MAX_SECONDS, transcribe, TRANSCRIBE_MAX_BYTES } from "@/lib/ai/transcribe";

export const maxDuration = 60;

const AUDIO = /^audio\/(webm|ogg|mp4|mpeg|mp3|wav|x-wav|m4a|x-m4a|flac)(;.*)?$/;

// S05 dictation: one recording in, text out. Nothing is stored: not the audio, not the text.
export const POST = route(async (req: Request) => {
  const userId = await requireUser();
  const declared = Number(req.headers.get("content-length") ?? 0);
  if (declared > TRANSCRIBE_MAX_BYTES + 64 * 1024) throw new HttpError(413, "That recording is too long. Keep it under 5 minutes.");

  // At most 10 recordings a minute per person.
  const [{ n }] = await asService((q) => q`
    select count(*)::int as n from usage_events where user_id = ${userId} and metric = 'voice_second' and created_at > now() - interval '1 minute'`);
  if (n >= 10) throw new HttpError(429, "That's a lot of dictation at once. Wait a moment and try again.");

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    throw new HttpError(400, "Send the recording as form data.");
  }
  const audio = form.get("audio");
  if (!(audio instanceof Blob) || audio.size === 0) throw new HttpError(400, "No recording was sent.");
  if (!AUDIO.test(audio.type)) throw new HttpError(415, "That isn't an audio recording.");
  if (audio.size > TRANSCRIBE_MAX_BYTES) throw new HttpError(413, "That recording is too long. Keep it under 5 minutes.");
  const seconds = Math.min(DICTATION_MAX_SECONDS, Math.max(0, Math.round(Number(form.get("seconds")) || 0)));

  const ext = audio.type.includes("ogg") ? "ogg" : audio.type.includes("mp4") || audio.type.includes("m4a") ? "m4a" : audio.type.includes("wav") ? "wav" : audio.type.includes("mpeg") || audio.type.includes("mp3") ? "mp3" : audio.type.includes("flac") ? "flac" : "webm";
  const result = await transcribe(audio, `dictation.${ext}`, req.signal);
  // One row per recording, its length in seconds as the quantity (for cost tracking and the rate limit above).
  await recordUsage(userId, "voice_second", `dictation-${randomUUID()}`, { model: process.env.TRANSCRIBE_MODEL || "gpt-transcribe", quantity: Math.max(1, seconds) });
  if (!result.ok) throw new HttpError(result.status, result.message);
  if (!result.text) throw new HttpError(422, "No speech was heard. Check your microphone and try again.");
  return { text: result.text };
});
