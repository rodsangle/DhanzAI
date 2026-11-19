import "server-only";
import { IMAGE_SIZES, type ImageSize } from "@/lib/data/types";
import { placeholderImage } from "./fake-model";

/**
 * Image generation behind one interface.
 * - "openai": the OpenAI Images API with the server's own key: `POST /v1/images/generations` for a new
 *   image, `POST /v1/images/edits` to change images the person gave (or the last one made in the chat).
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

/** An image to change: one the person attached, or the last one made in the chat. */
export type SourceImage = { bytes: Buffer; mime: string; name: string };

/** Formats the edit endpoint takes; others (SVG placeholders, GIF) can't be edited. */
export const EDITABLE_IMAGE = /^image\/(png|jpeg|webp)$/;

export async function generateImage(
  prompt: string,
  /** "auto" (edits only) keeps the proportions of the image being changed. */
  opts: { size?: ImageSize | "auto"; sources?: SourceImage[]; signal?: AbortSignal } = {},
): Promise<ImageResult> {
  const provider = imageProvider();
  const sources = (opts.sources ?? []).slice(0, 4);
  const auto = opts.size === "auto" && sources.length > 0;
  const shape = IMAGE_SIZES.find((s) => s.id === opts.size) ?? IMAGE_SIZES[0];
  if (provider === "placeholder")
    return { ok: true, bytes: placeholderImage(prompt, shape.id, sources.length > 0), mime: "image/svg+xml", provider };

  const base = (process.env.OPENAI_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  const model = process.env.IMAGE_MODEL || "gpt-image-1";
  let res: Response;
  try {
    if (sources.length) {
      const form = new FormData();
      form.set("model", model);
      form.set("prompt", prompt.slice(0, 4000));
      form.set("size", auto ? "auto" : shape.size);
      form.set("n", "1");
      for (const src of sources)
        form.append(sources.length > 1 ? "image[]" : "image", new Blob([new Uint8Array(src.bytes)], { type: src.mime }), src.name);
      res = await fetch(`${base}/images/edits`, {
        method: "POST",
        headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}` },
        body: form,
        signal: opts.signal,
      });
    } else {
      res = await fetch(`${base}/images/generations`, {
        method: "POST",
        headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({ model, prompt: prompt.slice(0, 4000), size: shape.size, n: 1 }),
        signal: opts.signal,
      });
    }
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
