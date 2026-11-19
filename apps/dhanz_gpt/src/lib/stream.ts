"use client";

import type { GenEvent } from "@/lib/ai/generation";
import { ApiError } from "./api";

export type { GenEvent };

/** POST or GET an SSE endpoint and hand each event to `onEvent`. Resolves when the stream ends. */
export async function streamEvents(url: string, init: RequestInit | undefined, onEvent: (e: GenEvent) => void, signal?: AbortSignal) {
  const res = await fetch(url, { ...init, signal });
  if (res.status === 401 && typeof window !== "undefined") {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  }
  if (!res.ok || !res.body) {
    let msg = "Something went wrong. Try again.";
    try {
      msg = ((await res.json()) as { error?: string }).error ?? msg;
    } catch {}
    throw new ApiError(res.status, msg);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (data) onEvent(JSON.parse(data.slice(6)) as GenEvent);
    }
  }
}
