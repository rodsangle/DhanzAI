"use client";

import { Check, RotateCcw, Trash2, X } from "lucide-react";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { Button, IconButton } from "@/components/ui/button";
import { useToast } from "@/components/ui/feedback";
import { Textarea } from "@/components/ui/field";
import type { CommentRow, Level } from "@/lib/data/space-types";

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

async function send(url: string, method: string, data?: unknown) {
  const res = await fetch(url, { method, headers: data ? { "Content-Type": "application/json" } : undefined, body: data ? JSON.stringify(data) : undefined });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? "That didn’t go through. Try again.");
}

function Thread({ root, replies, level, pageId, onChanged }: { root: CommentRow; replies: CommentRow[]; level: Level; pageId: string; onChanged: () => void }) {
  const toast = useToast();
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const canWrite = level !== "view";
  async function act(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
      onChanged();
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  }
  const resolved = !!root.resolved_at;
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-border p-3" aria-label={`Comment by ${root.author_name ?? "a former teammate"}`}>
      {root.quote && <blockquote className="border-l-2 border-border-strong pl-2 text-xs text-muted">{root.quote}</blockquote>}
      {[root, ...replies].map((c) => (
        <div key={c.id} className="group flex flex-col gap-0.5">
          <p className="flex items-center gap-2 text-xs text-muted">
            <span className="font-medium text-fg">{c.author_name ?? "Former teammate"}</span>
            <span>{when(c.created_at)}</span>
            {c.mine && (
              <IconButton
                label="Delete comment"
                size="sm"
                tooltip={false}
                className="ml-auto opacity-0 focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
                onClick={() => act(() => send(`/api/comments/${c.id}`, "DELETE"))}
              >
                <Trash2 />
              </IconButton>
            )}
          </p>
          <p className="whitespace-pre-wrap text-sm">{c.body}</p>
        </div>
      ))}
      {resolved && <p className="text-xs text-muted">Resolved by {root.resolved_by_name ?? "someone"}</p>}
      <div className="flex flex-wrap items-center gap-2">
        {canWrite && !resolved && (
          <form
            className="flex w-full items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (reply.trim()) act(async () => { await send(`/api/pages/${pageId}/comments`, "POST", { body: reply, parent_comment_id: root.id }); setReply(""); });
            }}
          >
            <Textarea label="Reply" hideLabel placeholder="Reply" rows={1} value={reply} onChange={(e) => setReply(e.target.value)} className="min-h-9" />
            <Button type="submit" size="sm" variant="secondary" disabled={!reply.trim() || busy}>Reply</Button>
          </form>
        )}
        {(root.mine || level === "edit") && (
          <Button
            size="sm"
            variant="ghost"
            icon={resolved ? <RotateCcw className="size-4" /> : <Check className="size-4" />}
            onClick={() => act(() => send(`/api/comments/${root.id}`, "PATCH", { resolved: !resolved }))}
            disabled={busy}
          >
            {resolved ? "Reopen" : "Resolve"}
          </Button>
        )}
      </div>
    </li>
  );
}

/** S12 comments: threads on the page, optionally quoting the passage they're about. */
export function CommentsPanel({ pageId, level, quote, onQuoteUsed, onClose }: {
  pageId: string; level: Level; quote: string | null; onQuoteUsed: () => void; onClose: () => void;
}) {
  const toast = useToast();
  const key = `/api/pages/${pageId}/comments`;
  const { data, error } = useSWR<CommentRow[]>(key, { refreshInterval: 8000 });
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [showResolved, setShowResolved] = useState(false);
  const roots = (data ?? []).filter((c) => !c.parent_comment_id);
  const open = roots.filter((c) => !c.resolved_at);
  const done = roots.filter((c) => c.resolved_at);
  const changed = () => { mutate(key); mutate(`/api/pages/${pageId}/state`); };

  async function add() {
    setBusy(true);
    try {
      await send(key, "POST", { body, quote });
      setBody("");
      onQuoteUsed();
      changed();
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside aria-label="Comments" className="flex h-full w-full flex-col border-l border-border bg-surface md:w-80">
      <div className="flex h-12 shrink-0 items-center justify-between px-3">
        <h2 className="text-sm font-semibold">Comments</h2>
        <IconButton label="Close comments" size="sm" onClick={onClose}><X /></IconButton>
      </div>
      <div className="flex-1 overflow-y-auto px-3 pb-3">
        {level !== "view" ? (
          <form className="mb-4 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); if (body.trim()) add(); }}>
            {quote && (
              <div className="flex items-start gap-2 rounded-md bg-surface-muted p-2 text-xs text-muted">
                <span className="flex-1">On “{quote.length > 140 ? `${quote.slice(0, 140)}…` : quote}”</span>
                <IconButton label="Comment on the whole page instead" size="sm" tooltip={false} onClick={onQuoteUsed}><X /></IconButton>
              </div>
            )}
            <Textarea label="New comment" hideLabel placeholder={quote ? "Comment on this passage" : "Comment on this page"} rows={2} value={body} onChange={(e) => setBody(e.target.value)} />
            <Button type="submit" size="sm" disabled={!body.trim()} loading={busy} className="self-end">Comment</Button>
          </form>
        ) : (
          <p className="mb-4 text-xs text-muted">You can read comments on this page. Ask an editor for comment access to add your own.</p>
        )}
        {error ? (
          <p className="text-sm text-danger-text">Couldn&apos;t load comments.</p>
        ) : !data ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : open.length === 0 ? (
          <p className="text-sm text-muted">No open comments.</p>
        ) : (
          <ul aria-label="Open comments" className="flex flex-col gap-3">
            {open.map((c) => <Thread key={c.id} root={c} replies={data.filter((r) => r.parent_comment_id === c.id)} level={level} pageId={pageId} onChanged={changed} />)}
          </ul>
        )}
        {done.length > 0 && (
          <div className="mt-4">
            <Button variant="ghost" size="sm" aria-expanded={showResolved} onClick={() => setShowResolved(!showResolved)}>
              {showResolved ? "Hide" : "Show"} {done.length} resolved
            </Button>
            {showResolved && (
              <ul aria-label="Resolved comments" className="mt-2 flex flex-col gap-3 opacity-80">
                {done.map((c) => <Thread key={c.id} root={c} replies={data!.filter((r) => r.parent_comment_id === c.id)} level={level} pageId={pageId} onChanged={changed} />)}
              </ul>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
