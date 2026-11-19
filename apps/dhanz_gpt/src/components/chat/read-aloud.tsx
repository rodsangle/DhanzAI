"use client";
import { Loader2, Square, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { IconButton } from "@/components/ui/button";
import { useToast } from "@/components/ui/feedback";

/** One answer reads at a time across the page: starting another stops this one. */
let stopCurrent: (() => void) | null = null;

/** Read aloud: plays an answer's parts in order, fetching the next while the current one plays. */
export function ReadAloud({ messageId }: { messageId: string }) {
  const toast = useToast();
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");
  const run = useRef<{ cancelled: boolean; audio: HTMLAudioElement | null; urls: string[] } | null>(null);

  const stop = () => {
    const r = run.current;
    if (!r) return;
    r.cancelled = true;
    r.audio?.pause();
    r.urls.forEach((u) => URL.revokeObjectURL(u));
    run.current = null;
    if (stopCurrent === stop) stopCurrent = null;
    setState("idle");
  };
  useEffect(() => () => stop(), []); // eslint-disable-line react-hooks/exhaustive-deps

  async function fetchPart(i: number) {
    const res = await fetch(`/api/messages/${messageId}/speech?part=${i}`);
    if (!res.ok) {
      const j = (await res.json().catch(() => ({}))) as { error?: string };
      throw new Error(j.error || "This answer couldn't be read aloud. Try again.");
    }
    return { url: URL.createObjectURL(await res.blob()), parts: Number(res.headers.get("X-Speech-Parts") || 1) };
  }

  async function start() {
    stopCurrent?.();
    stopCurrent = stop;
    const r = { cancelled: false, audio: null as HTMLAudioElement | null, urls: [] as string[] };
    run.current = r;
    setState("loading");
    try {
      let next = fetchPart(0);
      for (let i = 0; ; i++) {
        const { url, parts } = await next;
        if (r.cancelled) return URL.revokeObjectURL(url);
        r.urls.push(url);
        if (i + 1 < parts) next = fetchPart(i + 1);
        const audio = new Audio(url);
        r.audio = audio;
        setState("playing");
        await new Promise<void>((resolve, reject) => {
          audio.onended = () => resolve();
          audio.onerror = () => reject(new Error("The audio couldn't be played."));
          audio.play().catch(reject);
        });
        if (r.cancelled || i + 1 >= parts) break;
      }
    } catch (e) {
      if (!r.cancelled) toast({ title: (e as Error).message, tone: "error" });
    }
    if (run.current === r) stop();
  }

  return state === "idle" ? (
    <IconButton label="Read aloud" size="sm" onClick={start}><Volume2 /></IconButton>
  ) : (
    <IconButton label="Stop reading" size="sm" onClick={stop}>{state === "loading" ? <Loader2 className="animate-spin" /> : <Square />}</IconButton>
  );
}
