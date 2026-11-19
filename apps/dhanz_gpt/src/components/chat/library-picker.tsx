"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import useSWR from "swr";
import type { FileRow } from "@/lib/data/types";
import { Button } from "@/components/ui/button";
import { TextInput } from "@/components/ui/field";
import { Checkbox } from "@/components/ui/controls";
import { Dialog } from "@/components/ui/overlays";

const fmt = (n: number) => (n < 1024 ? `${n} B` : n < 1024 ** 2 ? `${Math.round(n / 1024)} KB` : `${(n / 1024 ** 2).toFixed(1)} MB`);

/** Pick files already in the Library to attach, without uploading them again. */
export function LibraryPicker({
  open, onOpenChange, max, already, onPick,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  /** How many more files fit on this message. */
  max: number;
  /** File ids already attached (shown checked and fixed). */
  already: string[];
  onPick: (files: FileRow[]) => void;
}) {
  const { data } = useSWR<FileRow[]>(open ? "/api/files" : null);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const files = useMemo(
    () => (data ?? []).filter((f) => f.status === "ready" && f.name.toLowerCase().includes(q.trim().toLowerCase())),
    [data, q],
  );
  const full = picked.length >= max;
  function close(o: boolean) {
    if (!o) {
      setPicked([]);
      setQ("");
    }
    onOpenChange(o);
  }
  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title="Add from Library"
      description={max > 0 ? `Pick up to ${max} file${max === 1 ? "" : "s"} you've already uploaded or created.` : "This message already has the most files it can take."}
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={() => close(false)}>Cancel</Button>
          <Button
            disabled={!picked.length}
            onClick={() => {
              onPick((data ?? []).filter((f) => picked.includes(f.id)));
              close(false);
            }}
          >
            {picked.length ? `Attach ${picked.length} file${picked.length === 1 ? "" : "s"}` : "Attach"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <TextInput label="Search your files" hideLabel placeholder="Search your files" leading={<Search />} value={q} onChange={(e) => setQ(e.target.value)} />
        {!data ? (
          <p role="status" className="py-6 text-center text-sm text-muted">Loading your files</p>
        ) : files.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted">{data.length ? "No files match." : "Your Library is empty. Files you upload show up here."}</p>
        ) : (
          <ul aria-label="Library files" className="flex max-h-80 flex-col gap-1 overflow-y-auto">
            {files.map((f) => {
              const isAttached = already.includes(f.id);
              const checked = isAttached || picked.includes(f.id);
              return (
                <li key={f.id} className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 hover:bg-surface-hover">
                  <Checkbox
                    label={f.name}
                    checked={checked}
                    disabled={isAttached || (!checked && full)}
                    onCheckedChange={(v) => setPicked((p) => (v ? [...p, f.id] : p.filter((x) => x !== f.id)))}
                  />
                  <span className="shrink-0 text-xs text-muted">{isAttached ? "Attached" : fmt(f.bytes)}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Dialog>
  );
}
