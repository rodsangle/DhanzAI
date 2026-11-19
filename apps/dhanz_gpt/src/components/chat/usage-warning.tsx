"use client";

import { useState } from "react";
import { Banner } from "@/components/ui/feedback";

type Usage = { messages: number; images: number; limits: { messages: number; images: number } };

/** Warn when this many (or fewer) are left: a fifth of the cap, at least 5. */
export function warnAt(limit: number) {
  return Math.max(5, Math.ceil(limit * 0.2));
}

const today = () => new Date().toISOString().slice(0, 10);

function dismissedKey(metric: string) {
  return `dhanz-gpt:usage-warning:${metric}:${today()}`;
}
function wasDismissed(metric: string) {
  try {
    return localStorage.getItem(dismissedKey(metric)) === "1";
  } catch {
    return false;
  }
}
function remember(metric: string) {
  try {
    localStorage.setItem(dismissedKey(metric), "1");
  } catch {
    /* storage can be off; the banner just comes back next visit */
  }
}

/**
 * S05 usage state: an early, dismissible heads-up before the daily cap, and a firm notice at it.
 * Messages always; images only while image mode is on.
 */
export function UsageWarning({ usage, imageMode }: { usage: Usage | undefined; imageMode: boolean }) {
  const [dismissed, setDismissed] = useState<Record<string, boolean>>({});
  if (!usage) return null;

  const metric = imageMode && usage.images >= usage.limits.images - warnAt(usage.limits.images) ? "images" : "messages";
  const used = metric === "images" ? usage.images : usage.messages;
  const limit = metric === "images" ? usage.limits.images : usage.limits.messages;
  const left = Math.max(0, limit - used);
  const noun = metric === "images" ? (left === 1 ? "image" : "images") : left === 1 ? "message" : "messages";

  if (left === 0) {
    if (metric === "messages") return null; // the composer itself says the limit is reached
    return (
      <Banner tone="danger" title="You've made today's images">
        You&apos;ve used all {limit} images for today. You can keep chatting, and images are available again after midnight.
      </Banner>
    );
  }
  if (left > warnAt(limit)) return null;
  if (dismissed[metric] || wasDismissed(metric)) return null;

  return (
    <Banner
      tone="warning"
      title={`${left} ${noun} left today`}
      onDismiss={() => {
        remember(metric);
        setDismissed((d) => ({ ...d, [metric]: true }));
      }}
    >
      You&apos;ve used {used} of today&apos;s {limit}. The count resets at midnight.
    </Banner>
  );
}
