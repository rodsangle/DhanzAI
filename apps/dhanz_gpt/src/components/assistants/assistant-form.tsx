"use client";

import { BRAND } from "@/lib/brand";
import { FileText, History, Library, Trash2, Upload, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { mutate } from "swr";
import { api, uploadFile } from "@/lib/api";
import { MODELS, type AssistantCapability, type AssistantDetail, type FileRow } from "@/lib/data/types";
import { cn, focusRing } from "@/lib/cn";
import { Button, IconButton, button } from "@/components/ui/button";
import { Banner, useToast } from "@/components/ui/feedback";
import { Textarea, TextInput } from "@/components/ui/field";
import { RadioGroup, Switch } from "@/components/ui/controls";
import { Dialog } from "@/components/ui/overlays";
import { LibraryPicker } from "@/components/chat/library-picker";

type KFile = { id: string; name: string; status: "uploading" | "ready" | "error"; error?: string };
const MAX_FILES = 20;

/** S22 builder: configure an assistant. With `existing`, it edits; otherwise it creates. */
export function AssistantForm({ existing }: { existing?: AssistantDetail }) {
  const router = useRouter();
  const toast = useToast();
  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [instructions, setInstructions] = useState(existing?.instructions ?? "");
  const [starters, setStarters] = useState<string[]>(() => [...(existing?.starters ?? []), "", "", "", ""].slice(0, 4));
  const [model, setModel] = useState(existing?.recommended_model ?? "none");
  const [caps, setCaps] = useState<AssistantCapability[]>(existing?.capabilities ?? ["web_search", "image_generation"]);
  const [visibility, setVisibility] = useState<"private" | "workspace">(existing?.visibility ?? "private");
  const [files, setFiles] = useState<KFile[]>(existing?.files.map((f) => ({ id: f.id, name: f.name, status: "ready" })) ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const uploading = files.some((f) => f.status === "uploading");

  function toggleCap(c: AssistantCapability, on: boolean) {
    setCaps((cur) => (on ? [...new Set([...cur, c])] : cur.filter((x) => x !== c)));
  }

  function upload(list: File[]) {
    for (const f of list.slice(0, MAX_FILES - files.length)) {
      const temp = `up-${crypto.randomUUID()}`;
      setFiles((cur) => [...cur, { id: temp, name: f.name, status: "uploading" }]);
      uploadFile(f, () => {})
        .then((row) => setFiles((cur) => cur.map((x) => (x.id === temp ? { id: row.id, name: row.name, status: row.status === "ready" ? "ready" : "error", error: row.error ?? undefined } : x))))
        .catch((e: Error) => setFiles((cur) => cur.map((x) => (x.id === temp ? { ...x, status: "error", error: e.message } : x))));
    }
  }

  function addFromLibrary(rows: FileRow[]) {
    setFiles((cur) => [...cur, ...rows.filter((r) => !cur.some((c) => c.id === r.id)).map((r): KFile => ({ id: r.id, name: r.name, status: "ready" }))]);
  }

  async function save() {
    setSaving(true);
    setError(null);
    const input = {
      name, description, instructions,
      starters: starters.map((s) => s.trim()).filter(Boolean),
      recommended_model: model === "none" ? null : model,
      capabilities: caps,
      visibility,
      file_ids: files.filter((f) => f.status === "ready").map((f) => f.id),
    };
    try {
      const saved = existing ? await api.updateAssistant(existing.id, input) : await api.createAssistant(input);
      mutate("/api/assistants");
      if (existing) {
        await mutate(`/api/assistants/${existing.id}`, saved, { revalidate: false });
        toast({ title: `Saved as version ${saved.current_version}.` });
      } else {
        toast({ title: `Created ${saved.name}. Try it out.` });
        router.push(`/assistants/${saved.id}`);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function restore(version: number) {
    if (!existing) return;
    try {
      const saved = await api.restoreAssistant(existing.id, version);
      await mutate(`/api/assistants/${existing.id}`, saved, { revalidate: false });
      mutate("/api/assistants");
      toast({ title: `Restored version ${version}. It's saved as version ${saved.current_version}.` });
      // The form keys on the version, so it reloads with the restored settings.
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    }
  }

  async function remove() {
    if (!existing) return;
    try {
      await api.deleteAssistant(existing.id);
      mutate("/api/assistants");
      toast({ title: `Deleted ${existing.name}. Its chats stay in your history.` });
      router.push("/assistants");
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    }
  }

  return (
    <form
      className="flex flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (!saving && !uploading) save();
      }}
    >
      <section className="flex flex-col gap-4" aria-labelledby="basics">
        <h2 id="basics" className="text-sm font-semibold">Basics</h2>
        <TextInput label="Name" placeholder="For example: Copywriter" value={name} maxLength={80} required onChange={(e) => setName(e.target.value)} />
        <TextInput label="Description" placeholder="What it's for, in one line" value={description} maxLength={300} onChange={(e) => setDescription(e.target.value)} />
        <Textarea
          label="Instructions"
          placeholder="What it does, how it should sound, what to always or never do. For example: Write product descriptions in a warm, plain voice: short lines, no exclamation marks, always mention the material."
          rows={10}
          value={instructions}
          maxLength={20000}
          onChange={(e) => setInstructions(e.target.value)}
          hint={`${instructions.length.toLocaleString()} / 20,000`}
        />
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="starters">
        <h2 id="starters" className="text-sm font-semibold">Conversation starters</h2>
        <p className="-mt-2 text-xs text-muted">Shown as buttons when someone opens the assistant. Up to four.</p>
        {starters.map((st, i) => (
          <TextInput
            key={i}
            label={`Starter ${i + 1}`}
            hideLabel
            placeholder={i === 0 ? "For example: Write a product description for a canvas tote bag" : `Starter ${i + 1}`}
            value={st}
            maxLength={200}
            onChange={(e) => setStarters((cur) => cur.map((x, j) => (j === i ? e.target.value : x)))}
          />
        ))}
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="knowledge">
        <h2 id="knowledge" className="text-sm font-semibold">Knowledge</h2>
        <p className="-mt-2 text-xs text-muted">Reference files it reads when answering: brand guides, tech packs, past campaigns. Long files are read by the parts that match each question.</p>
        {files.length > 0 && (
          <ul aria-label="Knowledge files" className="flex flex-col gap-1">
            {files.map((f) => (
              <li key={f.id} className="flex items-center gap-2 rounded-md bg-surface-muted px-3 py-2 text-sm">
                <FileText aria-hidden className="size-4 shrink-0 text-muted" />
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                <span className={cn("shrink-0 text-xs", f.status === "error" ? "text-danger-text" : "text-muted")}>
                  {f.status === "uploading" ? "Uploading" : f.status === "error" ? f.error ?? "Upload failed" : "Ready"}
                </span>
                <IconButton label={`Remove ${f.name}`} size="sm" onClick={() => setFiles((cur) => cur.filter((x) => x.id !== f.id))}><X /></IconButton>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" icon={<Upload className="size-4" />} disabled={files.length >= MAX_FILES} onClick={() => fileInput.current?.click()}>Upload files</Button>
          <Button variant="secondary" size="sm" icon={<Library className="size-4" />} disabled={files.length >= MAX_FILES} onClick={() => setPicking(true)}>Add from Library</Button>
        </div>
        <input
          ref={fileInput}
          type="file"
          multiple
          hidden
          tabIndex={-1}
          aria-hidden
          onChange={(e) => {
            if (e.target.files?.length) upload(Array.from(e.target.files));
            e.target.value = "";
          }}
        />
        <LibraryPicker
          open={picking}
          onOpenChange={setPicking}
          max={MAX_FILES - files.length}
          already={files.map((f) => f.id)}
          onPick={addFromLibrary}
        />
      </section>

      <section className="flex flex-col gap-4" aria-labelledby="behaviour">
        <h2 id="behaviour" className="text-sm font-semibold">Model and tools</h2>
        <RadioGroup
          label="Model"
          value={model}
          onValueChange={setModel}
          options={[{ value: "none", label: "No preference", description: "Uses whatever model the person picks" }, ...MODELS.map((m) => ({ value: m.id, label: m.label, description: m.description }))]}
        />
        <Switch label="Web search" description="Can look things up on the web and cite sources." checked={caps.includes("web_search")} onCheckedChange={(v) => toggleCap("web_search", v)} />
        <Switch label="Create images" description="Can make images when asked." checked={caps.includes("image_generation")} onCheckedChange={(v) => toggleCap("image_generation", v)} />
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="sharing">
        <h2 id="sharing" className="text-sm font-semibold">Who can use it</h2>
        <RadioGroup
          label="Visibility"
          value={visibility}
          onValueChange={(v) => setVisibility(v as "private" | "workspace")}
          options={[
            { value: "private", label: "Only me" },
            { value: "workspace", label: BRAND.everyone, description: "Teammates can chat with it and read its knowledge files. Only you and admins can edit it." },
          ]}
        />
      </section>

      {error && <Banner tone="danger" title="Not saved">{error}</Banner>}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
        <div className="flex gap-2">
          {existing && (
            <Dialog
              open={confirmDelete}
              onOpenChange={setConfirmDelete}
              title={`Delete ${existing.name}?`}
              description="People can't start new chats with it. Chats already made with it stay in their history."
              size="sm"
              trigger={<Button variant="ghost" icon={<Trash2 className="size-4" />}>Delete</Button>}
              footer={
                <>
                  <Button variant="secondary" onClick={() => setConfirmDelete(false)}>Cancel</Button>
                  <Button variant="danger" onClick={remove}>Delete assistant</Button>
                </>
              }
            />
          )}
        </div>
        <div className="flex gap-2">
          <Link href={existing ? `/assistants/${existing.id}` : "/assistants"} className={cn(button({ variant: "secondary" }), focusRing)}>
            {existing ? "Try it" : "Cancel"}
          </Link>
          <Button type="submit" loading={saving} disabled={uploading}>{existing ? "Save" : "Create"}</Button>
        </div>
      </div>

      {existing && existing.versions.length > 0 && (
        <section className="flex flex-col gap-2 border-t border-border pt-4" aria-labelledby="versions">
          <h2 id="versions" className="flex items-center gap-2 text-sm font-semibold"><History aria-hidden className="size-4" /> Version history</h2>
          <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">
            {existing.versions.map((v) => (
              <li key={v.version} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                <span>
                  Version {v.version}
                  <span className="text-muted"> · {new Date(v.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}{v.created_by_name ? ` · ${v.created_by_name}` : ""}</span>
                </span>
                {v.version === existing.current_version ? (
                  <span className="text-xs text-muted">Current</span>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => restore(v.version)}>Restore</Button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </form>
  );
}
