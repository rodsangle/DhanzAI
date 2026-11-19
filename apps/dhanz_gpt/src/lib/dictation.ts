"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export const DICTATION_LIMIT_SECONDS = 300;

export type DictationState =
  | { phase: "idle" }
  | { phase: "starting" }
  | { phase: "recording"; seconds: number; level: number }
  | { phase: "transcribing" };

/** Pick a recording format the browser supports and the speech service accepts. */
function pickMime() {
  const options = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  if (typeof MediaRecorder === "undefined") return null;
  return options.find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
}

export function dictationSupported() {
  return typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
}

/**
 * Records from the microphone, sends the clip to /api/transcribe, and hands back the text.
 * Stops on its own at 5 minutes. Cancel throws the recording away without sending it.
 */
export function useDictation({ onText, onError }: { onText: (text: string) => void; onError: (message: string) => void }) {
  const [state, setState] = useState<DictationState>({ phase: "idle" });
  const rec = useRef<{ recorder: MediaRecorder; stream: MediaStream; chunks: Blob[]; started: number; cancelled: boolean; timer: number; ctx?: AudioContext } | null>(null);

  const cleanup = useCallback(() => {
    const r = rec.current;
    if (!r) return;
    window.clearInterval(r.timer);
    r.stream.getTracks().forEach((t) => t.stop());
    r.ctx?.close().catch(() => {});
    rec.current = null;
  }, []);

  useEffect(() => () => {
    if (rec.current) {
      rec.current.cancelled = true;
      if (rec.current.recorder.state !== "inactive") rec.current.recorder.stop();
      cleanup();
    }
  }, [cleanup]);

  const send = useCallback(async (blob: Blob, seconds: number) => {
    setState({ phase: "transcribing" });
    try {
      const form = new FormData();
      form.set("audio", blob, "dictation");
      form.set("seconds", String(seconds));
      const res = await fetch("/api/transcribe", { method: "POST", body: form });
      const json = (await res.json().catch(() => ({}))) as { text?: string; error?: string };
      if (!res.ok || !json.text) throw new Error(json.error ?? "The recording couldn't be turned into text. Try again.");
      onText(json.text);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setState({ phase: "idle" });
    }
  }, [onText, onError]);

  const start = useCallback(async () => {
    if (rec.current) return;
    const mime = pickMime();
    if (mime === null || !navigator.mediaDevices?.getUserMedia) {
      onError("This browser can't record audio. Try Chrome, Edge, Safari or Firefox.");
      return;
    }
    setState({ phase: "starting" });
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      setState({ phase: "idle" });
      const name = (e as DOMException).name;
      onError(
        name === "NotAllowedError" || name === "SecurityError"
          ? "Microphone access is blocked. Allow it in your browser's site settings, then try again."
          : name === "NotFoundError"
            ? "No microphone was found."
            : "The microphone couldn't be started.",
      );
      return;
    }
    const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (ev) => ev.data.size && chunks.push(ev.data);

    // A live level for the meter, so you can see it's hearing you.
    let ctx: AudioContext | undefined;
    let analyser: AnalyserNode | undefined;
    try {
      ctx = new AudioContext();
      analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      ctx.createMediaStreamSource(stream).connect(analyser);
    } catch {
      /* no meter, recording still works */
    }
    const buf = new Uint8Array(analyser?.frequencyBinCount ?? 0);
    const started = Date.now();
    const timer = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      let level = 0;
      if (analyser) {
        analyser.getByteTimeDomainData(buf);
        for (const v of buf) level = Math.max(level, Math.abs(v - 128) / 128);
      }
      setState({ phase: "recording", seconds, level });
      if (seconds >= DICTATION_LIMIT_SECONDS) stop();
    }, 200);

    recorder.onstop = () => {
      const r = rec.current;
      const seconds = Math.round((Date.now() - started) / 1000);
      const cancelled = r?.cancelled ?? true;
      cleanup();
      if (cancelled) {
        setState({ phase: "idle" });
        return;
      }
      const blob = new Blob(chunks, { type: recorder.mimeType || mime || "audio/webm" });
      if (blob.size === 0) {
        setState({ phase: "idle" });
        onError("Nothing was recorded. Check your microphone and try again.");
        return;
      }
      void send(blob, seconds);
    };
    rec.current = { recorder, stream, chunks, started, cancelled: false, timer, ctx };
    recorder.start(1000);
    setState({ phase: "recording", seconds: 0, level: 0 });
  }, [cleanup, onError, send]);

  function stop() {
    const r = rec.current;
    if (r && r.recorder.state !== "inactive") r.recorder.stop();
  }
  const cancel = useCallback(() => {
    const r = rec.current;
    if (!r) return;
    r.cancelled = true;
    if (r.recorder.state !== "inactive") r.recorder.stop();
    else cleanup();
  }, [cleanup]);

  return { state, start, stop, cancel };
}
