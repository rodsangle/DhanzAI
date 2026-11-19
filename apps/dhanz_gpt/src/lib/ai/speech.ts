import "server-only";

export { MAX_SPEECH_PARTS, speakable, speechParts } from "@/lib/speech-text";

/**
 * Read aloud (text to speech) behind one interface.
 * - "openai": OpenAI's speech endpoint (`POST /v1/audio/speech`) with the server's own key.
 *   SPEECH_MODEL defaults to gpt-4o-mini-tts, SPEECH_VOICE to coral.
 * - "demo": a short silent clip, so the button can be tried and tested offline.
 * - "off": hides Read aloud.
 * Default: "openai" when OPENAI_API_KEY is set, otherwise "off".
 */

export function speechProvider(): "openai" | "demo" | "off" {
  const p = process.env.SPEECH_PROVIDER ?? (process.env.OPENAI_API_KEY ? "openai" : "off");
  return p === "openai" || p === "demo" ? p : "off";
}

export type SpeechResult = { ok: true; bytes: Buffer; mime: string } | { ok: false; message: string };

export async function synthesize(text: string, signal?: AbortSignal): Promise<SpeechResult> {
  const provider = speechProvider();
  if (provider === "off") return { ok: false, message: "Read aloud isn't set up." };
  if (provider === "demo") return { ok: true, bytes: silentWav(0.4), mime: "audio/wav" };
  const base = (process.env.OPENAI_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  try {
    const res = await fetch(`${base}/audio/speech`, {
      method: "POST",
      headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: process.env.SPEECH_MODEL || "gpt-4o-mini-tts",
        voice: process.env.SPEECH_VOICE || "coral",
        input: text,
        response_format: "mp3",
      }),
      signal,
    });
    if (!res.ok) return { ok: false, message: res.status === 429 ? "The voice service is busy. Try again in a moment." : "This answer couldn't be read aloud. Try again." };
    return { ok: true, bytes: Buffer.from(await res.arrayBuffer()), mime: "audio/mpeg" };
  } catch {
    return { ok: false, message: "The voice service didn't respond. Try again." };
  }
}

/** A mono 8 kHz silent WAV of `seconds` length (the demo voice). */
function silentWav(seconds: number) {
  const rate = 8000;
  const samples = Math.round(rate * seconds);
  const b = Buffer.alloc(44 + samples * 2);
  b.write("RIFF", 0);
  b.writeUInt32LE(36 + samples * 2, 4);
  b.write("WAVEfmt ", 8);
  b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22);
  b.writeUInt32LE(rate, 24);
  b.writeUInt32LE(rate * 2, 28);
  b.writeUInt16LE(2, 32);
  b.writeUInt16LE(16, 34);
  b.write("data", 36);
  b.writeUInt32LE(samples * 2, 40);
  return b;
}
