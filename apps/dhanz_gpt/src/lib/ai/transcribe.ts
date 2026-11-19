import "server-only";

/**
 * Speech to text for dictation (S05), behind one interface.
 * - "openai": OpenAI's transcription endpoint (`POST /v1/audio/transcriptions`) with the server's own key.
 *   Default model `gpt-transcribe`; set TRANSCRIBE_MODEL to change it. Files up to 25 MB; browsers record webm.
 * - "off": no key configured. The composer hides the Dictate button.
 */

export const TRANSCRIBE_MAX_BYTES = 24 * 1024 * 1024; // under the provider's 25 MB cap, with room for the form
export const DICTATION_MAX_SECONDS = 300;

export function transcribeProvider(): "openai" | "off" {
  const p = process.env.TRANSCRIBE_PROVIDER ?? (process.env.OPENAI_API_KEY ? "openai" : "off");
  if (p !== "openai" && p !== "off") throw new Error(`Unknown TRANSCRIBE_PROVIDER ${p}`);
  return p;
}

/** Words the model should spell our way. A prompt nudges spelling; it never becomes part of the transcript. */
const VOCABULARY = "Dhanz, Dhanz GPT, DHANZ AI.";

export type TranscribeResult = { ok: true; text: string } | { ok: false; status: number; message: string };

export async function transcribe(audio: Blob, filename: string, signal?: AbortSignal): Promise<TranscribeResult> {
  if (transcribeProvider() === "off") return { ok: false, status: 503, message: "Dictation isn't set up for this workspace." };
  const base = (process.env.OPENAI_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  const form = new FormData();
  form.set("file", audio, filename);
  form.set("model", process.env.TRANSCRIBE_MODEL || "gpt-transcribe");
  form.set("response_format", "json");
  form.set("prompt", `Dictated message to an AI assistant. ${VOCABULARY}`);
  let res: Response;
  try {
    res = await fetch(`${base}/audio/transcriptions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}` },
      body: form,
      signal,
    });
  } catch {
    return { ok: false, status: 502, message: "The speech service didn't respond. Try again." };
  }
  const json = (await res.json().catch(() => ({}))) as { text?: string; error?: { message?: string } };
  if (!res.ok) {
    if (res.status === 429) return { ok: false, status: 503, message: "The speech service is busy. Try again in a moment." };
    if (res.status === 400 || res.status === 413) return { ok: false, status: 422, message: "That recording couldn't be read. Try recording again." };
    return { ok: false, status: 502, message: "The recording couldn't be turned into text. Try again." };
  }
  return { ok: true, text: (json.text ?? "").trim() };
}
