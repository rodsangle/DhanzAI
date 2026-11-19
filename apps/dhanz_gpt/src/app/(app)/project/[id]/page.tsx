"use client";

import { FileText, FolderOpen, MoreHorizontal, Settings2, Trash2, Upload, Users, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import useSWR, { mutate } from "swr";
import { api, ApiError, fileUrl, uploadFile } from "@/lib/api";
import type { Profile, ProjectDetail } from "@/lib/data/types";
import { cn, focusRing } from "@/lib/cn";
import { Button, IconButton } from "@/components/ui/button";
import { Avatar, Badge, Banner, EmptyState, Skeleton, useToast } from "@/components/ui/feedback";
import { Dialog, DialogClose, Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/overlays";
import { Textarea, TextInput } from "@/components/ui/field";
import { PageHeader } from "@/components/shell/app-shell";
import { ChatView } from "@/components/chat/chat-view";
import { groupByDate } from "@/components/shell/sidebar";

/* S10 Project settings: name, instructions, delete */
function ProjectSettings({ detail, open, onOpenChange }: { detail: ProjectDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const p = detail.project;
  const [confirm, setConfirm] = useState(false);
  const router = useRouter();
  const toast = useToast();

  async function remove() {
    await api.deleteProject(p.id);
    mutate("/api/projects");
    mutate("/api/conversations");
    toast({ title: `Deleted “${p.name}”` });
    router.push("/");
  }

  const chatCount = detail.conversations.length;
  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange} title="Project settings" description="Instructions apply to every chat in this project, for everyone in it.">
        {/* Radix unmounts dialog content when closed, so the form re-reads the project each time it opens. */}
        <SettingsForm detail={detail} onDone={() => onOpenChange(false)} onDelete={() => setConfirm(true)} />
      </Dialog>
      <Dialog
        open={confirm}
        onOpenChange={setConfirm}
        size="sm"
        title={`Delete “${p.name}”?`}
        description={`This also deletes ${chatCount} ${chatCount === 1 ? "chat" : "chats"} in the project, for everyone it's shared with. Files stay in your Library.`}
        footer={
          <>
            <DialogClose asChild><Button variant="secondary" autoFocus>Cancel</Button></DialogClose>
            <Button variant="danger" onClick={remove}>Delete project and chats</Button>
          </>
        }
      />
    </>
  );
}

function SettingsForm({ detail, onDone, onDelete }: { detail: ProjectDetail; onDone: () => void; onDelete: () => void }) {
  const p = detail.project;
  const [name, setName] = useState(p.name);
  const [instructions, setInstructions] = useState(p.instructions);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.updateProject(p.id, { name, instructions });
      await mutate(`/api/projects/${p.id}`);
      mutate("/api/projects");
      onDone();
      toast({ title: "Project saved" });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
        <form onSubmit={save} className="flex flex-col gap-4">
          {error && <Banner tone="danger" title="Couldn't save">{error}</Banner>}
          <TextInput label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} disabled={!detail.can_edit} />
          <Textarea
            label="Instructions"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={8}
            maxLength={20000}
            disabled={!detail.can_edit}
            placeholder="How should the assistant write and think in this project? For example, brand voice, audience, words to avoid."
            hint={`${instructions.length.toLocaleString()} / 20,000`}
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            {detail.is_owner ? (
              <Button variant="ghost" className="text-danger-text" icon={<Trash2 className="size-4" />} onClick={onDelete}>Delete project</Button>
            ) : <span />}
            <div className="flex gap-2">
              <DialogClose asChild><Button variant="secondary">Cancel</Button></DialogClose>
              {detail.can_edit && <Button type="submit" loading={saving}>Save</Button>}
            </div>
          </div>
        </form>
  );
}

function ShareProject({ detail, open, onOpenChange }: { detail: ProjectDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const { data: people } = useSWR<(Profile & { role: string })[]>(open ? "/api/members" : null);
  const toast = useToast();
  const p = detail.project;
  async function set(userId: string, role: "viewer" | "editor" | null) {
    try {
      await api.setProjectMember(p.id, userId, role);
      mutate(`/api/projects/${p.id}`);
      mutate("/api/projects");
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Share project" description="Teammates you add can see every chat and file in this project. Editors can also start chats and change instructions.">
      <ul className="flex flex-col gap-1">
        {people?.filter((x) => x.id !== p.owner_id).map((person) => {
          const member = detail.members.find((m) => m.user_id === person.id);
          return (
            <li key={person.id} className="flex items-center gap-3 py-1.5">
              <Avatar name={person.name} />
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm font-medium">{person.name}</span>
                <span className="truncate text-xs text-muted">{person.email}</span>
              </div>
              <select
                aria-label={`Access for ${person.name}`}
                value={member?.role ?? "none"}
                disabled={!detail.is_owner}
                onChange={(e) => set(person.id, e.target.value === "none" ? null : (e.target.value as "viewer" | "editor"))}
                className={cn("h-9 rounded-md border border-border-input bg-bg px-2 text-sm", focusRing)}
              >
                <option value="none">No access</option>
                <option value="viewer">Can view</option>
                <option value="editor">Can edit</option>
              </select>
            </li>
          );
        })}
        {people && people.length <= 1 && <li className="text-sm text-muted">No one else is in the workspace yet.</li>}
      </ul>
      {!detail.is_owner && <p className="mt-3 text-xs text-muted">Only the project owner can change who has access.</p>}
    </Dialog>
  );
}

function FilesPanel({ detail }: { detail: ProjectDetail }) {
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<{ name: string; pct: number }[]>([]);
  const toast = useToast();
  const p = detail.project;

  async function add(files: File[]) {
    for (const f of files) {
      setUploading((u) => [...u, { name: f.name, pct: 0 }]);
      try {
        const row = await uploadFile(f, (pct) => setUploading((u) => u.map((x) => (x.name === f.name ? { ...x, pct } : x))));
        if (row.status !== "ready") throw new ApiError(400, row.error ?? "Upload failed");
        await api.addProjectFile(p.id, row.id);
        mutate(`/api/projects/${p.id}`);
      } catch (e) {
        toast({ title: `${f.name}: ${(e as Error).message}`, tone: "error" });
      } finally {
        setUploading((u) => u.filter((x) => x.name !== f.name));
      }
    }
  }

  return (
    <section aria-labelledby="files-h" className="flex flex-col gap-3 rounded-xl border border-border p-4">
      <div className="flex items-center justify-between">
        <h2 id="files-h" className="text-sm font-semibold">Files <span className="font-normal text-muted">({detail.files.length})</span></h2>
        {detail.can_edit && (
          <>
            <Button size="sm" variant="secondary" icon={<Upload className="size-4" />} onClick={() => input.current?.click()}>Add files</Button>
            <input ref={input} type="file" multiple hidden onChange={(e) => { if (e.target.files) add(Array.from(e.target.files)); e.target.value = ""; }} />
          </>
        )}
      </div>
      {detail.files.length === 0 && uploading.length === 0 && (
        <p className="text-sm text-muted">Add briefs, brand guides or product sheets. Every chat in this project can use them.</p>
      )}
      <ul className="flex flex-col gap-1">
        {detail.files.map((f) => (
          <li key={f.id} className="group flex items-center gap-2 rounded-md px-1 py-1 hover:bg-surface-hover">
            <FileText aria-hidden className="size-4 shrink-0 text-muted" />
            <a href={fileUrl(f.id, false)} className={cn("min-w-0 flex-1 truncate text-sm hover:underline", focusRing)}>{f.name}</a>
            {detail.can_edit && (
              <IconButton
                label={`Remove ${f.name} from project`}
                size="sm"
                className="opacity-0 focus-visible:opacity-100 group-hover:opacity-100"
                onClick={async () => { await api.removeProjectFile(p.id, f.id); mutate(`/api/projects/${p.id}`); }}
              >
                <X />
              </IconButton>
            )}
          </li>
        ))}
        {uploading.map((u) => (
          <li key={u.name} className="flex items-center gap-2 px-1 py-1 text-sm text-muted" role="status">
            <Upload aria-hidden className="size-4" /> {u.name} · {u.pct}%
          </li>
        ))}
      </ul>
    </section>
  );
}

// S09 Project
export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, isLoading } = useSWR<ProjectDetail>(`/api/projects/${id}`);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  if (error) {
    return (
      <main id="main" className="flex flex-1 items-center justify-center px-4">
        <div className="max-w-md">
          <Banner tone="danger" title={(error as ApiError).status === 404 ? "Project not found" : "Couldn't load this project"}>
            {(error as Error).message} <Link className="underline" href="/">Go home</Link>
          </Banner>
        </div>
      </main>
    );
  }

  const p = data?.project;
  return (
    <main id="main" className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <PageHeader
        left={
          isLoading || !p ? <Skeleton className="h-6 w-40" /> : (
            <h1 className="flex min-w-0 items-center gap-2 px-2 text-lg font-semibold">
              <FolderOpen aria-hidden className="size-5 shrink-0 text-muted" />
              <span className="truncate">{p.name}</span>
            </h1>
          )
        }
        right={
          data && (
            <>
              {data.members.length > 0 && (
                <span className="mr-1 hidden items-center -space-x-2 sm:flex" aria-label={`Shared with ${data.members.map((m) => m.name).join(", ")}`}>
                  {data.members.slice(0, 3).map((m) => <Avatar key={m.id} name={m.name} size={24} />)}
                </span>
              )}
              <Button variant="ghost" size="sm" icon={<Users className="size-4" />} onClick={() => setShareOpen(true)}>Share</Button>
              <Menu>
                <MenuTrigger asChild><IconButton label="Project options"><MoreHorizontal /></IconButton></MenuTrigger>
                <MenuContent align="end">
                  <MenuItem icon={<Settings2 />} onSelect={() => setSettingsOpen(true)}>Project settings</MenuItem>
                  {data.is_owner && (<><MenuSeparator /><MenuItem icon={<Trash2 />} destructive onSelect={() => setSettingsOpen(true)}>Delete project…</MenuItem></>)}
                </MenuContent>
              </Menu>
            </>
          )
        }
      />
      <div className="mx-auto flex w-full max-w-[var(--thread-max-width)] flex-col gap-6 px-4 pb-10">
        {data && (
          <>
            {data.can_edit ? (
              <ChatView key={`project-${id}`} projectId={id} projectName={p!.name} embedded />
            ) : (
              <Banner tone="info" title="View only">You can read this project&apos;s chats. Ask the owner for edit access to start new ones.</Banner>
            )}
            <button
              onClick={() => setSettingsOpen(true)}
              className={cn("flex flex-col gap-1 rounded-xl border border-border p-4 text-left hover:bg-surface-hover", focusRing)}
            >
              <span className="flex items-center justify-between text-sm font-semibold">
                Instructions {data.can_edit && <span className="text-xs font-normal text-muted">Edit</span>}
              </span>
              <span className="line-clamp-3 text-sm text-muted">
                {p!.instructions || "No instructions yet. Tell the assistant how to write and think for this project."}
              </span>
            </button>
            <FilesPanel detail={data} />
            <section aria-labelledby="chats-h" className="flex flex-col gap-2">
              <h2 id="chats-h" className="text-sm font-semibold">Chats in this project</h2>
              {data.conversations.length === 0 ? (
                <EmptyState icon={<FolderOpen />} title="No chats yet">Start one above. It&apos;ll use this project&apos;s instructions and files.</EmptyState>
              ) : (
                groupByDate(data.conversations).map(([label, items]) => (
                  <div key={label} className="flex flex-col">
                    <h3 className="px-1 pb-1 pt-2 text-xs font-semibold text-muted">{label}</h3>
                    <ul className="flex flex-col divide-y divide-border rounded-xl border border-border">
                      {items.map((c) => (
                        <li key={c.id}>
                          <Link href={`/c/${c.id}`} className={cn("flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-surface-hover", focusRing, "focus-visible:outline-offset-0")}>
                            <span className="truncate">{c.title}</span>
                            <span className="flex shrink-0 items-center gap-2 text-xs text-muted">
                              {c.streaming && <Badge tone="info">Answering</Badge>}
                              {new Date(c.last_message_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))
              )}
            </section>
            <ProjectSettings detail={data} open={settingsOpen} onOpenChange={setSettingsOpen} />
            <ShareProject detail={data} open={shareOpen} onOpenChange={setShareOpen} />
          </>
        )}
        {isLoading && (
          <div role="status" className="flex flex-col gap-4" aria-busy="true" aria-label="Loading project">
            <Skeleton className="h-28 w-full rounded-xl" />
            <Skeleton className="h-20 w-full rounded-xl" />
          </div>
        )}
      </div>
    </main>
  );
}
