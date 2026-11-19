import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Teach tailwind-merge our custom text sizes so `text-sm text-muted` isn't treated as a conflict.
const twMerge = extendTailwindMerge({
  extend: {
    theme: { text: ["xs", "sm", "base", "lg", "xl", "2xl", "3xl"] },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Shared focus treatment: 2px focus-token ring, offset by the surface colour.
 * Note: Tailwind v4's `outline-none` sets --tw-outline-style:none, which later `outline-2` inherits,
 * so the ring would never draw. Use `outline-hidden` + explicit `outline-solid` instead.
 */
export const focusRing =
  "outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-focus";
