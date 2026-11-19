"use client";

import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import Placeholder from "@tiptap/extension-placeholder";
import {
  Bold, FilePlus2, Heading2, Italic, List, ListOrdered, MessageSquare, MessageSquareText, MoreHorizontal, Quote, Share2, Sparkles, Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import useSWR, { mutate } from "swr";
import { cn, focusRing } from "@/lib/cn";
import { pageExtensions } from "@/lib/page-schema";
import type { PageDetail } from "@/lib/data/space-types";
import { Button, IconButton } from "@/components/ui/button";
import { Banner, useToast } from "@/components/ui/feedback";
import { Dialog, Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/overlays";
import { Textarea } from "@/components/ui/field";
import { CommentsPanel } from "./comments-panel";
import { ShareAccessDialog } from "./share-access-dialog";
import { SPACES_KEY, untitled, useNewPage } from "./page-tree";

type SaveState = "saved" | "dirty" | "saving" | "conflict" | "error";
type PageState = { version: number; title: string; updated_by_name: string | null; people: { user_id: string; name: string; editing: boolean }[]; open_comments: number };
type Conflict = { by: string; doc: PageDetail["page"]["doc"]; version: number; title: string };
type Proposal = { html: string; scope: "selection" | "page"; from: number; to: number; instruction: string };

const SAVE_DELAY = 800;
const now = () => Date.now();
const POLL_MS = 4000;

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error((body as { error?: string }).error ?? "That didn’t go through. Try again."), { status: res.status, body });
  return body as T;
}

function ToolbarButton({ label, active, onClick, children }: { label: string; active?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <IconButton label={label} size="sm" aria-pressed={active} onClick={onClick} className={cn(active && "bg-surface-active")}>
      {children}
    </IconButton>
  );
}

function Toolbar({ editor }: { editor: Editor }) {
  const c = () => editor.chain().focus();
  return (
    <div role="toolbar" aria-label="Formatting" className="flex flex-wrap items-center gap-0.5">
      <ToolbarButton label="Bold" active={editor.isActive("bold")} onClick={() => c().toggleBold().run()}><Bold /></ToolbarButton>
      <ToolbarButton label="Italic" active={editor.isActive("italic")} onClick={() => c().toggleItalic().run()}><Italic /></ToolbarButton>
      <ToolbarButton label="Heading" active={editor.isActive("heading", { level: 2 })} onClick={() => c().toggleHeading({ level: 2 }).run()}><Heading2 /></ToolbarButton>
      <ToolbarButton label="Bulleted list" active={editor.isActive("bulletList")} onClick={() => c().toggleBulletList().run()}><List /></ToolbarButton>
      <ToolbarButton label="Numbered list" active={editor.isActive("orderedList")} onClick={() => c().toggleOrderedList().run()}><ListOrdered /></ToolbarButton>
      <ToolbarButton label="Quote" active={editor.isActive("blockquote")} onClick={() => c().toggleBlockquote().run()}><Quote /></ToolbarButton>
    </div>
  );
}

function Presence({ people }: { people: PageState["people"] }) {
  if (!people.length) return null;
  const names = people.map((p) => `${p.name}${p.editing ? " (editing)" : ""}`).join(", ");
  return (
    <div className="flex items-center gap-1.5" aria-label={`Also here: ${names}`} role="group">
      <div className="flex -space-x-1.5" aria-hidden>
        {people.slice(0, 4).map((p) => (
          <span
            key={p.user_id}
            title={`${p.name}${p.editing ? " is editing" : " is viewing"}`}
            className={cn(
              "flex size-7 items-center justify-center rounded-full border-2 border-bg bg-surface-active text-xs font-semibold",
              p.editing && "outline outline-2 outline-accent",
            )}
          >
            {p.name.slice(0, 1).toUpperCase()}
          </span>
        ))}
      </div>
      <span className="hidden text-xs text-muted lg:inline">{people.length === 1 ? `${people[0].name} is ${people[0].editing ? "editing" : "here"}` : `${people.length} others here`}</span>
    </div>
  );
}

function AskAi({ editor, pageId, onPropose, onClose }: { editor: Editor; pageId: string; onPropose: (p: Proposal) => void; onClose: () => void }) {
  const toast = useToast();
  const { from, to, empty } = editor.state.selection;
  const selected = empty ? "" : editor.state.doc.textBetween(from, to, "\n\n");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const suggestions = selected
    ? ["Make it shorter", "Turn into a bulleted list", "Make it punchier and more direct"]
    : ["Tighten the whole page", "Add a heading for each section", "Turn into a one-page brief"];
  async function run(text: string) {
    setBusy(true);
    try {
      const out = await json<{ html: string; scope: "selection" | "page" }>(
        await fetch(`/api/pages/${pageId}/ai`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ instruction: text, selection: selected || null }),
        }),
      );
      onPropose({ html: out.html, scope: out.scope, from: selected ? from : 0, to: selected ? to : editor.state.doc.content.size, instruction: text });
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
      title="Ask AI to edit"
      description={selected ? "Changes the selected passage. You'll see the result before anything changes." : "Changes the whole page. You'll see the result before anything changes."}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button icon={<Sparkles className="size-4" />} loading={busy} disabled={!instruction.trim()} onClick={() => run(instruction)}>Suggest edit</Button>
        </>
      }
    >
      {selected && (
        <blockquote className="mb-3 max-h-28 overflow-y-auto border-l-2 border-border-strong pl-2 text-sm text-muted">{selected}</blockquote>
      )}
      <Textarea
        label="What should change?"
        rows={3}
        value={instruction}
        autoFocus
        onChange={(e) => setInstruction(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && instruction.trim()) run(instruction);
        }}
      />
      <ul aria-label="Suggestions" className="mt-3 flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <li key={s}>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => { setInstruction(s); run(s); }}>{s}</Button>
          </li>
        ))}
      </ul>
    </Dialog>
  );
}

/** S12 page: title, rich text, autosave, live updates from teammates, AI edits, comments, sharing. */
export function PageEditor({ id }: { id: string }) {
  const router = useRouter();
  const toast = useToast();
  const newPage = useNewPage();
  const { data, error, mutate: reload } = useSWR<PageDetail>(`/api/pages/${id}`, { revalidateOnFocus: false });
  // Unique per editor: Next keeps the previous page mounted (hidden), so fixed ids would collide.
  const uid = useId();
  const titleId = `${uid}-title`;
  const subpagesId = `${uid}-subpages`;
  const level = data?.level;
  const canEdit = level === "edit";

  const version = useRef<number | null>(null);
  const dirty = useRef(false);
  const typingAt = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  const titleTimer = useRef<number | undefined>(undefined);
  const [save, setSaveState] = useState<SaveState>("saved");
  // Mirrors for the poll callback, which outlives a render.
  const saveStateRef = useRef<SaveState>("saved");
  const setSave = (v: SaveState) => { saveStateRef.current = v; setSaveState(v); };
  const saveRef = useRef<(force?: boolean) => Promise<void>>(async () => {});
  const [conflict, setConflictState] = useState<Conflict | null>(null);
  const conflictRef = useRef<Conflict | null>(null);
  const setConflict = (c: Conflict | null) => { conflictRef.current = c; setConflictState(c); };
  const [title, setTitle] = useState("");
  const [liveNote, setLiveNote] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [comments, setComments] = useState(false);
  const [quote, setQuote] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const editor = useEditor({
    extensions: [...pageExtensions, Placeholder.configure({ placeholder: "Start writing, or use Ask AI to draft…" })],
    editable: false,
    immediatelyRender: false,
    editorProps: { attributes: { class: "page-content", "aria-label": "Page content", role: "textbox", "aria-multiline": "true" } },
    onUpdate: () => {
      dirty.current = true;
      typingAt.current = now();
      setSave("dirty");
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void saveRef.current(), SAVE_DELAY);
    },
  });

  // The title loads as soon as the page does (before the editor is ready), and never over something typed.
  const titleFor = useRef<string | null>(null);
  const pendingTitle = useRef<string | null>(null);
  useEffect(() => {
    if (!data || titleFor.current === data.page.id) return;
    titleFor.current = data.page.id;
    if (pendingTitle.current === null) setTitle(data.page.title);
  }, [data]);

  // Load the page into the editor once per page (and when someone else's version is pulled in).
  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!editor || !data) return;
    if (loadedFor.current !== data.page.id) {
      loadedFor.current = data.page.id;
      editor.commands.setContent(data.page.doc as never, { emitUpdate: false });
      version.current = data.page.version;
      dirty.current = false;
      setSave("saved");
      setConflict(null);
      setProposal(null);
    }
    // No update event: making the editor editable isn't an edit (it would mark the page unsaved).
    if (editor.isEditable !== (data.level === "edit")) editor.setEditable(data.level === "edit", false);
  }, [editor, data]);

  const saveDoc = useCallback(async (force = false) => {
    if (!editor || !canEdit || version.current === null) return;
    if (!dirty.current && !force) return;
    setSave("saving");
    dirty.current = false;
    try {
      const out = await json<{ version: number }>(
        await fetch(`/api/pages/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ doc: editor.getJSON(), text: editor.getText({ blockSeparator: "\n\n" }), base_version: version.current, force }),
        }),
      );
      version.current = out.version;
      setSave(dirty.current ? "dirty" : "saved");
      setConflict(null);
    } catch (e) {
      const err = e as Error & { status?: number; body?: { latest?: { version: number; doc: Conflict["doc"]; title: string; updated_by_name: string | null } } };
      dirty.current = true;
      if (err.status === 409 && err.body?.latest) {
        const l = err.body.latest;
        setConflict({ by: l.updated_by_name ?? "Someone", doc: l.doc, version: l.version, title: l.title });
        setSave("conflict");
      } else {
        setSave("error");
        toast({ title: err.message, tone: "error" });
      }
    }
  }, [editor, canEdit, id, toast]);
  useEffect(() => { saveRef.current = saveDoc; }, [saveDoc]);

  // Leaving with unsaved typing: save now, and warn if a save can't finish.
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty.current || save === "saving" || save === "conflict") e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [save]);
  useEffect(() => () => {
    window.clearTimeout(timer.current);
    if (dirty.current) void saveDoc();
    if (pendingTitle.current !== null) {
      window.clearTimeout(titleTimer.current);
      void saveTitle(pendingTitle.current);
    }
    void fetch(`/api/pages/${id}/state`, { method: "DELETE", keepalive: true }).catch(() => {});
  }, [id, saveDoc]);

  // Presence heartbeat + live updates: every few seconds, say we're here and check the version.
  const editorRef = useRef(editor);
  useEffect(() => { editorRef.current = editor; }, [editor]);
  async function onState(st: PageState) {
    const ed = editorRef.current;
    if (!ed || version.current === null) return;
    if (st.title !== title && !titleTimer.current && document.activeElement?.id !== titleId) setTitle(st.title);
    if (st.version <= version.current || saveStateRef.current === "saving") return;
    if (dirty.current) {
      // You're mid-edit: say so now rather than at the next save.
      if (!conflictRef.current) {
        setConflict({ by: st.updated_by_name ?? "Someone", doc: null as never, version: st.version, title: st.title });
        setSave("conflict");
      }
      return;
    }
    // Nobody typing here: take their version in place, keeping the cursor near where it was.
    const fresh = await reload();
    if (!fresh || dirty.current) return;
    const pos = ed.state.selection.from;
    ed.commands.setContent(fresh.page.doc as never, { emitUpdate: false });
    try { ed.commands.setTextSelection(Math.min(pos, ed.state.doc.content.size)); } catch { /* the document got shorter */ }
    version.current = fresh.page.version;
    setTitle(fresh.page.title);
    setLiveNote(`Updated by ${fresh.page.updated_by_name ?? "a teammate"}`);
    mutate(SPACES_KEY);
  }
  const { data: state } = useSWR<PageState>(
    data ? `/api/pages/${id}/state` : null,
    async (url: string) => json<PageState>(await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ editing: canEdit && now() - typingAt.current < 10_000 }),
    })),
    { refreshInterval: POLL_MS, revalidateOnFocus: true, onSuccess: (st) => void onState(st) },
  );
  useEffect(() => {
    if (!liveNote) return;
    const t = window.setTimeout(() => setLiveNote(null), 4000);
    return () => window.clearTimeout(t);
  }, [liveNote]);

  async function takeTheirs() {
    const fresh = await reload();
    if (!fresh || !editor) return;
    editor.commands.setContent(fresh.page.doc as never, { emitUpdate: false });
    version.current = fresh.page.version;
    dirty.current = false;
    setTitle(fresh.page.title);
    setConflict(null);
    setSave("saved");
  }
  async function keepMine() {
    await saveDoc(true);
  }

  async function saveTitle(v: string) {
    pendingTitle.current = null;
    titleTimer.current = undefined;
    const res = await fetch(`/api/pages/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: v }), keepalive: true });
    if (!res.ok) toast({ title: (await res.json().catch(() => ({}))).error ?? "Couldn't save the title.", tone: "error" });
    // The tree and any open parent page (its "Pages inside" list) show titles.
    mutate(SPACES_KEY);
    mutate((key) => typeof key === "string" && key.startsWith("/api/pages/") && !key.endsWith("/state") && key !== `/api/pages/${id}`);
  }
  function onTitle(v: string) {
    setTitle(v);
    pendingTitle.current = v;
    window.clearTimeout(titleTimer.current);
    titleTimer.current = window.setTimeout(() => void saveTitle(v), 600);
  }

  function accept() {
    if (!editor || !proposal) return;
    if (proposal.scope === "page") editor.commands.setContent(proposal.html, { emitUpdate: true });
    else editor.chain().focus().insertContentAt({ from: proposal.from, to: proposal.to }, proposal.html).run();
    setProposal(null);
    toast({ title: "Edit applied" });
  }

  function commentOnSelection() {
    if (!editor) return;
    const { from, to, empty } = editor.state.selection;
    setQuote(empty ? null : editor.state.doc.textBetween(from, to, " ").slice(0, 1000));
    setComments(true);
  }

  async function remove() {
    const res = await fetch(`/api/pages/${id}`, { method: "DELETE" });
    if (!res.ok) return toast({ title: (await res.json().catch(() => ({}))).error ?? "Couldn't delete the page.", tone: "error" });
    const out = (await res.json()) as { deleted: number; parent_page_id: string | null };
    dirty.current = false;
    await mutate(SPACES_KEY);
    toast({ title: out.deleted > 1 ? `Deleted the page and ${out.deleted - 1} inside it` : "Deleted the page" });
    router.push(out.parent_page_id ? `/space/${out.parent_page_id}` : "/space");
  }

  if (error) {
    return (
      <div className="mx-auto mt-24 max-w-md px-6 text-center">
        <h1 className="text-xl font-semibold">{(error as { status?: number }).status === 404 || /exist/.test((error as Error).message) ? "Page not found" : "Couldn't open this page"}</h1>
        <p className="mt-2 text-sm text-muted">It may have been deleted, or it isn&apos;t shared with you. Ask the person who sent it for access.</p>
        <Link href="/space" className={cn("mt-4 inline-block text-sm text-accent-text underline underline-offset-2", focusRing)}>Back to your pages</Link>
      </div>
    );
  }

  const saveLabel = !canEdit
    ? level === "comment" ? "You can comment" : "View only"
    : save === "saving" ? "Saving…" : save === "dirty" ? "Unsaved changes" : save === "error" ? "Not saved" : save === "conflict" ? "Not saved" : "Saved";

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Left padding on narrow screens leaves room for the "Show pages" button. */}
        <header className="flex h-[var(--header-height)] shrink-0 items-center justify-between gap-2 pl-14 pr-3 md:pl-3">
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 text-sm text-muted">
            {data && (
              <>
                <span className="truncate">{data.space.name}</span>
                {data.breadcrumbs.map((b) => (
                  <span key={b.id} className="flex min-w-0 items-center gap-1">
                    <span aria-hidden>/</span>
                    <Link href={`/space/${b.id}`} className={cn("max-w-40 truncate hover:text-fg", focusRing)}>{untitled(b.title)}</Link>
                  </span>
                ))}
              </>
            )}
          </nav>
          <div className="flex shrink-0 items-center gap-1">
            {state && <Presence people={state.people} />}
            <span role="status" aria-live="polite" className="hidden px-2 text-xs text-muted sm:inline">{liveNote ?? saveLabel}</span>
            {data && level !== "view" && (
              <Button variant="ghost" size="sm" icon={<MessageSquare className="size-4" />} onClick={() => (comments ? setComments(false) : commentOnSelection())} aria-pressed={comments}>
                <span className="hidden sm:inline">Comments</span>
                {!!state?.open_comments && <span className="ml-0.5 rounded-full bg-surface-active px-1.5 text-xs">{state.open_comments}<span className="sr-only"> open</span></span>}
              </Button>
            )}
            {data && level === "view" && (
              <IconButton label="Comments" onClick={() => setComments(!comments)}><MessageSquare /></IconButton>
            )}
            {data && (
              <Button variant="ghost" size="sm" icon={<Share2 className="size-4" />} onClick={() => setSharing(true)}>
                <span className="hidden sm:inline">Share</span>
              </Button>
            )}
            {data && canEdit && (
              <Menu>
                <MenuTrigger asChild>
                  <IconButton label="Page options"><MoreHorizontal /></IconButton>
                </MenuTrigger>
                <MenuContent align="end">
                  <MenuItem icon={<FilePlus2 />} onSelect={() => newPage({ parent_page_id: id })}>Add a page inside</MenuItem>
                  {data.page.source_conversation_id && (
                    <MenuItem icon={<MessageSquareText />} onSelect={() => router.push(`/c/${data.page.source_conversation_id}`)}>Open the chat it came from</MenuItem>
                  )}
                  <MenuSeparator />
                  <MenuItem icon={<Trash2 />} onSelect={() => setDeleting(true)}>Delete page</MenuItem>
                </MenuContent>
              </Menu>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto">
          <article className="mx-auto w-full max-w-3xl px-6 pb-24 pt-6 sm:px-10">
            {conflict && (
              <div className="mb-4">
                <Banner
                  tone="warning"
                  title={`${conflict.by} changed this page while you were editing`}
                  action={
                    <span className="flex shrink-0 gap-2">
                      <Button size="sm" variant="secondary" onClick={takeTheirs}>Use their version</Button>
                      <Button size="sm" onClick={keepMine}>Keep mine</Button>
                    </span>
                  }
                >
                  Your latest changes aren&apos;t saved. Use their version to drop yours, or keep yours to replace theirs.
                </Banner>
              </div>
            )}
            {!data ? (
              <div aria-busy="true" className="flex flex-col gap-4">
                <div className="h-10 w-2/3 animate-shimmer rounded-md bg-surface-muted" />
                <div className="h-4 w-full animate-shimmer rounded-md bg-surface-muted" />
                <div className="h-4 w-5/6 animate-shimmer rounded-md bg-surface-muted" />
              </div>
            ) : (
              <>
                <label htmlFor={titleId} className="sr-only">Page title</label>
                <input
                  id={titleId}
                  value={title}
                  readOnly={!canEdit}
                  maxLength={300}
                  placeholder="Untitled"
                  onChange={(e) => onTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      editor?.commands.focus("start");
                    }
                  }}
                  className="w-full bg-transparent text-3xl font-semibold leading-tight text-fg outline-hidden placeholder:text-subtle"
                />
                {canEdit && editor && (
                  <div className="sticky top-0 z-[1] -mx-2 mt-3 flex items-center justify-between gap-2 border-b border-border bg-bg px-2 py-1.5">
                    <Toolbar editor={editor} />
                    <Button size="sm" variant="secondary" icon={<Sparkles className="size-4" />} onClick={() => setAsking(true)}>Ask AI</Button>
                  </div>
                )}
                {proposal && (
                  <section aria-label="Suggested edit" className="mt-4 rounded-lg border border-accent bg-surface-raised p-4">
                    <p className="mb-2 text-xs font-medium text-muted">
                      Suggested {proposal.scope === "selection" ? "replacement for the selection" : "new version of the page"}: “{proposal.instruction}”
                    </p>
                    {/* Server-made HTML from Markdown with raw tags escaped and unsafe links removed. */}
                    <div className="page-content max-h-96 min-h-0 overflow-y-auto" dangerouslySetInnerHTML={{ __html: proposal.html }} />
                    <div className="mt-3 flex justify-end gap-2">
                      <Button size="sm" variant="secondary" onClick={() => setProposal(null)}>Discard</Button>
                      <Button size="sm" onClick={accept}>Accept</Button>
                    </div>
                  </section>
                )}
                <div className="mt-4">
                  <EditorContent editor={editor} />
                </div>
                {data.children.length > 0 && (
                  <section aria-labelledby={subpagesId} className="mt-10 border-t border-border pt-4">
                    <h2 id={subpagesId} className="text-xs font-semibold text-muted">Pages inside</h2>
                    <ul className="mt-2 flex flex-col gap-1">
                      {data.children.map((c) => (
                        <li key={c.id}>
                          <Link href={`/space/${c.id}`} className={cn("text-sm text-accent-text underline-offset-2 hover:underline", focusRing)}>{untitled(c.title)}</Link>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </>
            )}
          </article>
        </div>
      </div>

      {comments && data && (
        <div className="fixed inset-0 z-20 md:static md:z-auto md:flex">
          <CommentsPanel pageId={id} level={data.level} quote={quote} onQuoteUsed={() => setQuote(null)} onClose={() => { setComments(false); setQuote(null); }} />
        </div>
      )}
      {asking && editor && <AskAi editor={editor} pageId={id} onPropose={(p) => { setProposal(p); setAsking(false); }} onClose={() => setAsking(false)} />}
      {sharing && data && <ShareAccessDialog target={{ page_id: id }} title={title} onClose={() => setSharing(false)} />}
      {deleting && (
        <Dialog
          open
          onOpenChange={(o) => !o && setDeleting(false)}
          title="Delete this page?"
          description={data?.children.length ? "Pages inside it are deleted too, for everyone." : "It's deleted for everyone who can see it."}
          footer={
            <>
              <Button variant="secondary" onClick={() => setDeleting(false)}>Cancel</Button>
              <Button variant="danger" onClick={remove}>Delete</Button>
            </>
          }
        />
      )}
    </div>
  );
}
