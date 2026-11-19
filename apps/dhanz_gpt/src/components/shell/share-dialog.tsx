"use client";

import { Check, Copy, Link2 } from "lucide-react";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import type { ConversationDetail } from "@/lib/data/types";
import { Button } from "@/components/ui/button";
import { Banner, useToast } from "@/components/ui/feedback";
import { Dialog } from "@/components/ui/overlays";
import { TextInput } from "@/components/ui/field";

export function ShareDialog({ conversationId, open, onOpenChange }: { conversationId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const key = `/api/conversations/${conversationId}`;
  const { data } = useSWR<ConversationDetail>(open ? key : null);
  const toast = useToast();
  const [busy, setBusy] = useState<"create" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const share = data?.share;
  const url = share ? `${typeof window !== "undefined" ? window.location.origin : ""}/s/${share.slug}` : "";
  const stale = share && data && new Date(data.conversation.last_message_at) > new Date(share.updated_at);

  async function create() {
    setBusy("create");
    setError(null);
    try {
      await api.share(conversationId);
      await mutate(key);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  async function copy() {
    await navigator.clipboard?.writeText(url).catch(() => {});
    setCopied(true);
    toast({ title: "Link copied" });
    setTimeout(() => setCopied(false), 2000);
  }
  async function remove() {
    if (!share) return;
    setBusy("delete");
    await api.deleteShare(share.slug);
    await mutate(key);
    setBusy(null);
    toast({ title: "Link deleted. Anyone who had it can no longer open it." });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Share chat"
      description="People in your workspace with the link can read this chat as it is right now. Later messages aren't included until you update the link."
    >
      <div className="flex flex-col gap-4">
        {error && <Banner tone="danger" title="Couldn't create the link">{error}</Banner>}
        {!data ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : share ? (
          <>
            <TextInput label="Link" readOnly value={url} className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
            <p className="text-xs text-muted">
              {stale ? "This chat has new messages since you shared it. " : ""}Last updated {new Date(share.updated_at).toLocaleString()}.
            </p>
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="ghost" onClick={remove} loading={busy === "delete"}>Delete link</Button>
              {stale && <Button variant="secondary" onClick={create} loading={busy === "create"}>Update link</Button>}
              <Button onClick={copy} icon={copied ? <Check className="size-4" /> : <Copy className="size-4" />}>{copied ? "Copied" : "Copy link"}</Button>
            </div>
          </>
        ) : (
          <div className="flex justify-end">
            <Button onClick={create} loading={busy === "create"} icon={<Link2 className="size-4" />}>Create link</Button>
          </div>
        )}
      </div>
    </Dialog>
  );
}
