"use client";

import { BRAND } from "@/lib/brand";
import { AlertTriangle, Check, Circle, Loader2, MessageSquare, MoreHorizontal, Minus, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { cn, focusRing } from "@/lib/cn";
import { Button, IconButton } from "@/components/ui/button";
import { Badge } from "@/components/ui/feedback";

/* ------------------------------------------------------------------ ApprovalCard */

type Decision = "pending" | "approved" | "always" | "denied" | "expired";

export function ApprovalCard({
  app, appIcon, action, importance = "change", preview, initial = "pending",
}: {
  app: string;
  appIcon: ReactNode;
  action: string;
  importance?: "change" | "important";
  preview: { label: string; value: string }[];
  initial?: Decision;
}) {
  const [decision, setDecision] = useState<Decision>(initial);
  const done = decision !== "pending";
  const outcome: Record<Exclude<Decision, "pending">, string> = {
    approved: "Approved",
    always: `Approved. Future ${app} actions won't ask`,
    denied: "Denied. Nothing was sent",
    expired: "Expired without a decision",
  };
  return (
    <section
      aria-label="Approval needed"
      role={done ? undefined : "alert"}
      className={cn("overflow-hidden rounded-lg border border-border-strong bg-surface-raised", done && "opacity-80")}
    >
      {importance === "important" && !done && (
        <div className="flex items-center gap-2 bg-warning-subtle px-4 py-2 text-xs font-semibold text-warning-text">
          <AlertTriangle aria-hidden className="size-3.5" /> This reaches people outside {BRAND.name}
        </div>
      )}
      <div className="flex flex-col gap-3 p-4">
        <div className="flex items-center gap-2.5">
          <span aria-hidden className="flex size-7 items-center justify-center rounded-md bg-surface-muted [&_svg]:size-4">{appIcon}</span>
          <p className="text-sm font-semibold text-fg">
            {app} wants to {action}
          </p>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-md bg-surface-muted p-3 text-sm">
          {preview.map((p) => (
            <div key={p.label} className="contents">
              <dt className="text-muted">{p.label}</dt>
              <dd className="whitespace-pre-wrap text-fg">{p.value}</dd>
            </div>
          ))}
        </dl>
        {done ? (
          <p role="status" className="text-sm text-muted">{outcome[decision]}</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setDecision("approved")}>Approve</Button>
            <Button size="sm" variant="secondary" onClick={() => setDecision("always")}>Always allow</Button>
            <Button size="sm" variant="ghost" onClick={() => setDecision("denied")}>Deny</Button>
          </div>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ ProgressTimeline */

export type Step = { label: string; detail?: string; status: "pending" | "running" | "done" | "failed" | "skipped"; time?: string };

const stepIcon = {
  pending: <Circle className="size-4 text-subtle" />,
  running: <Loader2 className="size-4 animate-spin text-fg motion-reduce:animate-none" />,
  done: <Check className="size-4 text-success-text" strokeWidth={3} />,
  failed: <X className="size-4 text-danger-text" strokeWidth={3} />,
  skipped: <Minus className="size-4 text-subtle" />,
};
const stepWord = { pending: "Not started", running: "In progress", done: "Done", failed: "Failed", skipped: "Skipped" };

export function ProgressTimeline({ steps }: { steps: Step[] }) {
  return (
    <ol className="flex flex-col">
      {steps.map((s, i) => (
        <li key={i} aria-current={s.status === "running" ? "step" : undefined} className="relative flex gap-3 pb-4 last:pb-0">
          {i < steps.length - 1 && <span aria-hidden className="absolute left-[11px] top-6 h-[calc(100%-20px)] w-px bg-border-strong" />}
          <span aria-hidden className="flex size-6 shrink-0 items-center justify-center rounded-full bg-surface-muted">{stepIcon[s.status]}</span>
          <div className="flex flex-1 flex-col gap-0.5 pt-0.5">
            <div className="flex items-baseline justify-between gap-2">
              <span className={cn("text-sm", s.status === "pending" ? "text-muted" : "text-fg", s.status === "running" && "font-medium")}>
                {s.label}
                <span className="sr-only">, {stepWord[s.status]}</span>
              </span>
              {s.time && <span className="text-xs tabular-nums text-muted">{s.time}</span>}
            </div>
            {s.detail && <span className="text-xs text-muted">{s.detail}</span>}
            {s.status === "failed" && (
              <div className="pt-1"><Button size="sm" variant="secondary">Retry step</Button></div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

/* ------------------------------------------------------------------ Sidebar rows */

export function ChatRow({
  title, active, streaming, href = "#",
}: { title: string; active?: boolean; streaming?: boolean; href?: string }) {
  return (
    <li className="group relative">
      <a
        href={href}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex h-9 items-center gap-2 rounded-md px-2 pr-9 text-sm text-fg transition-colors",
          "hover:bg-surface-hover aria-[current=page]:bg-surface-active",
          focusRing, "focus-visible:outline-offset-0",
        )}
      >
        <span className="min-w-0 flex-1 overflow-hidden whitespace-nowrap [mask-image:linear-gradient(to_right,black_85%,transparent)]">
          {title}
        </span>
        {streaming && <Loader2 aria-label="Answering" className="size-3.5 animate-spin text-muted motion-reduce:animate-none" />}
      </a>
      <IconButton
        label={`Options for ${title}`}
        size="sm"
        className="absolute right-0.5 top-0.5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 group-has-[[aria-current=page]]:opacity-100"
      >
        <MoreHorizontal />
      </IconButton>
    </li>
  );
}

export function SidebarSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-0.5">
      <h2 className="sticky top-0 bg-surface px-2 pb-1 pt-3 text-xs font-semibold text-muted">{label}</h2>
      <ul className="flex flex-col gap-px">{children}</ul>
    </section>
  );
}

/* ------------------------------------------------------------------ TaskCard */

export function TaskCard({
  title, schedule, next, status,
}: { title: string; schedule: string; next: string; status: "active" | "paused" }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border bg-surface-raised p-4">
      <span aria-hidden className="flex size-9 items-center justify-center rounded-md bg-surface-muted text-muted">
        <MessageSquare className="size-4" />
      </span>
      <div className="flex flex-1 flex-col gap-0.5">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold text-fg">{title}</p>
          <Badge tone={status === "active" ? "success" : "warning"}>{status === "active" ? "Active" : "Paused"}</Badge>
        </div>
        <p className="text-sm text-muted">{schedule}</p>
        <p className="text-xs text-muted">Next run: {next}</p>
      </div>
      <IconButton label={`Options for ${title}`} size="sm"><MoreHorizontal /></IconButton>
    </div>
  );
}
