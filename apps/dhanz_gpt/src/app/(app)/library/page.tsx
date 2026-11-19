"use client";

import { Download, FileText, Image as ImageIcon, Library, MessageSquarePlus, RotateCcw, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import { api, fileUrl } from "@/lib/api";
import type { FileRow } from "@/lib/data/types";
import { cn, focusRing } from "@/lib/cn";
import { IconButton } from "@/components/ui/button";
import { Badge, EmptyState, Skeleton, useToast } from "@/components/ui/feedback";
import { Tabs } from "@/components/ui/controls";
import { TextInput } from "@/components/ui/field";
import { PageHeader } from "@/components/shell/app-shell";
import { useUI } from "@/components/shell/providers";
import { useRouter } from "next/navigation";

const gb = (n: number) => (n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(1).replace(/\.0$/, "")} GB` : n >= 1024 ** 2 ? `${Math.round(n / 1024 ** 2)} MB` : `${Math.max(0, Math.round(n / 1024))} KB`);

/** How much of the storage quota the person's files use. */
function StorageBar() {
  const { data } = useSWR<{ used: number; quota: number }>("/api/files/usage");
  if (!data) return <Skeleton className="h-9" />;
  const pct = Math.min(100, (data.used / data.quota) * 100);
  const full = pct >= 90;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between text-sm">
        <span id="storage-label">Storage</span>
        <span className={cn("text-xs tabular-nums", full ? "text-warning-text" : "text-muted")}>
          {gb(data.used)} of {gb(data.quota)} used
        </span>
      </div>
      <div
        role="progressbar"
        aria-labelledby="storage-label"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        aria-valuetext={`${gb(data.used)} of ${gb(data.quota)} used`}
        className="h-1.5 overflow-hidden rounded-full bg-surface-muted"
      >
        <div className={cn("h-full rounded-full", full ? "bg-warning-text" : "bg-accent")} style={{ width: `${Math.max(pct, data.used ? 1 : 0)}%` }} />
      </div>
      {full && <p className="text-xs text-warning-text">Almost full. Delete files you don&apos;t need: deleted files stop counting right away.</p>}
    </div>
  );
}

const fmt = (n: number) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);

function FileList({ files, trashed }: { files: FileRow[] | undefined; trashed?: boolean }) {
  const toast = useToast();
  const router = useRouter();
  const { setPendingFiles } = useUI();
  function startChatWith(f: FileRow) {
    setPendingFiles([f]);
    router.push("/");
  }
  async function setTrashed(f: FileRow, t: boolean) {
    await api.trashFile(f.id, t);
    mutate("/api/files");
    mutate("/api/files?trashed=1");
    mutate("/api/files/usage");
    if (t) toast({ title: `Moved ${f.name} to Recently deleted`, action: { label: "Undo", onClick: () => setTrashed(f, false) } });
  }
  if (!files) return <div className="flex flex-col gap-2" aria-busy="true">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>;
  if (!files.length)
    return trashed ? (
      <EmptyState icon={<Trash2 />} title="Nothing here">Deleted files stay here for 30 days before they&apos;re gone for good.</EmptyState>
    ) : (
      <EmptyState icon={<Library />} title="No files yet">Upload a file once and use it in any chat. Everything you add lands here.</EmptyState>
    );
  return (
    <ul className="flex flex-col divide-y divide-border rounded-xl border border-border">
      {files.map((f) => (
        <li key={f.id} className="flex items-center gap-3 px-4 py-2.5">
          <span aria-hidden className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-md bg-surface-muted text-muted">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {f.mime.startsWith("image/") ? <img src={fileUrl(f.id)} alt="" className="size-full object-cover" /> : <FileText className="size-4" />}
          </span>
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-sm">{f.name}</span>
            <span className="text-xs text-muted">{fmt(f.bytes)} · {new Date(f.created_at).toLocaleDateString()}</span>
          </div>
          {f.source === "generated" && <Badge>Generated</Badge>}
          {trashed ? (
            <IconButton label={`Restore ${f.name}`} size="sm" onClick={() => setTrashed(f, false)}><RotateCcw /></IconButton>
          ) : (
            <>
              <IconButton label={`Use ${f.name} in a chat`} size="sm" onClick={() => startChatWith(f)}><MessageSquarePlus /></IconButton>
              <a href={fileUrl(f.id, false)} aria-label={`Download ${f.name}`} className={cn("inline-flex size-8 items-center justify-center rounded-md text-muted hover:bg-surface-hover hover:text-fg", focusRing)}>
                <Download className="size-4" />
              </a>
              <IconButton label={`Delete ${f.name}`} size="sm" onClick={() => setTrashed(f, true)}><Trash2 /></IconButton>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

// S11 Library: list, search, download, recently deleted, storage used
export default function LibraryPage() {
  const { data: files } = useSWR<FileRow[]>("/api/files");
  const { data: trashed } = useSWR<FileRow[]>("/api/files?trashed=1");
  const [q, setQ] = useState("");
  const filtered = useMemo(() => files?.filter((f) => f.name.toLowerCase().includes(q.toLowerCase())), [files, q]);
  const images = filtered?.filter((f) => f.mime.startsWith("image/"));
  const docs = filtered?.filter((f) => !f.mime.startsWith("image/"));
  return (
    <main id="main" className="flex flex-1 flex-col overflow-y-auto">
      <PageHeader left={<h1 className="px-2 text-lg font-semibold">Library</h1>} />
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 pb-10">
        <StorageBar />
        <TextInput label="Search files" hideLabel leading={<Search />} placeholder="Search files" value={q} onChange={(e) => setQ(e.target.value)} />
        <Tabs
          defaultValue="all"
          variant="pill"
          tabs={[
            { value: "all", label: "All", content: <FileList files={filtered} /> },
            { value: "images", label: "Images", content: <FileList files={images} /> },
            { value: "docs", label: "Documents", content: <FileList files={docs} /> },
            { value: "trash", label: `Recently deleted${trashed?.length ? ` (${trashed.length})` : ""}`, content: <FileList files={trashed} trashed /> },
          ]}
        />
        <p className="flex items-center gap-1.5 text-xs text-muted"><ImageIcon aria-hidden className="size-3.5" /> Generated images are saved here automatically.</p>
      </div>
    </main>
  );
}
