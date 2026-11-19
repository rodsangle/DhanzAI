"use client";

import { CircleAlert, CircleCheck, ShieldQuestion } from "lucide-react";
import { useState } from "react";
import type { ContentBlock } from "@/lib/data/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/feedback";

type Approval = Extract<ContentBlock, { type: "approval" }>;

/** What the apps did while answering, one line each. */
export function ToolActivity({ items }: { items: { app: string; text: string; ok: boolean }[] }) {
  return (
    <ul aria-label="App activity" className="flex flex-col gap-1 text-sm text-muted">
      {items.map((it, i) => (
        <li key={i} className="flex items-start gap-2">
          {it.ok ? <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-success-text" /> : <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-danger-text" />}
          <span>
            <span className="font-medium text-fg">{it.app}</span> · {it.text}
          </span>
        </li>
      ))}
    </ul>
  );
}

const STATUS: Record<Approval["status"], string> = { pending: "Waiting for you", approved: "Approved", denied: "Declined", expired: "Expired" };

/** An app action the assistant wants to take, with exactly what it will send. */
export function ApprovalCard({ block, onDecide }: { block: Approval; onDecide?: (id: string, d: "approve" | "always" | "deny") => Promise<void> }) {
  const [busy, setBusy] = useState<null | "approve" | "always" | "deny">(null);
  const pending = block.status === "pending";
  const headingId = `approval-${block.approval_id}`;
  async function go(d: "approve" | "always" | "deny") {
    if (!onDecide) return;
    setBusy(d);
    try {
      await onDecide(block.approval_id, d);
    } finally {
      setBusy(null);
    }
  }
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3 rounded-xl border border-border-strong bg-surface p-4">
      <div className="flex items-start gap-2">
        <ShieldQuestion aria-hidden className="mt-0.5 size-5 shrink-0 text-muted" />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h4 id={headingId} className="text-sm font-semibold">{pending ? `Allow ${block.app} to do this?` : `${block.app} action`}</h4>
          <p className="text-sm">{block.action}</p>
        </div>
        <Badge tone={block.status === "approved" ? "success" : block.status === "denied" || block.status === "expired" ? "neutral" : "warning"}>{STATUS[block.status]}</Badge>
      </div>
      <dl className="flex flex-col gap-2 rounded-lg bg-surface-muted p-3 text-sm">
        {block.fields.map((f) => (
          <div key={f.label} className="flex flex-col gap-0.5">
            <dt className="text-xs font-medium text-muted">{f.label}</dt>
            <dd className="whitespace-pre-wrap break-words">{f.value}</dd>
          </div>
        ))}
      </dl>
      {pending && onDecide && (
        <div className="flex flex-wrap justify-end gap-2">
          <Button size="sm" variant="ghost" disabled={!!busy} loading={busy === "deny"} onClick={() => go("deny")}>Decline</Button>
          <Button size="sm" variant="secondary" disabled={!!busy} loading={busy === "always"} onClick={() => go("always")}>Always allow</Button>
          <Button size="sm" disabled={!!busy} loading={busy === "approve"} onClick={() => go("approve")}>Approve</Button>
        </div>
      )}
    </section>
  );
}
