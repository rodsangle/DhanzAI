"use client";

import { BRAND } from "@/lib/brand";
import {
  Archive, Bot, CalendarClock, FileStack, FolderOpen, FolderPlus, Images, LayoutGrid, Library, LogOut, MoreHorizontal, PanelLeftClose,
  PanelLeftOpen, Pencil, Search, Settings, Share, SquarePen, Trash2,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { DropdownMenu as M } from "radix-ui";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import type { ConversationListItem } from "@/lib/data/types";
import { cn, focusRing } from "@/lib/cn";
import { Button, IconButton } from "@/components/ui/button";
import { Avatar, Skeleton, useToast } from "@/components/ui/feedback";
import { Dialog, DialogClose, Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/overlays";
import { TextInput } from "@/components/ui/field";
import { Tooltip } from "@/components/ui/tooltip";
import { useUI } from "./providers";
import { ShareDialog } from "./share-dialog";

type ProjectItem = { id: string; name: string; shared: boolean };

/** Groups chats the way people think about time: Today, Yesterday, Previous 7 days, Previous 30 days, then months. */
export function groupByDate(items: ConversationListItem[]) {
  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);
  const day = 86_400_000;
  const groups = new Map<string, ConversationListItem[]>();
  for (const it of items) {
    const t = new Date(it.last_message_at).getTime();
    const label =
      t >= startOfDay.getTime() ? "Today"
      : t >= startOfDay.getTime() - day ? "Yesterday"
      : t >= startOfDay.getTime() - 7 * day ? "Previous 7 days"
      : t >= startOfDay.getTime() - 30 * day ? "Previous 30 days"
      : new Date(t).toLocaleDateString(undefined, { month: "long", year: "numeric" });
    groups.set(label, [...(groups.get(label) ?? []), it]);
  }
  return [...groups.entries()];
}

function NavLink({ href, icon, label, collapsed, onClick, badge }: { href: string; icon: ReactNode; label: string; collapsed: boolean; onClick?: () => void; badge?: number }) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname.startsWith(href));
  const link = (
    <Link
      href={href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed || badge ? `${label}${badge ? `, ${badge} new` : ""}` : undefined}
      className={cn(
        "flex h-9 items-center gap-2.5 rounded-md px-2 text-sm text-fg transition-colors hover:bg-surface-hover aria-[current=page]:bg-surface-active [&_svg]:size-[18px] [&_svg]:shrink-0",
        collapsed && "justify-center px-0",
        focusRing, "focus-visible:outline-offset-0",
      )}
    >
      <span className="relative flex">
        {icon}
        {!!badge && collapsed && <span aria-hidden className="absolute -right-1 -top-1 size-2 rounded-full bg-accent" />}
      </span>
      {!collapsed && <span className="flex-1 truncate">{label}</span>}
      {!!badge && !collapsed && (
        <span aria-hidden className="min-w-5 rounded-full bg-accent px-1.5 text-center text-xs font-medium leading-5 text-on-accent">{badge > 9 ? "9+" : badge}</span>
      )}
    </Link>
  );
  return collapsed ? <Tooltip label={label} side="right">{link}</Tooltip> : link;
}

function ChatItem({ item, projects, onNavigate }: { item: ConversationListItem; projects: ProjectItem[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const toast = useToast();
  const active = pathname === `/c/${item.id}`;
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [sharing, setSharing] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (renaming) input.current?.select();
  }, [renaming]);

  async function commitRename() {
    setRenaming(false);
    const next = title.trim();
    if (!next || next === item.title) return setTitle(item.title);
    try {
      await api.updateConversation(item.id, { title: next });
      mutate("/api/conversations");
      mutate(`/api/conversations/${item.id}`);
    } catch (e) {
      setTitle(item.title);
      toast({ title: (e as Error).message, tone: "error" });
    }
  }

  async function move(projectId: string | null) {
    await api.updateConversation(item.id, { project_id: projectId });
    mutate("/api/conversations");
    mutate((k) => typeof k === "string" && k.startsWith("/api/projects/"));
    toast({ title: projectId ? `Moved to ${projects.find((p) => p.id === projectId)?.name}` : "Removed from project" });
  }

  async function archive() {
    await api.updateConversation(item.id, { archived: true });
    mutate("/api/conversations");
    toast({
      title: "Chat archived",
      action: { label: "Undo", onClick: () => api.updateConversation(item.id, { archived: false }).then(() => mutate("/api/conversations")) },
    });
    if (active) router.push("/");
  }

  async function remove() {
    await api.deleteConversation(item.id);
    setConfirmDelete(false);
    mutate("/api/conversations");
    toast({ title: "Chat deleted" });
    if (active) router.push("/");
  }

  if (renaming) {
    return (
      <li className="px-0.5 py-px">
        <label htmlFor={`rename-${item.id}`} className="sr-only">Chat name</label>
        <input
          id={`rename-${item.id}`}
          ref={input}
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            if (e.key === "Escape") {
              setTitle(item.title);
              setRenaming(false);
            }
          }}
          className="h-9 w-full rounded-md border border-focus bg-bg px-2 text-sm text-fg outline-none"
        />
      </li>
    );
  }

  return (
    <li className="group relative">
      <Link
        href={`/c/${item.id}`}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex h-9 items-center gap-2 rounded-md px-2 pr-9 text-sm text-fg transition-colors hover:bg-surface-hover aria-[current=page]:bg-surface-active",
          focusRing, "focus-visible:outline-offset-0",
        )}
      >
        <span className="min-w-0 flex-1 overflow-hidden whitespace-nowrap [mask-image:linear-gradient(to_right,black_85%,transparent)]">
          {item.title}
        </span>
        {item.streaming && <span aria-label="Answering" className="size-1.5 shrink-0 animate-pulse rounded-full bg-fg motion-reduce:animate-none" />}
      </Link>
      <Menu>
        <MenuTrigger asChild>
          <IconButton
            label={`Options for ${item.title}`}
            size="sm"
            tooltip={false}
            className="absolute right-0.5 top-0.5 opacity-0 focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100 group-has-[[aria-current=page]]:opacity-100"
          >
            <MoreHorizontal />
          </IconButton>
        </MenuTrigger>
        <MenuContent align="start">
          <MenuItem icon={<Share />} onSelect={() => setSharing(true)}>Share</MenuItem>
          <MenuItem icon={<Pencil />} onSelect={() => setRenaming(true)}>Rename</MenuItem>
          <M.Sub>
            <M.SubTrigger className="flex min-h-9 cursor-default select-none items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-surface-hover data-[state=open]:bg-surface-hover [&_svg]:size-4">
              <FolderOpen /> Move to project
            </M.SubTrigger>
            <M.Portal>
              <M.SubContent sideOffset={6} className="z-[var(--z-dropdown)] min-w-48 rounded-lg bg-surface-raised p-1.5 text-fg shadow-md">
                {projects.length === 0 && <p className="px-2.5 py-2 text-sm text-muted">No projects yet</p>}
                {projects.map((p) => (
                  <MenuItem key={p.id} onSelect={() => move(p.id)} disabled={p.id === item.project_id}>{p.name}</MenuItem>
                ))}
                {item.project_id && (
                  <>
                    <MenuSeparator />
                    <MenuItem onSelect={() => move(null)}>Remove from project</MenuItem>
                  </>
                )}
              </M.SubContent>
            </M.Portal>
          </M.Sub>
          <MenuItem icon={<Archive />} onSelect={archive}>Archive</MenuItem>
          <MenuSeparator />
          <MenuItem icon={<Trash2 />} destructive onSelect={() => setConfirmDelete(true)}>Delete</MenuItem>
        </MenuContent>
      </Menu>
      <Dialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        size="sm"
        title="Delete this chat?"
        description={`“${item.title}” will be deleted for good, along with any share link. This can't be undone.`}
        footer={
          <>
            <DialogClose asChild><Button variant="secondary" autoFocus>Cancel</Button></DialogClose>
            <Button variant="danger" onClick={remove}>Delete</Button>
          </>
        }
      />
      {sharing && <ShareDialog conversationId={item.id} open onOpenChange={setSharing} />}
    </li>
  );
}

function NewProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const p = await api.createProject(name);
      mutate("/api/projects");
      onOpenChange(false);
      setName("");
      router.push(`/project/${p.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="sm" title="New project" description="Keep chats, files and instructions for one piece of work together.">
      <form onSubmit={create} className="flex flex-col gap-4">
        <TextInput label="Project name" placeholder="e.g. SS27 campaign" value={name} onChange={(e) => setName(e.target.value)} error={error} autoFocus maxLength={120} />
        <div className="flex justify-end gap-2">
          <DialogClose asChild><Button variant="secondary">Cancel</Button></DialogClose>
          <Button type="submit" loading={busy} disabled={!name.trim()}>Create project</Button>
        </div>
      </form>
    </Dialog>
  );
}

export function SidebarContent({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const { setSidebarOpen, sidebarOpen, setSearchOpen, openSettings, me } = useUI();
  const { data: chats, error } = useSWR<ConversationListItem[]>("/api/conversations", { refreshInterval: (d) => (d?.some((c) => c.streaming) ? 1500 : 0) });
  const { data: projects } = useSWR<ProjectItem[]>("/api/projects");
  const [newProject, setNewProject] = useState(false);
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col bg-surface">
      <div className={cn("flex h-[var(--header-height)] shrink-0 items-center px-2", collapsed ? "justify-center" : "justify-between")}>
        {!collapsed && (
          <Link href="/" onClick={onNavigate} className={cn("rounded-md px-2 text-sm font-semibold tracking-wide", focusRing)}>
            {BRAND.name} <span className="font-normal text-muted">by {BRAND.company}</span>
          </Link>
        )}
        <IconButton
          label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
          className="hidden md:inline-flex"
          onClick={() => setSidebarOpen(!sidebarOpen)}
        >
          {sidebarOpen ? <PanelLeftClose /> : <PanelLeftOpen />}
        </IconButton>
      </div>

      <nav aria-label="Main" className="flex flex-col gap-px px-2">
        <NavLink href="/" icon={<SquarePen />} label="New chat" collapsed={collapsed} onClick={onNavigate} />
        {collapsed ? (
          <Tooltip label="Search chats" side="right">
            <button onClick={() => setSearchOpen(true)} aria-label="Search chats" className={cn("flex h-9 items-center justify-center rounded-md text-fg hover:bg-surface-hover [&_svg]:size-[18px]", focusRing)}>
              <Search />
            </button>
          </Tooltip>
        ) : (
          <button
            onClick={() => setSearchOpen(true)}
            className={cn("flex h-9 items-center gap-2.5 rounded-md px-2 text-sm text-fg hover:bg-surface-hover [&_svg]:size-[18px]", focusRing, "focus-visible:outline-offset-0")}
          >
            <Search /> <span className="flex-1 text-left">Search chats</span>
            <kbd className="font-sans text-xs text-muted">⌘K</kbd>
          </button>
        )}
        <NavLink href="/images" icon={<Images />} label="Images" collapsed={collapsed} onClick={onNavigate} />
        <NavLink href="/library" icon={<Library />} label="Library" collapsed={collapsed} onClick={onNavigate} />
        <NavLink href="/space" icon={<FileStack />} label="Space" collapsed={collapsed} onClick={onNavigate} />
        <NavLink href="/scheduled" icon={<CalendarClock />} label="Scheduled" collapsed={collapsed} onClick={onNavigate} badge={me?.unseen_task_runs} />
        <NavLink href="/apps" icon={<LayoutGrid />} label="Apps" collapsed={collapsed} onClick={onNavigate} />
        <NavLink href="/assistants" icon={<Bot />} label="Assistants" collapsed={collapsed} onClick={onNavigate} />
      </nav>

      {!collapsed && (
        <div className="mt-2 flex-1 overflow-y-auto px-2 pb-2" aria-label="Chats and projects">
          <section className="flex flex-col gap-0.5">
            <div className="sticky top-0 z-[1] flex items-center justify-between bg-surface pl-2 pt-3">
              <h2 className="pb-1 text-xs font-semibold text-muted">Projects</h2>
              <IconButton label="New project" size="sm" onClick={() => setNewProject(true)}><FolderPlus /></IconButton>
            </div>
            <ul className="flex flex-col gap-px">
              {projects?.map((p) => (
                <li key={p.id}>
                  <Link
                    href={`/project/${p.id}`}
                    onClick={onNavigate}
                    aria-current={pathname === `/project/${p.id}` ? "page" : undefined}
                    className={cn("flex h-9 items-center gap-2 rounded-md px-2 text-sm hover:bg-surface-hover aria-[current=page]:bg-surface-active [&_svg]:size-4", focusRing, "focus-visible:outline-offset-0")}
                  >
                    <FolderOpen className="text-muted" />
                    <span className="truncate">{p.name}</span>
                  </Link>
                </li>
              ))}
              {projects && projects.length === 0 && (
                <li>
                  <button onClick={() => setNewProject(true)} className={cn("h-9 w-full rounded-md px-2 text-left text-sm text-muted hover:bg-surface-hover", focusRing)}>
                    Start a project
                  </button>
                </li>
              )}
            </ul>
          </section>

          <nav aria-label="Chats" className="flex flex-col">
            {!chats && !error && (
              <div role="status" className="flex flex-col gap-2 px-2 pt-4" aria-busy="true" aria-label="Loading chats">
                {[70, 90, 60, 80].map((w, i) => <Skeleton key={i} className="h-4" />)}
              </div>
            )}
            {error && <p className="px-2 pt-4 text-sm text-danger-text">Couldn&apos;t load your chats.</p>}
            {chats?.length === 0 && <p className="px-2 pt-4 text-sm text-muted">No chats yet. Start one and it lands here.</p>}
            {chats &&
              groupByDate(chats).map(([label, items]) => (
                <section key={label} className="flex flex-col gap-0.5">
                  <h2 className="sticky top-0 z-[1] bg-surface px-2 pb-1 pt-3 text-xs font-semibold text-muted">{label}</h2>
                  <ul className="flex flex-col gap-px">
                    {items.map((c) => <ChatItem key={c.id} item={c} projects={projects ?? []} onNavigate={onNavigate} />)}
                  </ul>
                </section>
              ))}
          </nav>
        </div>
      )}
      {collapsed && <div className="flex-1" />}

      <div className="border-t border-border p-2">
        <Menu>
          <MenuTrigger asChild>
            <button
              className={cn("flex h-11 w-full items-center gap-2.5 rounded-md px-2 text-left hover:bg-surface-hover", collapsed && "justify-center px-0", focusRing)}
              aria-label={collapsed ? "Account" : undefined}
            >
              <Avatar name={me?.profile.name ?? "?"} size={28} />
              {!collapsed && (
                <span className="flex min-w-0 flex-col">
                  <span className="truncate text-sm font-medium">{me?.profile.name ?? " "}</span>
                  <span className="truncate text-xs text-muted">{me?.workspace.name}</span>
                </span>
              )}
            </button>
          </MenuTrigger>
          <MenuContent align="start" className="w-64">
            <div className="px-2.5 py-2">
              <p className="text-sm font-medium">{me?.profile.name}</p>
              <p className="text-xs text-muted">{me?.profile.email}</p>
            </div>
            {me && (
              <div className="px-2.5 pb-2 text-xs text-muted">
                {me.usage.messages} of {me.usage.limits.messages} messages · {me.usage.images} of {me.usage.limits.images} images today
              </div>
            )}
            <MenuSeparator />
            <MenuItem icon={<Settings />} onSelect={() => openSettings("general")}>Settings</MenuItem>
            <MenuItem icon={<Pencil />} onSelect={() => openSettings("personalization")}>Personalization</MenuItem>
            <MenuSeparator />
            <MenuItem icon={<LogOut />} onSelect={() => api.signOut().then(() => (window.location.href = "/login"))}>Sign out</MenuItem>
          </MenuContent>
        </Menu>
      </div>
      <NewProjectDialog open={newProject} onOpenChange={setNewProject} />
    </div>
  );
}
