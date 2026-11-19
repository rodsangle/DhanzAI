"use client";

import { BRAND } from "@/lib/brand";
import {
  Bot,
  ArrowDown, Check, ChevronDown, ChevronLeft, ChevronRight, Copy, FilePlus2, FileText, Pencil, RefreshCw, Share, ThumbsDown, ThumbsUp, Upload,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import useSWR, { mutate } from "swr";
import { api, ApiError, fileUrl, uploadFile } from "@/lib/api";
import { streamEvents, type GenEvent } from "@/lib/stream";
import { LIMITS, MODELS, type AssistantDetail, type AssistantListItem, type ContentBlock, type ConversationDetail, type FileRow, type Message } from "@/lib/data/types";
import { cn, focusRing } from "@/lib/cn";
import { Button, IconButton } from "@/components/ui/button";
import { Badge, Banner, useToast } from "@/components/ui/feedback";
import { Menu, MenuCheckItem, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@/components/ui/overlays";
import { PageHeader } from "@/components/shell/app-shell";
import { ShareDialog } from "@/components/shell/share-dialog";
import { useUI } from "@/components/shell/providers";
import { Composer, type Attachment, type ComposerHandle, type SlashCommand } from "./composer";
import { Markdown } from "./markdown";
import { SourcesRow } from "./sources";
import { ApprovalCard, ToolActivity } from "./app-actions";
import { LibraryPicker } from "./library-picker";
import { UsageWarning } from "./usage-warning";
import { useDictation } from "@/lib/dictation";

/* ------------------------------------------------------------------ helpers */

type Live = { text: string; content?: ContentBlock[]; status: Message["status"]; error?: string | null; activity?: string };

function pathTo(messages: Message[], leaf: string | null) {
  const byId = new Map(messages.map((m) => [m.id, m]));
  const out: Message[] = [];
  let cur = leaf ? byId.get(leaf) : undefined;
  while (cur) {
    out.unshift(cur);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return out;
}

/** Newest leaf under `id`, following the most recent child at each step. */
function deepestLeaf(messages: Message[], id: string) {
  let cur = id;
  for (;;) {
    const kids = messages.filter((m) => m.parent_id === cur).sort((a, b) => b.created_at.localeCompare(a.created_at));
    if (!kids.length) return cur;
    cur = kids[0].id;
  }
}

const fmtBytes = (n: number) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);

function kindOf(f: File): Attachment["kind"] {
  if (f.type.startsWith("image/")) return "image";
  if (f.type.startsWith("audio/")) return "audio";
  if (f.name === "Pasted text.txt") return "paste";
  return "document";
}

export const SUGGESTIONS = [
  "Write three captions for a product launch",
  "Draft a polite follow-up email to a client",
  "Plan a checklist for launching on Friday",
  "Create an image of a city street at night",
];

/* ------------------------------------------------------------------ model picker (S06) */

export function ModelPicker({ value, onChange }: { value: string; onChange: (m: string) => void }) {
  const current = MODELS.find((m) => m.id === value) ?? MODELS[0];
  return (
    <Menu>
      <MenuTrigger asChild>
        <button
          aria-label={`Model: ${current.label}. Change model`}
          className={cn("flex h-9 items-center gap-1 rounded-md px-2.5 text-lg font-semibold hover:bg-surface-hover", focusRing)}
        >
          {current.label} <ChevronDown aria-hidden className="size-4 text-muted" />
        </button>
      </MenuTrigger>
      <MenuContent className="w-72">
        <MenuLabel>Model</MenuLabel>
        {MODELS.map((m) => (
          <MenuCheckItem key={m.id} checked={m.id === value} onCheckedChange={() => onChange(m.id)} description={m.description}>
            {m.label}
          </MenuCheckItem>
        ))}
      </MenuContent>
    </Menu>
  );
}

/* ------------------------------------------------------------------ message views */

function Blocks({
  content, text, role, onDecide,
}: {
  content: ContentBlock[];
  text: string;
  role: Message["role"];
  /** The person can answer approval cards on this message. */
  onDecide?: (approvalId: string, decision: "approve" | "always" | "deny") => Promise<void>;
}) {
  const { openSettings } = useUI();
  const media = content.filter((b) => b.type === "image" || b.type === "file_ref");
  const hasTextBlock = content.some((b) => b.type === "text");
  // Users attach first, then write; answers explain first, then show the image.
  const textEl = (hasTextBlock || !content.length) && text ? (role === "user" ? <p className="whitespace-pre-wrap">{text}</p> : <Markdown text={text} />) : null;
  return (
    <div className="flex flex-col gap-3">
      {role === "assistant" && content.map((b, i) => (b.type === "tool_activity" ? <ToolActivity key={`a${i}`} items={b.items} /> : null))}
      {role === "assistant" && textEl}
      {role === "assistant" && content.map((b) => (b.type === "approval" ? <ApprovalCard key={b.approval_id} block={b} onDecide={onDecide} /> : null))}
      {media.length > 0 && (
        <div className={cn("flex flex-wrap gap-2", role === "user" && "justify-end")}>
          {media.map((b) =>
            b.type === "image" ? (
              <a key={b.file_id} href={fileUrl(b.file_id)} target="_blank" rel="noreferrer" className={cn("block overflow-hidden rounded-lg border border-border", focusRing)}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={fileUrl(b.file_id)} alt={b.alt} className={cn("block object-cover", role === "user" ? "max-h-48 max-w-64" : "max-h-[420px] w-full max-w-[420px]")} />
              </a>
            ) : b.type === "file_ref" ? (
              <a key={b.file_id} href={fileUrl(b.file_id, false)} className={cn("flex h-12 items-center gap-2 rounded-md bg-surface-muted px-3 text-sm hover:bg-surface-active", focusRing)}>
                <FileText aria-hidden className="size-4 text-muted" /> {b.name}
              </a>
            ) : null,
          )}
        </div>
      )}
      {role === "user" && textEl}
      {role === "assistant" && content.map((b, i) => (b.type === "sources" ? <SourcesRow key={i} items={b.items} onOpenMemory={() => openSettings("personalization")} /> : null))}
    </div>
  );
}

function BranchNav({ index, total, onPick, kind }: { index: number; total: number; onPick: (i: number) => void; kind: string }) {
  if (total < 2) return null;
  return (
    <div role="group" aria-label={`${kind} version ${index + 1} of ${total}`} className="flex items-center text-xs text-muted">
      <IconButton label="Previous version" size="sm" disabled={index === 0} onClick={() => onPick(index - 1)}><ChevronLeft /></IconButton>
      <span aria-hidden className="tabular-nums">{index + 1} / {total}</span>
      <IconButton label="Next version" size="sm" disabled={index === total - 1} onClick={() => onPick(index + 1)}><ChevronRight /></IconButton>
    </div>
  );
}

/* ------------------------------------------------------------------ ChatView */

export function ChatView({
  conversationId: initialId,
  projectId,
  projectName,
  assistant: assistantProp,
  assistantEditable = false,
  embedded = false,
}: {
  conversationId?: string;
  projectId?: string;
  projectName?: string;
  /** Start a new chat with this assistant (the /assistants/[id] page). */
  assistant?: Pick<AssistantDetail, "id" | "name" | "description" | "starters" | "recommended_model" | "capabilities">;
  assistantEditable?: boolean;
  /** Rendered inside the project page: no header, compact home state. */
  embedded?: boolean;
}) {
  const router = useRouter();
  const toast = useToast();
  const { newChatModel, setNewChatModel, me, pendingFiles, setPendingFiles } = useUI();
  const [libraryOpen, setLibraryOpen] = useState(false);
  const { data: apps } = useSWR<{ id: string; name: string; configured: boolean; connection: { status: string } | null }[]>("/api/apps");
  const { data: assistantList } = useSWR<{ mine: AssistantListItem[]; team: AssistantListItem[] }>("/api/assistants");
  const { data: projectList } = useSWR<{ id: string; name: string }[]>("/api/projects");
  const [convId, setConvId] = useState<string | undefined>(initialId);
  const key = convId ? `/api/conversations/${convId}` : null;
  const { data, error: loadError, isLoading } = useSWR<ConversationDetail>(key);

  const [live, setLive] = useState<Record<string, Live>>({});
  const [liveId, setLiveId] = useState<string | null>(null);
  const [pending, setPending] = useState<{ text: string; attachments: Attachment[] } | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [imageMode, setImageModeRaw] = useState(false);
  const [searchMode, setSearchModeRaw] = useState(false);
  // One tool at a time: turning one on turns the other off.
  const setImageMode = (on: boolean) => { setImageModeRaw(on); if (on) setSearchModeRaw(false); };
  const setSearchMode = (on: boolean) => { setSearchModeRaw(on); if (on) setImageModeRaw(false); };
  const [temporary, setTemporary] = useState(false);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [atBottom, setAtBottom] = useState(true);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<ComposerHandle>(null);
  const following = useRef<Set<string>>(new Set());

  const conversation = data?.conversation;
  const [modelTouched, setModelTouched] = useState(false);
  const model = conversation?.model ?? (assistantProp?.recommended_model && !modelTouched ? assistantProp.recommended_model : newChatModel);
  // The assistant this chat runs with: the one passed in for a new chat, or the saved chat's.
  const assistant = data?.assistant ?? (convId ? null : assistantProp ?? null);
  const canImage = !assistant || assistant.capabilities.includes("image_generation");
  const canSearch = !assistant || assistant.capabilities.includes("web_search");
  const messages = useMemo(() => data?.messages ?? [], [data]);
  const thread = useMemo(() => pathTo(messages, conversation?.current_leaf_id ?? null), [messages, conversation?.current_leaf_id]);
  const canEdit = data ? data.can_edit : true;
  const streamingId = liveId ?? thread.find((m) => m.status === "streaming")?.id ?? null;
  const overLimit = !!me && me.usage.messages >= me.usage.limits.messages;

  const refreshLists = useCallback(() => {
    mutate("/api/conversations");
    mutate("/api/me");
    if (projectId || conversation?.project_id) mutate(`/api/projects/${projectId ?? conversation?.project_id}`);
  }, [projectId, conversation?.project_id]);

  /* ---------------- stream handling */

  const follow = useCallback(
    async (run: (onEvent: (e: GenEvent) => void) => Promise<void>, opts: { onMeta?: (e: Extract<GenEvent, { type: "meta" }>) => Promise<void> } = {}) => {
      let id: string | null = null;
      try {
        await run(async (e) => {
          if (e.type === "meta") {
            id = e.assistant_message_id;
            following.current.add(id);
            setLiveId(id);
            setLive((l) => ({ ...l, [id!]: { text: "", status: "streaming" } }));
            await opts.onMeta?.(e);
          } else if (!id) {
            return;
          } else if (e.type === "snapshot") {
            setLive((l) => ({ ...l, [id!]: { ...l[id!], text: e.text, content: e.content.length ? e.content : undefined } }));
          } else if (e.type === "delta") {
            setLive((l) => ({ ...l, [id!]: { ...l[id!], text: (l[id!]?.text ?? "") + e.text, activity: undefined } }));
          } else if (e.type === "status") {
            setLive((l) => ({ ...l, [id!]: { ...l[id!], activity: e.text } }));
          } else if (e.type === "content") {
            setLive((l) => ({ ...l, [id!]: { ...l[id!], content: e.content } }));
          } else if (e.type === "title") {
            mutate("/api/conversations");
          } else if (e.type === "done") {
            setLive((l) => ({ ...l, [id!]: { ...l[id!], status: e.status, error: e.error } }));
          }
        });
      } catch (err) {
        if ((err as Error).name !== "AbortError") throw err;
      } finally {
        if (id) {
          following.current.delete(id);
          setLiveId((cur) => (cur === id ? null : cur));
          // Always refetch by the live conversation id (this callback may predate a new chat's id).
          if (convIdRef.current) await mutate(`/api/conversations/${convIdRef.current}`);
          setLive((l) => {
            const n = { ...l };
            delete n[id!];
            return n;
          });
          refreshLists();
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [refreshLists],
  );
  const convIdRef = useRef(convId);
  useEffect(() => {
    convIdRef.current = convId;
  }, [convId]);

  // Resume an answer that's still being written (page reload, or opened from another tab).
  // Streams are only aborted on unmount, never on re-render, so a resume can't cancel itself.
  const controllers = useRef<Set<AbortController>>(new Set());
  useEffect(() => {
    const m = thread.find((x) => x.status === "streaming");
    if (!m || following.current.has(m.id)) return;
    following.current.add(m.id);
    const ctl = new AbortController();
    controllers.current.add(ctl);
    void follow((on) =>
      streamEvents(`/api/messages/${m.id}/stream`, undefined, (e) => {
        if (e.type === "snapshot") on({ type: "meta", conversation_id: m.conversation_id, assistant_message_id: m.id });
        on(e);
      }, ctl.signal),
    )
      .catch(() => {
        following.current.delete(m.id);
        // Couldn't reconnect: refetch so the message shows whatever the server finished with.
        if (convIdRef.current) void mutate(`/api/conversations/${convIdRef.current}`);
      })
      .finally(() => controllers.current.delete(ctl));
  }, [thread, follow]);
  useEffect(() => {
    const all = controllers.current;
    return () => all.forEach((c) => c.abort());
  }, []);

  /* ---------------- scrolling */

  useEffect(() => {
    const el = scroller.current;
    if (el && atBottom) el.scrollTop = el.scrollHeight;
  }, [live, thread.length, pending, atBottom]);

  function onScroll() {
    const el = scroller.current;
    if (el) setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 120);
  }
  const scrollToBottom = () => scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });

  /* ---------------- files */

  const addFiles = useCallback((files: File[]) => {
    for (const f of files.slice(0, LIMITS.attachmentsPerMessage)) {
      const id = crypto.randomUUID();
      const base: Attachment = {
        id, name: f.name, kind: kindOf(f), status: "uploading", progress: 0, meta: fmtBytes(f.size),
        previewUrl: f.type.startsWith("image/") ? URL.createObjectURL(f) : undefined,
      };
      if (f.size > LIMITS.fileBytes) {
        setAttachments((a) => [...a, { ...base, status: "error", error: "Over the 512 MB limit" }]);
        continue;
      }
      if (f.size === 0) {
        setAttachments((a) => [...a, { ...base, status: "error", error: "This file is empty" }]);
        continue;
      }
      setAttachments((a) => [...a, base]);
      uploadFile(f, (p) => setAttachments((a) => a.map((x) => (x.id === id ? { ...x, progress: p } : x))), { temporary })
        .then((row) => setAttachments((a) => a.map((x) => (x.id === id ? { ...x, status: row.status === "ready" ? "ready" : "error", fileId: row.id, error: row.error ?? undefined } : x))))
        .catch((e: Error) => setAttachments((a) => a.map((x) => (x.id === id ? { ...x, status: "error", error: e.message } : x))));
    }
    if (files.length > LIMITS.attachmentsPerMessage) toast({ title: `Attach up to ${LIMITS.attachmentsPerMessage} files at a time.`, tone: "error" });
  }, [temporary, toast]);

  /** Files already in the Library: attached as they are, no upload. */
  const addLibraryFiles = useCallback((files: FileRow[]) => {
    setAttachments((cur) => {
      const room = LIMITS.attachmentsPerMessage - cur.length;
      const fresh = files.filter((f) => !cur.some((a) => a.fileId === f.id)).slice(0, Math.max(0, room));
      return [
        ...cur,
        ...fresh.map((f): Attachment => ({
          id: crypto.randomUUID(), name: f.name, status: "ready", fileId: f.id, meta: fmtBytes(f.bytes),
          kind: f.mime.startsWith("image/") ? "image" : f.mime.startsWith("audio/") ? "audio" : "document",
          previewUrl: f.mime.startsWith("image/") ? fileUrl(f.id) : undefined,
        })),
      ];
    });
  }, []);

  // "Use in a chat" from the Library hands files over through the shell: take them while rendering
  // (React's pattern for adjusting state to new input), then clear the hand-off so no other chat takes them.
  const [taken, setTaken] = useState<FileRow[] | null>(null);
  // Only the home page's new chat takes them (other chats may still be mounted, hidden).
  const isHome = !initialId && !projectId && !embedded && !assistantProp;
  if (isHome && canEdit && pendingFiles.length && pendingFiles !== taken) {
    setTaken(pendingFiles);
    addLibraryFiles(pendingFiles);
  }
  useEffect(() => {
    if (taken && pendingFiles === taken) setPendingFiles([]);
  }, [taken, pendingFiles, setPendingFiles]);

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (canEdit && e.dataTransfer.files.length) addFiles(Array.from(e.dataTransfer.files));
  }

  /* ---------------- actions */

  async function send(opts: { text?: string; parentId?: string | null; files?: Attachment[] } = {}) {
    const body = (opts.text ?? text).trim();
    const files = opts.files ?? attachments;
    if (!body && !files.length) return;
    setSendError(null);
    const isNew = !convId;
    if (opts.text === undefined) {
      setText("");
      setAttachments([]);
    }
    setPending({ text: body, attachments: files });
    try {
      await follow(
        (on) =>
          streamEvents(
            "/api/chat",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                conversation_id: convId, project_id: projectId, assistant_id: convId ? undefined : assistantProp?.id, parent_id: opts.parentId, text: body,
                file_ids: files.map((f) => f.fileId).filter(Boolean), model, temporary: isNew ? temporary : undefined,
                tools: { image: imageMode, search: searchMode },
              }),
            },
            on,
          ),
        {
          onMeta: async (e) => {
            if (isNew) {
              setConvId(e.conversation_id);
              convIdRef.current = e.conversation_id;
              if (!embedded) window.history.replaceState(null, "", `/c/${e.conversation_id}`);
            }
            await mutate(`/api/conversations/${e.conversation_id}`);
            setPending(null);
            refreshLists();
          },
        },
      );
      setImageMode(false);
      setSearchMode(false);
      if (isNew && embedded) router.push(`/c/${convIdRef.current}`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Couldn't send. Check your connection and try again.";
      setSendError(msg);
      if (opts.text === undefined) {
        setText(body);
        setAttachments(files);
      }
    } finally {
      setPending(null);
    }
  }

  async function regenerate(m: Message, withModel?: string) {
    setSendError(null);
    try {
      await follow((on) =>
        streamEvents(`/api/messages/${m.id}/regenerate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model: withModel }),
        }, on),
        { onMeta: async () => void (await mutate(key)) },
      );
    } catch (e) {
      setSendError((e as Error).message);
    }
  }

  /** An approval card's answer: the paused answer continues and streams in. */
  async function decide(approvalId: string, decision: "approve" | "always" | "deny") {
    setSendError(null);
    try {
      await follow((on) =>
        streamEvents(`/api/approvals/${approvalId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision }),
        }, on),
      );
    } catch (e) {
      setSendError((e as Error).message);
      await mutate(key);
    }
  }

  async function stop() {
    if (streamingId) await api.stop(streamingId).catch(() => {});
  }

  async function pickSibling(m: Message, i: number) {
    const sibs = messages.filter((x) => x.parent_id === m.parent_id && x.role === m.role).sort((a, b) => a.created_at.localeCompare(b.created_at));
    const target = sibs[i];
    if (!target || !convId || !data) return;
    const leaf = deepestLeaf(messages, target.id);
    await mutate(key, { ...data, conversation: { ...data.conversation, current_leaf_id: leaf } }, { revalidate: false });
    await api.updateConversation(convId, { current_leaf_id: leaf });
  }

  async function changeModel(m: string) {
    if (!convId || !data) {
      setModelTouched(true);
      return setNewChatModel(m);
    }
    await mutate(key, { ...data, conversation: { ...data.conversation, model: m } }, { revalidate: false });
    await api.updateConversation(convId, { model: m });
  }

  async function copy(m: Message, t: string) {
    await navigator.clipboard?.writeText(t).catch(() => {});
    setCopied(m.id);
    setTimeout(() => setCopied(null), 2000);
  }

  async function rate(m: Message, v: 1 | -1) {
    const next = m.feedback === v ? null : v;
    await mutate(key, data && { ...data, messages: data.messages.map((x) => (x.id === m.id ? { ...x, feedback: next } : x)) }, { revalidate: false });
    await api.feedback(m.id, next);
    if (next) toast({ title: "Thanks for the feedback" });
  }

  const lastUser = [...thread].reverse().find((m) => m.role === "user");

  const dictation = useDictation({
    onText: useCallback((t: string) => {
      setText((prev) => (prev.trim() ? `${prev.replace(/\s+$/, "")} ${t}` : t));
      composer.current?.focus();
    }, []),
    onError: useCallback((message: string) => toast({ title: message, tone: "error" }), [toast]),
  });

  const [savingPage, setSavingPage] = useState(false);
  async function saveAsPage() {
    if (!convId) return;
    setSavingPage(true);
    try {
      const res = await fetch("/api/pages/from-conversation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: convId }),
      });
      const out = (await res.json().catch(() => ({}))) as { id?: string; title?: string; error?: string };
      if (!res.ok || !out.id) throw new Error(out.error ?? "The page couldn't be made. Try again.");
      mutate("/api/spaces");
      mutate("/api/me");
      toast({ title: `Saved “${out.title}” to your pages`, action: { label: "Open", onClick: () => router.push(`/space/${out.id}`) } });
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setSavingPage(false);
    }
  }

  /* ---------------- render */

  if (convId && loadError) {
    return (
      <div className="flex flex-1 flex-col">
        {!embedded && <PageHeader />}
        <div className="m-auto max-w-md px-4">
          <Banner tone="danger" title={loadError instanceof ApiError && loadError.status === 404 ? "Chat not found" : "Couldn't load this chat"}>
            {loadError.message} <Link className="underline" href="/">Start a new chat</Link>
          </Banner>
        </div>
      </div>
    );
  }

  const empty = !convId && !pending;
  const header = !embedded && (
    <PageHeader
      left={
        <>
          <ModelPicker value={model} onChange={changeModel} />
          {data?.project && (
            <Link href={`/project/${data.project.id}`} className={cn("hidden truncate rounded-md px-2 text-sm text-muted hover:text-fg sm:block", focusRing)}>
              in {data.project.name}
            </Link>
          )}
          {assistant && (
            <Link href={`/assistants/${assistant.id}`} className={cn("hidden max-w-60 truncate rounded-md px-2 text-sm text-muted hover:text-fg sm:block", focusRing)}>
              with {assistant.name}
            </Link>
          )}
        </>
      }
      right={
        <>
          {!convId && (
            <Button
              variant="ghost"
              size="sm"
              aria-pressed={temporary}
              onClick={() => setTemporary(!temporary)}
              className={cn(temporary && "bg-info-subtle text-info-text hover:bg-info-subtle")}
            >
              {temporary ? "Temporary chat on" : "Temporary chat"}
            </Button>
          )}
          {convId && data?.can_edit && !conversation?.is_temporary && thread.some((m) => m.role === "assistant" && m.status === "complete") && (
            <Button variant="ghost" size="sm" icon={<FilePlus2 className="size-4" />} onClick={saveAsPage} loading={savingPage} disabled={!!streamingId}>
              <span className="hidden sm:inline">Save as a page</span>
              <span className="sr-only sm:hidden">Save as a page</span>
            </Button>
          )}
          {convId && data?.can_edit && !conversation?.is_temporary && (
            <Button variant="ghost" size="sm" icon={<Share className="size-4" />} onClick={() => setSharing(true)} disabled={!!streamingId}>
              Share
            </Button>
          )}
        </>
      }
    />
  );

  const commands: SlashCommand[] = [
    ...(canImage ? [{ id: "image", label: "Create an image", group: "Tools" as const, hint: "/image", run: () => setImageMode(true) }] : []),
    ...(me?.features?.webSearch !== "off" && canSearch
      ? [{ id: "search", label: "Search the web", group: "Tools" as const, hint: "/search", run: () => setSearchMode(true) }]
      : []),
    { id: "library", label: "Add from Library", group: "Tools", hint: "/library", run: () => setLibraryOpen(true) },
    ...(!convId ? [{ id: "temporary", label: "Temporary chat", group: "Tools" as const, hint: "/temporary", run: () => setTemporary(true) }] : []),
    ...[...(assistantList?.mine ?? []), ...(assistantList?.team ?? [])]
      .filter((a, i, all) => all.findIndex((b) => b.id === a.id) === i)
      .map((a) => ({ id: `a-${a.id}`, label: a.name, group: "Assistants" as const, hint: "Assistant", run: () => router.push(`/assistants/${a.id}`) })),
    ...(projectList ?? []).map((p) => ({ id: `p-${p.id}`, label: p.name, group: "Projects" as const, hint: "Project", run: () => router.push(`/project/${p.id}`) })),
  ];

  const composerEl = canEdit ? (
    <>
    <div className="mx-auto mb-2 w-full max-w-[var(--composer-max-width)] empty:hidden">
      <UsageWarning usage={me?.usage} imageMode={imageMode} />
    </div>
    <Composer
      ref={composer}
      variant={empty ? "home" : "thread"}
      value={text}
      onChange={setText}
      onSend={() => send()}
      onStop={stop}
      streaming={!!streamingId || !!pending}
      attachments={attachments}
      onAddFiles={addFiles}
      onRemoveAttachment={(id) => setAttachments((a) => a.filter((x) => x.id !== id))}
      imageMode={imageMode}
      onImageMode={canImage ? setImageMode : undefined}
      searchMode={me?.features?.webSearch === "off" || !canSearch ? null : searchMode}
      onSearchMode={setSearchMode}
      onAddFromLibrary={() => setLibraryOpen(true)}
      mentionApps={(apps ?? []).filter((a) => a.configured).map((a) => ({ label: a.name, connected: a.connection?.status === "active" }))}
      commands={commands}
      dictation={me?.features?.dictation ? dictation : null}
      onLastMessageEdit={lastUser ? () => setEditing({ id: lastUser.id, text: lastUser.text }) : undefined}
      disabled={overLimit}
      disabledReason="You've reached today's message limit. It resets at midnight."
      placeholder={imageMode ? "Describe the image: subject, style, setting" : searchMode ? "What should I look up?" : projectName ? `New chat in ${projectName}` : "Ask, draft, or paste copy to edit"}
    />
    <LibraryPicker
      open={libraryOpen}
      onOpenChange={setLibraryOpen}
      max={LIMITS.attachmentsPerMessage - attachments.length}
      already={attachments.flatMap((a) => (a.fileId ? [a.fileId] : []))}
      onPick={addLibraryFiles}
    />
    </>
  ) : (
    <p className="mx-auto max-w-[var(--composer-max-width)] rounded-lg bg-surface-muted px-4 py-3 text-center text-sm text-muted">
      This chat belongs to a teammate. You can read it, but only they can reply.
    </p>
  );

  return (
    <div
      id={embedded ? undefined : "main"}
      className="relative flex min-h-0 flex-1 flex-col"
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files") && canEdit) {
          e.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={onDrop}
    >
      {header}
      {dragging && (
        <div aria-hidden className="pointer-events-none absolute inset-2 z-10 flex items-center justify-center rounded-xl border-2 border-dashed border-accent bg-bg/80 text-lg font-medium">
          <Upload className="mr-2 size-5" /> Drop files to attach them
        </div>
      )}

      {empty ? (
        <div className={cn("flex flex-1 flex-col items-center justify-center gap-6 px-4", embedded ? "py-6" : "pb-[12vh]")}>
          {!embedded && assistantProp && !temporary ? (
            <div className="flex max-w-md flex-col items-center gap-2 text-center">
              <span aria-hidden className="flex size-12 items-center justify-center rounded-full bg-surface-muted text-muted"><Bot className="size-6" /></span>
              <h1 className="text-3xl font-semibold">{assistantProp.name}</h1>
              {assistantProp.description && <p className="text-sm text-muted">{assistantProp.description}</p>}
              {assistantEditable && (
                <Link href={`/assistants/${assistantProp.id}/edit`} className={cn("text-sm text-accent-text underline-offset-2 hover:underline", focusRing)}>Edit assistant</Link>
              )}
            </div>
          ) : !embedded && (
            <h1 className="text-center text-3xl font-semibold">
              {temporary ? "Temporary chat" : `What are we making today${me ? `, ${me.profile.name.split(" ")[0]}` : ""}?`}
            </h1>
          )}
          {temporary && <p className="-mt-3 max-w-md text-center text-sm text-muted">This chat won&apos;t appear in your history or be used for memory, and its files won&apos;t be saved to your Library.</p>}
          <div className="w-full">{composerEl}</div>
          {sendError && <div className="w-full max-w-[var(--composer-max-width)]"><Banner tone="danger" title="Message not sent">{sendError}</Banner></div>}
          {!embedded && !temporary && assistantProp && assistantProp.starters.length > 0 && (
            <ul className="grid w-full max-w-[var(--composer-max-width)] gap-2 sm:grid-cols-2" aria-label="Conversation starters">
              {assistantProp.starters.map((st) => (
                <li key={st}>
                  <button
                    onClick={() => send({ text: st })}
                    className={cn("h-full w-full rounded-lg border border-border-strong px-3.5 py-2.5 text-left text-sm text-muted hover:bg-surface-hover hover:text-fg", focusRing)}
                  >
                    {st}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {!embedded && !temporary && !assistantProp && (
            <ul className="flex max-w-[var(--composer-max-width)] flex-wrap justify-center gap-2" aria-label="Suggestions">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button
                    onClick={() => {
                      if (s.startsWith("Create an image")) setImageMode(true);
                      setText(s);
                      composer.current?.focus();
                    }}
                    className={cn("rounded-full border border-border-strong px-3.5 py-1.5 text-sm text-muted hover:bg-surface-hover hover:text-fg", focusRing)}
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {!embedded && (
            <p className="max-w-md text-center text-xs text-muted">
              Demo mode: answers come from a built-in sample model until the Claude API is connected.
            </p>
          )}
        </div>
      ) : (
        <>
          <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex w-full max-w-[var(--thread-max-width)] flex-col gap-8 px-4 pb-8 pt-4">
              {conversation?.is_temporary && <Banner tone="info" title="Temporary chat">Not saved to your history. It&apos;s deleted after 30 days.</Banner>}
              {isLoading && !data && (
                <div role="status" aria-busy="true" aria-label="Loading chat" className="flex flex-col gap-6">
                  <div className="ml-auto h-10 w-2/3 animate-shimmer rounded-xl bg-surface-muted" />
                  <div className="h-24 w-full animate-shimmer rounded-md bg-surface-muted" />
                </div>
              )}
              {thread.map((m, idx) => {
                const l = live[m.id];
                const textNow = l?.text ?? m.text;
                const content = l?.content ?? m.content;
                const status = l?.status ?? m.status;
                const err = l?.error ?? m.error;
                const sibs = messages.filter((x) => x.parent_id === m.parent_id && x.role === m.role).sort((a, b) => a.created_at.localeCompare(b.created_at));
                const sibIndex = sibs.findIndex((x) => x.id === m.id);
                const isLast = idx === thread.length - 1;

                if (m.role === "user") {
                  const isEditing = editing?.id === m.id;
                  return (
                    <article key={m.id} className="group flex flex-col items-end gap-1">
                      <h2 className="sr-only">You said:</h2>
                      {isEditing ? (
                        <form
                          className="flex w-full flex-col gap-2 rounded-xl bg-surface-muted p-3"
                          onSubmit={(e) => {
                            e.preventDefault();
                            const t = editing.text.trim();
                            if (!t) return;
                            setEditing(null);
                            void send({ text: t, parentId: m.parent_id ?? null, files: [] });
                          }}
                        >
                          <label htmlFor={`edit-${m.id}`} className="sr-only">Edit message</label>
                          <textarea
                            id={`edit-${m.id}`}
                            autoFocus
                            value={editing.text}
                            onChange={(e) => setEditing({ id: m.id, text: e.target.value })}
                            onKeyDown={(e) => e.key === "Escape" && setEditing(null)}
                            rows={3}
                            className="w-full resize-y bg-transparent text-base outline-hidden"
                          />
                          <div className="flex justify-end gap-2">
                            <Button size="sm" variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
                            <Button size="sm" type="submit" disabled={!editing.text.trim()}>Send</Button>
                          </div>
                        </form>
                      ) : (
                        <div className="max-w-[85%] rounded-xl bg-surface-muted px-4 py-2.5 text-base sm:max-w-[70%]">
                          <Blocks content={content} text={textNow} role="user" />
                        </div>
                      )}
                      {!isEditing && (
                        <div className="flex items-center opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100">
                          <BranchNav kind="Message" index={sibIndex} total={sibs.length} onPick={(i) => pickSibling(m, i)} />
                          <IconButton label="Copy message" size="sm" onClick={() => copy(m, textNow)}>{copied === m.id ? <Check /> : <Copy />}</IconButton>
                          {canEdit && !streamingId && (
                            <IconButton label="Edit message" size="sm" onClick={() => setEditing({ id: m.id, text: m.text })}><Pencil /></IconButton>
                          )}
                        </div>
                      )}
                    </article>
                  );
                }

                return (
                  <article key={m.id} className="group flex flex-col gap-3" aria-busy={status === "streaming" || undefined}>
                    <h2 className="sr-only">Assistant said:</h2>
                    {status === "streaming" && (!textNow || l?.activity) && (
                      <p className="flex items-center gap-2 text-sm text-muted" role="status">
                        <span aria-hidden className="flex gap-1">
                          {[0, 1, 2].map((d) => <span key={d} className="size-1.5 animate-pulse rounded-full bg-current motion-reduce:animate-none" style={{ animationDelay: `${d * 150}ms` }} />)}
                        </span>
                        {l?.activity ?? (MODELS.find((x) => x.id === m.model)?.label === "Deep" ? "Thinking it through" : "Thinking")}
                      </p>
                    )}
                    <div className="text-base text-fg">
                      <Blocks content={content} text={textNow} role="assistant" onDecide={canEdit ? (id, d) => decide(id, d) : undefined} />
                      {status === "streaming" && textNow && <span aria-hidden className="ml-0.5 inline-block h-5 w-2 translate-y-1 rounded-[1px] bg-fg animate-caret" />}
                    </div>
                    {status === "stopped" && <div><Badge>Stopped</Badge></div>}
                    {status === "error" && (
                      <Banner
                        tone="danger"
                        title="This answer didn't finish."
                        action={canEdit ? <Button size="sm" variant="secondary" icon={<RefreshCw className="size-3.5" />} onClick={() => regenerate(m)}>Retry</Button> : undefined}
                      >
                        {err ?? "That didn’t go through."} Your message is safe.
                      </Banner>
                    )}
                    {status !== "streaming" && (
                      <div
                        role="toolbar"
                        aria-label="Answer actions"
                        className={cn("-ml-1.5 flex flex-wrap items-center gap-0.5 transition-opacity", !isLast && "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100")}
                      >
                        <BranchNav kind="Answer" index={sibIndex} total={sibs.length} onPick={(i) => pickSibling(m, i)} />
                        <IconButton label={copied === m.id ? "Copied" : "Copy"} size="sm" onClick={() => copy(m, textNow)}>{copied === m.id ? <Check /> : <Copy />}</IconButton>
                        {canEdit && (
                          <>
                            <IconButton label="Good answer" size="sm" aria-pressed={m.feedback === 1} onClick={() => rate(m, 1)}><ThumbsUp className={cn(m.feedback === 1 && "fill-current")} /></IconButton>
                            <IconButton label="Bad answer" size="sm" aria-pressed={m.feedback === -1} onClick={() => rate(m, -1)}><ThumbsDown className={cn(m.feedback === -1 && "fill-current")} /></IconButton>
                            <Menu>
                              <MenuTrigger asChild>
                                <IconButton label="Try again" size="sm" disabled={!!streamingId}><RefreshCw /></IconButton>
                              </MenuTrigger>
                              <MenuContent>
                                <MenuItem icon={<RefreshCw />} onSelect={() => regenerate(m)}>Try again</MenuItem>
                                <MenuSeparator />
                                <MenuLabel>Try again with</MenuLabel>
                                {MODELS.map((x) => (
                                  <MenuItem key={x.id} onSelect={() => regenerate(m, x.id)} description={x.description}>{x.label}</MenuItem>
                                ))}
                              </MenuContent>
                            </Menu>
                          </>
                        )}
                        {m.model && <span className="ml-1 text-xs text-muted">{MODELS.find((x) => x.id === m.model)?.label}</span>}
                      </div>
                    )}
                    <div className="sr-only" role="status">{status === "complete" && l ? "Answer ready" : ""}</div>
                  </article>
                );
              })}
              {pending && (
                <>
                  <article className="flex flex-col items-end gap-1">
                    <h2 className="sr-only">You said:</h2>
                    {pending.attachments.length > 0 && (
                      <ul className="flex flex-wrap justify-end gap-2">
                        {pending.attachments.map((a) => <li key={a.id} className="rounded-md bg-surface-muted px-3 py-2 text-sm">{a.name}</li>)}
                      </ul>
                    )}
                    {pending.text && <div className="max-w-[85%] whitespace-pre-wrap rounded-xl bg-surface-muted px-4 py-2.5 sm:max-w-[70%]">{pending.text}</div>}
                  </article>
                  <p className="flex items-center gap-2 text-sm text-muted" role="status">
                    <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-current motion-reduce:animate-none" /> Sending
                  </p>
                </>
              )}
              {sendError && <Banner tone="danger" title="Message not sent" onDismiss={() => setSendError(null)}>{sendError}</Banner>}
            </div>
          </div>
          {!atBottom && (
            <div className="pointer-events-none absolute inset-x-0 bottom-36 flex justify-center">
              <IconButton label="Scroll to latest message" variant="secondary" className="pointer-events-auto shadow-md" onClick={scrollToBottom}>
                <ArrowDown />
              </IconButton>
            </div>
          )}
          <div className="shrink-0 px-4 pb-4 pt-1">
            {composerEl}
            <p className="mt-2 text-center text-xs text-muted">{BRAND.name} can be wrong. Check facts that matter before you rely on them.</p>
          </div>
        </>
      )}
      {sharing && convId && <ShareDialog conversationId={convId} open onOpenChange={setSharing} />}
    </div>
  );
}
