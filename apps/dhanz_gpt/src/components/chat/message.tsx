"use client";

import {
  Check, ChevronDown, ChevronLeft, ChevronRight, Copy, Globe, MoreHorizontal, RefreshCw, Share, ThumbsDown, ThumbsUp, Volume2,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { cn, focusRing } from "@/lib/cn";
import { Button, IconButton } from "@/components/ui/button";
import { Badge, Banner } from "@/components/ui/feedback";

export function UserMessage({ children }: { children: ReactNode }) {
  return (
    <article className="flex justify-end">
      <h3 className="sr-only">You said:</h3>
      <div className="max-w-[70%] rounded-xl bg-surface-muted px-4 py-2.5 text-base text-fg">{children}</div>
    </article>
  );
}

export function AssistantMessage({
  children, status = "complete", footer, thinking,
}: {
  children: ReactNode;
  status?: "streaming" | "complete" | "stopped" | "error";
  footer?: ReactNode;
  thinking?: ReactNode;
}) {
  return (
    <article className="group flex flex-col gap-3" aria-busy={status === "streaming" || undefined}>
      <h3 className="sr-only">Assistant said:</h3>
      {thinking}
      <div className="flex flex-col gap-4 text-base leading-7 text-fg [&_a]:text-accent-text [&_a]:underline [&_a]:underline-offset-2">
        {children}
        {status === "streaming" && (
          <span aria-hidden className="-mt-3 inline-block h-5 w-2 rounded-[1px] bg-fg animate-caret" />
        )}
      </div>
      {status === "stopped" && <div><Badge>Stopped</Badge></div>}
      {status === "error" && (
        <Banner
          tone="danger"
          title="That answer didn’t finish."
          action={<Button size="sm" variant="secondary" icon={<RefreshCw className="size-3.5" />}>Retry</Button>}
        >
          Your message is safe. Retry, or pick another model.
        </Banner>
      )}
      {status === "complete" && footer}
      <div className="sr-only" role="status">{status === "complete" ? "Response ready" : ""}</div>
    </article>
  );
}

export function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-code-bg">
      <div className="flex h-9 items-center justify-between border-b border-border px-3 text-xs text-muted">
        <span>{language}</span>
        <button
          type="button"
          onClick={() => {
            navigator.clipboard?.writeText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          }}
          className={cn("flex items-center gap-1.5 rounded-sm hover:text-fg", focusRing)}
          aria-label={copied ? "Copied" : "Copy code"}
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre aria-label={`${language} code`} className="overflow-x-auto p-4 font-mono text-sm leading-6 text-fg">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export function MessageActions({ alwaysVisible = false }: { alwaysVisible?: boolean }) {
  const [vote, setVote] = useState<1 | -1 | 0>(0);
  return (
    <div
      role="toolbar"
      aria-label="Message actions"
      className={cn(
        "-ml-1.5 flex items-center gap-0.5 transition-opacity",
        !alwaysVisible && "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100",
      )}
    >
      <IconButton label="Copy" size="sm"><Copy /></IconButton>
      <IconButton label="Good response" size="sm" aria-pressed={vote === 1} onClick={() => setVote(vote === 1 ? 0 : 1)}>
        <ThumbsUp className={cn(vote === 1 && "fill-current")} />
      </IconButton>
      <IconButton label="Bad response" size="sm" aria-pressed={vote === -1} onClick={() => setVote(vote === -1 ? 0 : -1)}>
        <ThumbsDown className={cn(vote === -1 && "fill-current")} />
      </IconButton>
      <IconButton label="Read aloud" size="sm"><Volume2 /></IconButton>
      <IconButton label="Regenerate" size="sm"><RefreshCw /></IconButton>
      <IconButton label="Share" size="sm"><Share /></IconButton>
      <IconButton label="More actions" size="sm"><MoreHorizontal /></IconButton>
    </div>
  );
}

export function BranchSwitcher({ index, total }: { index: number; total: number }) {
  const [i, setI] = useState(index);
  return (
    <div role="group" aria-label={`Response version ${i} of ${total}`} className="flex items-center text-xs text-muted">
      <IconButton label="Previous version" size="sm" disabled={i <= 1} onClick={() => setI(i - 1)}><ChevronLeft /></IconButton>
      <span className="tabular-nums" aria-hidden>{i} / {total}</span>
      <IconButton label="Next version" size="sm" disabled={i >= total} onClick={() => setI(i + 1)}><ChevronRight /></IconButton>
    </div>
  );
}

export function CitationChip({ title, href }: { title: string; href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={`Source: ${title}, opens in new tab`}
      className={cn(
        "mx-0.5 inline-flex h-5 translate-y-[-1px] items-center gap-1 rounded-full bg-surface-muted px-2 align-middle text-xs",
        "text-muted! no-underline! hover:bg-surface-active hover:text-fg!",
        focusRing,
      )}
    >
      <Globe aria-hidden className="size-3" />
      {title}
    </a>
  );
}

export function ThinkingIndicator({ seconds, summary, running }: { seconds?: number; summary?: string; running?: boolean }) {
  const [open, setOpen] = useState(false);
  if (running) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted" role="status">
        <span aria-hidden className="flex gap-1">
          {[0, 1, 2].map((d) => (
            <span key={d} className="size-1.5 animate-pulse rounded-full bg-current motion-reduce:animate-none" style={{ animationDelay: `${d * 150}ms` }} />
          ))}
        </span>
        Thinking
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className={cn("flex w-fit items-center gap-1 rounded-sm text-sm text-muted hover:text-fg", focusRing)}
      >
        Thought for {seconds}s
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && <p className="border-l-2 border-border-strong pl-3 text-sm text-muted">{summary}</p>}
    </div>
  );
}
