"use client";

import { BRAND } from "@/lib/brand";
import { X } from "lucide-react";
import { useState } from "react";
import useSWR, { mutate } from "swr";
import { Button, IconButton } from "@/components/ui/button";
import { Badge, useToast } from "@/components/ui/feedback";
import { Dialog } from "@/components/ui/overlays";
import { Select } from "@/components/ui/field";
import type { AccessEntry, Level } from "@/lib/data/space-types";
import { useUI } from "@/components/shell/providers";
import { SPACES_KEY } from "./page-tree";

type Access = {
  owner: { id: string; name: string; email: string };
  everyone_level: Level | null;
  is_personal: boolean;
  can_share: boolean;
  people: AccessEntry[];
};
type Member = { id: string; name: string; email: string };

const LABEL: Record<Level, string> = { view: "Can view", comment: "Can comment", edit: "Can edit" };

/** Share a space or a page with teammates. Page access also applies to every page inside it. */
export function ShareAccessDialog({ target, title, onClose }: { target: { space_id: string } | { page_id: string }; title: string; onClose: () => void }) {
  const toast = useToast();
  const { me } = useUI();
  const base = "space_id" in target ? `/api/spaces/${target.space_id}/access` : `/api/pages/${target.page_id}/access`;
  const { data, error } = useSWR<Access>(base);
  const { data: members } = useSWR<Member[]>("/api/members");
  const [who, setWho] = useState("");
  const [level, setLevel] = useState<Level>("edit");
  const [busy, setBusy] = useState(false);
  const [everyone, setEveryone] = useState<string | null>(null);

  const direct = (data?.people ?? []).filter((p) => !p.inherited_from);
  const inherited = (data?.people ?? []).filter((p) => p.inherited_from);
  const taken = new Set([data?.owner.id, ...direct.map((p) => p.user_id)]);
  const candidates = (members ?? []).filter((m) => !taken.has(m.id) && m.id !== me?.profile.id);

  async function refresh() {
    await Promise.all([mutate(base), mutate(SPACES_KEY)]);
  }
  async function add() {
    if (!who) return;
    setBusy(true);
    const res = await fetch(base, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: who, level }) });
    setBusy(false);
    if (!res.ok) return toast({ title: (await res.json().catch(() => ({}))).error ?? "Couldn't share.", tone: "error" });
    const name = members?.find((m) => m.id === who)?.name ?? "them";
    setWho("");
    toast({ title: `Shared with ${name}` });
    await refresh();
  }
  async function change(p: AccessEntry, next: Level | "remove") {
    const res =
      next === "remove"
        ? await fetch(`/api/page-access/${p.id}`, { method: "DELETE" })
        : await fetch(base, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: p.user_id, level: next }) });
    if (!res.ok) return toast({ title: (await res.json().catch(() => ({}))).error ?? "Couldn't change access.", tone: "error" });
    if (next === "remove") toast({ title: `Removed ${p.name}` });
    await refresh();
  }
  async function setEveryoneLevel(v: string) {
    if (!("space_id" in target)) return;
    setEveryone(v);
    const res = await fetch(`/api/spaces/${target.space_id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ everyone_level: v === "none" ? null : v }),
    });
    if (!res.ok) toast({ title: (await res.json().catch(() => ({}))).error ?? "Couldn't change access.", tone: "error" });
    await refresh();
    setEveryone(null);
  }

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Share “${title || "Untitled"}”`}
      description={"page_id" in target ? "People you add here can also open every page inside this one." : "People you add can open every page in this space."}
      footer={<Button variant="secondary" onClick={onClose}>Done</Button>}
    >
      {error ? (
        <p className="text-sm text-danger-text">{(error as Error).message || "Couldn't load who has access."}</p>
      ) : !data ? (
        <p className="text-sm text-muted" aria-busy="true">Loading…</p>
      ) : (
        <div className="flex flex-col gap-4">
          {data.can_share && ("page_id" in target || !data.is_personal) ? (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <div className="flex-1">
                <Select label="Add a teammate" value={who} onChange={(e) => setWho(e.target.value)}>
                  <option value="">Choose someone…</option>
                  {candidates.map((m) => <option key={m.id} value={m.id}>{m.name} ({m.email})</option>)}
                </Select>
              </div>
              <Select label="Access" hideLabel value={level} onChange={(e) => setLevel(e.target.value as Level)}>
                <option value="edit">Can edit</option>
                <option value="comment">Can comment</option>
                <option value="view">Can view</option>
              </Select>
              <Button onClick={add} loading={busy} disabled={!who}>Share</Button>
            </div>
          ) : !data.can_share ? (
            <p className="text-sm text-muted">Only people who can edit can change who has access.</p>
          ) : null}

          {"space_id" in target && data.can_share && !data.is_personal && (
            <Select
              label={BRAND.everyone}
              value={everyone ?? data.everyone_level ?? "none"}
              onChange={(e) => setEveryoneLevel(e.target.value)}
              disabled={!!everyone || !("space_id" in target) || data.owner.id !== me?.profile.id}
            >
              <option value="none">No access unless added</option>
              <option value="view">Can view</option>
              <option value="comment">Can comment</option>
              <option value="edit">Can edit</option>
            </Select>
          )}

          <ul aria-label="People with access" className="flex flex-col divide-y divide-border rounded-md border border-border">
            <li className="flex items-center justify-between gap-3 px-3 py-2">
              <span className="min-w-0">
                <span className="block truncate text-sm">{data.owner.name}{data.owner.id === me?.profile.id && " (you)"}</span>
                <span className="block truncate text-xs text-muted">{data.owner.email}</span>
              </span>
              <Badge>Owner</Badge>
            </li>
            {data.everyone_level && (
              <li className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span>{BRAND.everyone}</span>
                <span className="text-xs text-muted">{LABEL[data.everyone_level]}{"page_id" in target && " · from the space"}</span>
              </li>
            )}
            {direct.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="min-w-0">
                  <span className="block truncate text-sm">{p.name}</span>
                  <span className="block truncate text-xs text-muted">{p.email}</span>
                </span>
                {data.can_share ? (
                  <span className="flex items-center gap-1">
                    <Select label={`Access for ${p.name}`} hideLabel value={p.level} onChange={(e) => change(p, e.target.value as Level)} className="h-8">
                      <option value="edit">Can edit</option>
                      <option value="comment">Can comment</option>
                      <option value="view">Can view</option>
                    </Select>
                    <IconButton label={`Remove ${p.name}`} size="sm" onClick={() => change(p, "remove")}><X /></IconButton>
                  </span>
                ) : (
                  <span className="text-xs text-muted">{LABEL[p.level]}</span>
                )}
              </li>
            ))}
            {inherited.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="min-w-0">
                  <span className="block truncate text-sm">{p.name}</span>
                  <span className="block truncate text-xs text-muted">From {p.inherited_from === "the space" ? "the space" : `“${p.inherited_from}”`}</span>
                </span>
                <span className="text-xs text-muted">{LABEL[p.level]}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Dialog>
  );
}
