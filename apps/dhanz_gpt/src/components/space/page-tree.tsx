"use client";

import { BRAND } from "@/lib/brand";
import { ChevronRight, FilePlus2, FileText, FolderPlus, Lock, MoreHorizontal, Settings2, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import { cn, focusRing } from "@/lib/cn";
import { Button, IconButton } from "@/components/ui/button";
import { Skeleton, useToast } from "@/components/ui/feedback";
import { Dialog } from "@/components/ui/overlays";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/overlays";
import { RadioGroup } from "@/components/ui/controls";
import { TextInput } from "@/components/ui/field";
import type { Level, PageNode, SpaceSummary } from "@/lib/data/space-types";
import { ShareAccessDialog } from "./share-access-dialog";

export type SpacesData = { spaces: SpaceSummary[]; pages: PageNode[] };
export const SPACES_KEY = "/api/spaces";

export const untitled = (t: string) => t.trim() || "Untitled";

async function postJson<T>(url: string, data: unknown): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((json as { error?: string }).error ?? "That didn’t go through. Try again.");
  return json as T;
}

/** Create a page (top level in a space, or under a parent) and open it. */
export function useNewPage() {
  const router = useRouter();
  const toast = useToast();
  return async (where: { space_id?: string; parent_page_id?: string }) => {
    try {
      const page = await postJson<{ id: string }>("/api/pages", where);
      await mutate(SPACES_KEY);
      router.push(`/space/${page.id}`);
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    }
  };
}

function Branch({
  node, all, depth, activeId, open, toggle, onNew,
}: {
  node: PageNode; all: PageNode[]; depth: number; activeId?: string;
  open: Set<string>; toggle: (id: string) => void; onNew: (parent: string) => void;
}) {
  const kids = all.filter((p) => p.parent_page_id === node.id);
  const expanded = open.has(node.id);
  const active = node.id === activeId;
  return (
    <li role="treeitem" aria-expanded={kids.length ? expanded : undefined} aria-selected={active} aria-level={depth + 1}>
      <div
        className={cn("group flex h-8 items-center gap-0.5 rounded-md pr-1 text-sm hover:bg-surface-hover", active && "bg-surface-active font-medium")}
        style={{ paddingLeft: `${depth * 14 + 2}px` }}
      >
        {kids.length ? (
          <button
            type="button"
            tabIndex={-1}
            aria-label={expanded ? `Collapse ${untitled(node.title)}` : `Expand ${untitled(node.title)}`}
            onClick={() => toggle(node.id)}
            className="flex size-6 shrink-0 items-center justify-center rounded-sm text-muted hover:bg-surface-active"
          >
            <ChevronRight aria-hidden className={cn("size-3.5 transition-transform", expanded && "rotate-90")} />
          </button>
        ) : (
          <span aria-hidden className="flex size-6 shrink-0 items-center justify-center text-muted"><FileText className="size-3.5" /></span>
        )}
        <Link
          href={`/space/${node.id}`}
          aria-current={active ? "page" : undefined}
          className={cn("min-w-0 flex-1 truncate rounded-sm px-1 py-1", !node.title.trim() && "text-muted", focusRing)}
        >
          {untitled(node.title)}
        </Link>
        {node.level !== "edit" && <span className="sr-only">, {node.level === "view" ? "view only" : "can comment"}</span>}
        {node.level === "edit" && (
          <IconButton
            label={`Add a page inside ${untitled(node.title)}`}
            size="sm"
            tooltip={false}
            onClick={() => onNew(node.id)}
            className="opacity-0 focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
          >
            <FilePlus2 />
          </IconButton>
        )}
      </div>
      {kids.length > 0 && expanded && (
        <ul role="group">
          {kids.map((k) => <Branch key={k.id} node={k} all={all} depth={depth + 1} activeId={activeId} open={open} toggle={toggle} onNew={onNew} />)}
        </ul>
      )}
    </li>
  );
}

function SpaceSettings({ space, onClose }: { space: SpaceSummary; onClose: () => void }) {
  const toast = useToast();
  const router = useRouter();
  const [name, setName] = useState(space.name);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  async function save() {
    setBusy(true);
    const res = await fetch(`/api/spaces/${space.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
    setBusy(false);
    if (!res.ok) return toast({ title: (await res.json().catch(() => ({}))).error ?? "Couldn't rename the space.", tone: "error" });
    await mutate(SPACES_KEY);
    onClose();
  }
  async function remove() {
    setBusy(true);
    const res = await fetch(`/api/spaces/${space.id}`, { method: "DELETE" });
    setBusy(false);
    if (!res.ok) return toast({ title: (await res.json().catch(() => ({}))).error ?? "Couldn't delete the space.", tone: "error" });
    toast({ title: `Deleted ${space.name}` });
    await mutate(SPACES_KEY);
    onClose();
    router.push("/space");
  }
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="Space settings"
      footer={
        <>
          {!space.is_personal && (
            confirm ? (
              <Button variant="danger" loading={busy} onClick={remove}>Delete space and its pages</Button>
            ) : (
              <Button variant="ghost" className="mr-auto text-danger-text" onClick={() => setConfirm(true)}>Delete space…</Button>
            )
          )}
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={busy} onClick={save} disabled={!name.trim()}>Save</Button>
        </>
      }
    >
      <TextInput label="Name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
      {confirm && <p role="alert" className="mt-3 text-sm text-danger-text">Every page in {space.name} will be deleted for everyone. This can&apos;t be undone.</p>}
    </Dialog>
  );
}

function NewSpace({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [who, setWho] = useState<"me" | "view" | "comment" | "edit">("edit");
  const [busy, setBusy] = useState(false);
  async function create() {
    setBusy(true);
    try {
      await postJson("/api/spaces", { name, everyone_level: who === "me" ? null : who });
      await mutate(SPACES_KEY);
      toast({ title: `Created ${name.trim()}` });
      onClose();
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title="New space"
      description="A space groups pages for a team, a drop or a campaign."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={busy} onClick={create} disabled={!name.trim()}>Create space</Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <TextInput label="Name" placeholder="e.g. FW26 drop" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} autoFocus />
        <RadioGroup
          label="Who can open it"
          value={who}
          onValueChange={(v) => setWho(v as typeof who)}
          options={[
            { value: "edit", label: `${BRAND.everyone} can edit` },
            { value: "comment", label: `${BRAND.everyone} can comment` },
            { value: "view", label: `${BRAND.everyone} can view` },
            { value: "me", label: "Only people I add" },
          ]}
        />
      </div>
    </Dialog>
  );
}

const levelNote = (s: SpaceSummary) =>
  s.is_personal ? "Private" : s.everyone_level ? `Everyone can ${s.everyone_level}` : s.level === null ? "Shared pages" : s.is_owner ? "People you add" : `Shared by ${s.owner_name}`;

/** S12 left pane: spaces and their page trees. */
export function PageTree({ activeId, ancestors = [] }: { activeId?: string; ancestors?: string[] }) {
  const { data, error } = useSWR<SpacesData>(SPACES_KEY);
  const newPage = useNewPage();
  const [opened, setOpened] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [settings, setSettings] = useState<SpaceSummary | null>(null);
  const [sharing, setSharing] = useState<SpaceSummary | null>(null);
  // The open page's ancestors are always expanded.
  const open = useMemo(() => new Set([...opened, ...ancestors]), [opened, ancestors]);
  const toggle = (id: string) => setOpened((s) => {
    const n = new Set(s);
    if (open.has(id)) { n.delete(id); for (const a of ancestors) if (a === id) n.delete(a); } else n.add(id);
    return n;
  });

  if (error) return <p className="p-3 text-sm text-danger-text">Couldn&apos;t load your pages. Refresh to try again.</p>;
  if (!data) return <div className="flex flex-col gap-2 p-3" aria-busy="true">{[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-7" />)}</div>;

  const visible = new Set(data.pages.map((p) => p.id));
  return (
    <nav aria-label="Pages" className="flex flex-col gap-4 p-2">
      {data.spaces.map((s) => {
        // Top of the tree for this space: real roots, plus shared pages whose parent you can't see.
        const roots = data.pages.filter((p) => p.space_id === s.id && (!p.parent_page_id || !visible.has(p.parent_page_id)));
        const canAdd = s.level === "edit";
        return (
          <section key={s.id} aria-labelledby={`sp-${s.id}`}>
            <div className="group flex items-center gap-1 px-1">
              <h2 id={`sp-${s.id}`} className="min-w-0 flex-1 truncate text-xs font-semibold text-muted">
                {s.name}
                <span className="ml-1.5 font-normal">
                  {s.is_personal ? <Lock aria-hidden className="inline size-3" /> : <Users aria-hidden className="inline size-3" />}
                  <span className="sr-only">, {levelNote(s)}</span>
                </span>
              </h2>
              {canAdd && (
                <IconButton label={`New page in ${s.name}`} size="sm" onClick={() => newPage({ space_id: s.id })}>
                  <FilePlus2 />
                </IconButton>
              )}
              {s.is_owner && (
                <Menu>
                  <MenuTrigger asChild>
                    <IconButton label={`${s.name} options`} size="sm"><MoreHorizontal /></IconButton>
                  </MenuTrigger>
                  <MenuContent align="end">
                    {!s.is_personal && <MenuItem icon={<Users />} onSelect={() => setSharing(s)}>Share space</MenuItem>}
                    <MenuItem icon={<Settings2 />} onSelect={() => setSettings(s)}>Rename or delete</MenuItem>
                  </MenuContent>
                </Menu>
              )}
            </div>
            {roots.length ? (
              <ul role="tree" aria-labelledby={`sp-${s.id}`} className="mt-1 flex flex-col">
                {roots.map((p) => (
                  <Branch key={p.id} node={p} all={data.pages} depth={0} activeId={activeId} open={open} toggle={toggle} onNew={(parent) => newPage({ parent_page_id: parent })} />
                ))}
              </ul>
            ) : (
              <p className="px-2 py-1.5 text-xs text-muted">{canAdd ? "No pages yet." : "Nothing shared with you here yet."}</p>
            )}
          </section>
        );
      })}
      <Button variant="ghost" size="sm" icon={<FolderPlus className="size-4" />} onClick={() => setCreating(true)} className="justify-start">
        New space
      </Button>
      {creating && <NewSpace onClose={() => setCreating(false)} />}
      {settings && <SpaceSettings space={settings} onClose={() => setSettings(null)} />}
      {sharing && <ShareAccessDialog target={{ space_id: sharing.id }} title={sharing.name} onClose={() => setSharing(null)} />}
    </nav>
  );
}

export type { Level };
