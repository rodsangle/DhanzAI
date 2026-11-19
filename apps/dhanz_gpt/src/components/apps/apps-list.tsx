"use client";

import { Check, LayoutGrid } from "lucide-react";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import { cn, focusRing } from "@/lib/cn";
import { Button, button } from "@/components/ui/button";
import { Badge, Skeleton, useToast } from "@/components/ui/feedback";
import { Select, TextInput } from "@/components/ui/field";
import { Dialog } from "@/components/ui/overlays";

export type AppItem = {
  id: "google_drive" | "slack" | "shopify";
  name: string;
  description: string;
  can: string[];
  mentions: string[];
  needs_shop: boolean;
  configured: boolean;
  connection: { id: string; account: string; permission_level: "always_ask" | "any_changes" | "important" | "never_ask"; status: string; always_allowed: string[] } | null;
};

const LEVELS = [
  { value: "always_ask", label: "Ask before every action" },
  { value: "any_changes", label: "Ask before anything that changes something" },
  { value: "important", label: "Ask before important actions (posting, editing the store)" },
  { value: "never_ask", label: "Never ask" },
] as const;

function AppCard({ a }: { a: AppItem }) {
  const toast = useToast();
  const [shop, setShop] = useState("");
  const [confirm, setConfirm] = useState(false);
  const c = a.connection;
  const active = c?.status === "active";
  const connectHref = `/api/apps/${a.id}/connect`;
  async function setLevel(level: string) {
    try {
      await api.setAppPermission(c!.id, level);
      await mutate("/api/apps");
      toast({ title: "Saved." });
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    }
  }
  async function remove() {
    try {
      await api.disconnectApp(c!.id);
      await mutate("/api/apps");
      setConfirm(false);
      toast({ title: `${a.name} disconnected.` });
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    }
  }
  const headingId = `app-${a.id}`;
  return (
    <li aria-labelledby={headingId} className="flex flex-col gap-3 rounded-xl border border-border p-4">
      <div className="flex items-start gap-3">
        <span aria-hidden className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-muted"><LayoutGrid className="size-5" /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h2 id={headingId} className="flex items-center gap-2 font-medium">
            {a.name}
            {active && <Badge tone="success">Connected</Badge>}
            {c && !active && <Badge tone="warning">Needs reconnecting</Badge>}
          </h2>
          <p className="text-sm text-muted">{a.description}</p>
        </div>
      </div>
      <ul className="flex flex-col gap-1 text-sm">
        {a.can.map((x) => (
          <li key={x} className="flex items-center gap-2"><Check aria-hidden className="size-4 text-muted" /> {x}</li>
        ))}
      </ul>
      {!a.configured ? (
        <p className="text-sm text-muted">Not set up for this workspace yet. An admin adds the {a.name} app credentials (see backend.md).</p>
      ) : c ? (
        <div className="flex flex-col gap-3 border-t border-border pt-3">
          <p className="text-sm">
            {active ? "Connected as" : "Was connected as"} <span className="font-medium">{c.account}</span>.
            {active && <> Mention <span className="font-medium">@{a.mentions[0]}</span> in a chat to use it.</>}
          </p>
          {active && <Select label="When to ask you first" value={c.permission_level} onChange={(e) => setLevel(e.target.value)}>
            {LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
          </Select>}
          {active && c.always_allowed.length > 0 && <p className="text-xs text-muted">Always allowed: {c.always_allowed.join(", ").replace(/_/g, " ")}. Changing the setting above resets this.</p>}
          <div className="flex justify-end gap-2">
            {!active && <a href={a.needs_shop ? `${connectHref}?shop=${encodeURIComponent(c.account)}` : connectHref} className={cn(button({ variant: "primary", size: "sm" }), focusRing)}>Reconnect</a>}
            <Button size="sm" variant="ghost" onClick={() => setConfirm(true)}>Disconnect</Button>
          </div>
          <Dialog
            open={confirm}
            onOpenChange={setConfirm}
            title={`Disconnect ${a.name}?`}
            description="The assistant can't use it until you connect it again. Chats that used it stay."
            size="sm"
            footer={
              <>
                <Button variant="secondary" onClick={() => setConfirm(false)}>Cancel</Button>
                <Button variant="danger" onClick={remove}>Disconnect</Button>
              </>
            }
          />
        </div>
      ) : a.needs_shop ? (
        <form action={connectHref} method="get" className="flex flex-wrap items-end gap-2 border-t border-border pt-3">
          <div className="min-w-56 flex-1">
            <TextInput label="Store address" name="shop" placeholder="your-store.myshopify.com" value={shop} onChange={(e) => setShop(e.target.value)} required />
          </div>
          <Button type="submit" size="sm">Connect</Button>
        </form>
      ) : (
        <div className="flex justify-end border-t border-border pt-3">
          <a href={connectHref} className={cn(button({ variant: "primary", size: "sm" }), focusRing)}>Connect<span className="sr-only"> {a.name}</span></a>
        </div>
      )}
    </li>
  );
}

/** S20: every app, connected or not. Used on the Apps page and in Settings → Apps. */
export function AppsList() {
  const { data } = useSWR<AppItem[]>("/api/apps");
  if (!data) return <div aria-busy="true" className="flex flex-col gap-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}</div>;
  return <ul aria-label="Apps" className="flex flex-col gap-3">{data.map((a) => <AppCard key={a.id} a={a} />)}</ul>;
}
