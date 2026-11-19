"use client";

import { Tooltip as T } from "radix-ui";
import type { ReactNode } from "react";

export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <T.Provider delayDuration={500} skipDelayDuration={300}>
      {children}
    </T.Provider>
  );
}

export function Tooltip({
  label,
  side = "top",
  children,
}: {
  label: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  children: ReactNode;
}) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content
          side={side}
          sideOffset={6}
          className="z-[var(--z-tooltip)] rounded-sm bg-fg px-2 py-1 text-xs font-medium text-bg shadow-sm animate-enter"
        >
          {label}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
