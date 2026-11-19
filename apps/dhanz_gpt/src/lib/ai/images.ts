import "server-only";
import { placeholderImage } from "./fake-model";

/**
 * Image generation behind one interface.
 * - "openai": the OpenAI Images API (`POST /v1/images/generations`) with the server's own key.
 *   Set IMAGE_MODEL to the model you've chosen; check OpenAI's docs for the current name.
 * - "placeholder": a labelled abstract render, for development and tests.
 * Swap in another provider (e.g. fal.ai) by adding a branch here: nothing else changes.
 */

export type ImageResult =
  | { ok: true; bytes: Buffer; mime: string; provider: string }
  | { ok: false; refused: boolean; message: string; provider: string };

export function imageProvider(): "openai" | "placeholder" {
  const p = process.env.IMAGE_PROVIDER ?? (process.env.OPENAI_API_KEY ? "openai" : "placeholder");
  if (p !== "openai" && p !== "placeholder") throw new Error(`Unknown IMAGE_PROVIDER ${p}`);
  return p;
}

export async function generateImage(prompt: string, signal?: AbortSignal): Promise<ImageResult> {
  const provider = imageProvider();
  if (provider === "placeholder") return { ok: true, bytes: placeholderImage(prompt), mime: "image/svg+xml", provider };

  const base = (process.env.OPENAI_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  let res: Response;
  try {
    res = await fetch(`${base}/images/generations`, {
      method: "POST",
      headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: process.env.IMAGE_MODEL || "gpt-image-1", prompt: prompt.slice(0, 4000), size: "1024x1024", n: 1 }),
      signal,
    });
  } catch {
    return { ok: false, refused: false, message: "The image service didn't respond. Try again.", provider };
  }
  const json = (await res.json().catch(() => ({}))) as { data?: { b64_json?: string }[]; error?: { code?: string; message?: string } };
  if (!res.ok) {
    const code = json.error?.code ?? "";
    const refused = res.status === 400 && /moderation|content_policy|safety/i.test(code + (json.error?.message ?? ""));
    return {
      ok: false,
      refused,
      message: refused ? "The image service declined this request. Try describing it differently." : res.status === 429 ? "The image service is busy. Try again in a moment." : "The image couldn't be created. Try again.",
      provider,
    };
  }
  const b64 = json.data?.[0]?.b64_json;
  if (!b64) return { ok: false, refused: false, message: "The image service returned nothing. Try again.", provider };
  return { ok: true, bytes: Buffer.from(b64, "base64"), mime: "image/png", provider };
}
