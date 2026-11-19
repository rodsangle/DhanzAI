"use client";

import { Dialog as D } from "radix-ui";
import { FileStack, FileText, FolderOpen, MessageSquare, Search, SquarePen } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import useSWR from "swr";
import type { ConversationListItem, SearchResult } from "@/lib/data/types";
import { cn } from "@/lib/cn";
import { useUI } from "./providers";

const icon = { chat: MessageSquare, message: MessageSquare, project: FolderOpen, file: FileText, page: FileStack };
const groupLabel = { chat: "Chats", message: "In messages", project: "Projects", file: "Files", page: "Pages" };

function useDebounced<T>(v: T, ms: number) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

function highlight(text: string, q: string) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded-sm bg-selection text-fg">{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  );
}

export function SearchModal() {
  const { searchOpen, setSearchOpen } = useUI();
  const router = useRouter();
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim(), 150);
  const { data: results, isLoading } = useSWR<SearchResult[]>(searchOpen && dq ? `/api/search?q=${encodeURIComponent(dq)}` : null);
  const { data: recent } = useSWR<ConversationListItem[]>(searchOpen ? "/api/conversations" : null);
  const [cursor, setCursor] = useState({ q: "", i: 0 });
  const active = cursor.q === dq ? cursor.i : 0;
  const setActive = (f: (i: number) => number) => setCursor({ q: dq, i: f(active) });
  const listId = useId();

  const items: { id: string; kind: SearchResult["kind"] | "new"; title: string; snippet?: string; href: string }[] = dq
    ? (results ?? [])
    : [{ id: "new", kind: "new", title: "New chat", href: "/" }, ...(recent ?? []).slice(0, 8).map((c) => ({ id: c.id, kind: "chat" as const, title: c.title, href: `/c/${c.id}` }))];

  function close() {
    setSearchOpen(false);
    setQ("");
  }
  function go(i: number) {
    const it = items[i];
    if (!it) return;
    close();
    router.push(it.href);
  }

  const headers = items.map((it, i) =>
    dq ? (i === 0 || items[i - 1].kind !== it.kind ? groupLabel[it.kind as SearchResult["kind"]] : null) : i === 1 ? "Recent" : null,
  );
  return (
    <D.Root open={searchOpen} onOpenChange={(o) => (o ? setSearchOpen(true) : close())}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[var(--z-modal)] bg-overlay" />
        <D.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-[12vh] z-[var(--z-modal)] flex max-h-[70vh] w-[calc(100vw-2rem)] max-w-[var(--modal-lg)] -translate-x-1/2 flex-col overflow-hidden rounded-xl bg-surface-raised text-fg shadow-lg"
        >
          <D.Title className="sr-only">Search chats</D.Title>
          <div className="flex items-center gap-3 border-b border-border px-4">
            <Search aria-hidden className="size-5 text-muted" />
            <input
              autoFocus
              role="combobox"
              aria-expanded
              aria-controls={listId}
              aria-activedescendant={items[active] ? `${listId}-${active}` : undefined}
              aria-label="Search chats, projects and files"
              placeholder="Search chats, projects and files"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActive((a) => Math.min(a + 1, items.length - 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActive((a) => Math.max(a - 1, 0));
                } else if (e.key === "Enter") {
                  e.preventDefault();
                  go(active);
                }
              }}
              className="h-14 flex-1 bg-transparent text-lg outline-hidden placeholder:text-subtle"
            />
          </div>
          <ul id={listId} role="listbox" aria-label="Results" className="overflow-y-auto p-2">
            {dq && isLoading && <li className="px-3 py-6 text-center text-sm text-muted">Searching…</li>}
            {dq && results && results.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted">Nothing matches “{dq}”.</li>}
            {items.map((it, i) => {
              const header = headers[i];
              const Icon = it.kind === "new" ? SquarePen : icon[it.kind];
              return (
                <li key={`${it.kind}-${it.id}`} role="presentation">
                  {header && <p className="px-3 pb-1 pt-3 text-xs font-semibold text-muted">{header}</p>}
                  <div
                    id={`${listId}-${i}`}
                    role="option"
                    aria-selected={i === active}
                    onMouseMove={() => i !== active && setActive(() => i)}
                    onClick={() => go(i)}
                    className={cn("flex cursor-pointer items-start gap-3 rounded-md px-3 py-2", i === active && "bg-surface-hover")}
                  >
                    <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-muted" />
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate text-sm">{highlight(it.title, dq)}</span>
                      {it.snippet && <span className="line-clamp-2 text-xs text-muted">{highlight(it.snippet, dq)}</span>}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
