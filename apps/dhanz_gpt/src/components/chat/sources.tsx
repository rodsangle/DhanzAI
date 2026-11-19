"use client";

import { BookMarked, Globe, MessageSquare } from "lucide-react";
import Link from "next/link";
import type { Source } from "@/lib/data/types";
import { cn, focusRing } from "@/lib/cn";

const chip = cn(
  "inline-flex h-7 max-w-64 items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 text-xs text-muted",
  "hover:bg-surface-active hover:text-fg",
  focusRing,
);

const host = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
};

/** What an answer drew on: saved memory, an earlier chat, web pages. */
export function SourcesRow({ items, onOpenMemory }: { items: Source[]; onOpenMemory?: () => void }) {
  if (!items.length) return null;
  let web = 0;
  return (
    <div className="flex flex-col gap-1.5">
      <h4 className="text-xs font-medium text-muted">Sources</h4>
      <ul aria-label="Sources" className="flex flex-wrap gap-1.5">
        {items.map((s, i) => (
          <li key={i} className="min-w-0">
            {s.kind === "memory" ? (
              <button type="button" className={chip} onClick={onOpenMemory}>
                <BookMarked aria-hidden className="size-3.5 shrink-0" /> Memory
              </button>
            ) : s.kind === "chat" ? (
              <Link href={`/c/${s.conversation_id}`} className={chip} title={s.title}>
                <MessageSquare aria-hidden className="size-3.5 shrink-0" />
                <span className="truncate">Earlier chat: {s.title}</span>
              </Link>
            ) : (
              <a href={s.url} target="_blank" rel="noreferrer noopener" className={chip} title={s.title}>
                <span className="shrink-0 font-medium text-fg">{++web}</span>
                <Globe aria-hidden className="size-3.5 shrink-0" />
                <span className="truncate">{s.title}</span>
                <span className="shrink-0">· {host(s.url)}</span>
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
