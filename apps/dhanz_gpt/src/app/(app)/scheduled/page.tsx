"use client";

import { Bell, CalendarClock, CircleAlert, CircleCheck, Loader, Mail, MoreHorizontal, Pause, Pencil, Play, Plus, Trash2, Zap } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import type { TaskItem } from "@/lib/data/tasks";
import { DAY_NAMES, describe, isValidZone, nextRun, validate, type Schedule } from "@/lib/schedule";
import { MODELS } from "@/lib/data/types";
import { cn, focusRing } from "@/lib/cn";
import { Button, IconButton } from "@/components/ui/button";
import { Badge, Banner, EmptyState, Skeleton, useToast } from "@/components/ui/feedback";
import { Select, Textarea, TextInput } from "@/components/ui/field";
import { Checkbox } from "@/components/ui/controls";
import { Dialog, Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/overlays";
import { PageHeader } from "@/components/shell/app-shell";
import { useUI } from "@/components/shell/providers";

// S18 Scheduled: tasks that run on their own, each run a new chat.

const browserZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "America/New_York";
const fmtWhen = (iso: string, tz?: string) =>
  new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: tz });

type Repeat = Schedule["kind"];
type Draft = { title: string; prompt: string; repeat: Repeat; date: string; time: string; days: number[]; day: number; timezone: string; push: boolean; email: boolean; model: string };

function toSchedule(d: Draft): Schedule {
  switch (d.repeat) {
    case "once": return { kind: "once", date: d.date, time: d.time };
    case "weekly": return { kind: "weekly", days: d.days, time: d.time };
    case "monthly": return { kind: "monthly", day: d.day, time: d.time };
    default: return { kind: d.repeat, time: d.time };
  }
}

function TaskDialog({ open, onOpenChange, task }: { open: boolean; onOpenChange: (o: boolean) => void; task?: TaskItem }) {
  const { me } = useUI();
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(() => {
    const s = task?.schedule;
    const tomorrow = new Date(Date.now() + 86_400_000);
    return {
      title: task?.title ?? "",
      prompt: task?.prompt ?? "",
      repeat: s?.kind ?? "weekdays",
      date: s?.kind === "once" ? s.date : `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`,
      time: s?.time ?? "09:00",
      days: s?.kind === "weekly" ? s.days : [1],
      day: s?.kind === "monthly" ? s.day : 1,
      timezone: task?.timezone ?? browserZone(),
      push: task ? task.notify.includes("push") : !!me?.features?.push,
      email: task ? task.notify.includes("email") : !!me?.features?.email,
      model: task?.model ?? "none",
    };
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const zones = useMemo(() => {
    const all = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.("timeZone") ?? [];
    return all.includes(draft.timezone) ? all : [draft.timezone, ...all];
  }, [draft.timezone]);
  const schedule = toSchedule(draft);
  const problem = validate(schedule) ?? (isValidZone(draft.timezone) ? null : "Pick a time zone.");
  const next = problem ? null : nextRun(schedule, draft.timezone);

  async function save() {
    setSaving(true);
    setError(null);
    const input = {
      title: draft.title, prompt: draft.prompt, schedule, timezone: draft.timezone,
      notify: [...(draft.push ? ["push" as const] : []), ...(draft.email ? ["email" as const] : [])],
      model: draft.model === "none" ? null : draft.model,
    };
    try {
      const saved = task ? await api.updateTask(task.id, input) : await api.createTask(input);
      await mutate("/api/tasks");
      toast({ title: task ? "Task saved." : `Scheduled. ${saved.next_run_at ? `First run ${fmtWhen(saved.next_run_at)}.` : ""}` });
      onOpenChange(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={task ? "Edit task" : "New scheduled task"}
      description="The assistant runs this on its own and saves each result as a chat."
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button loading={saving} disabled={!!problem || !next || !draft.title.trim() || !draft.prompt.trim()} onClick={save}>{task ? "Save" : "Schedule"}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <TextInput label="Name" placeholder="For example: Monday news recap" value={draft.title} maxLength={200} onChange={(e) => set("title", e.target.value)} />
        <Textarea
          label="What should it do each time?"
          placeholder="For example: Search the web for news about my industry from the past week and give me five bullet points with sources."
          rows={4}
          maxLength={10000}
          value={draft.prompt}
          onChange={(e) => set("prompt", e.target.value)}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Repeats" value={draft.repeat} onChange={(e) => set("repeat", e.target.value as Repeat)}>
            <option value="once">Once</option>
            <option value="daily">Every day</option>
            <option value="weekdays">Every weekday</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </Select>
          <TextInput label="Time" type="time" value={draft.time} onChange={(e) => set("time", e.target.value)} />
        </div>
        {draft.repeat === "once" && <TextInput label="Date" type="date" value={draft.date} onChange={(e) => set("date", e.target.value)} />}
        {draft.repeat === "weekly" && (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium">On</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {[1, 2, 3, 4, 5, 6, 0].map((d) => (
                <Checkbox
                  key={d}
                  label={DAY_NAMES[d]}
                  checked={draft.days.includes(d)}
                  onCheckedChange={(v) => set("days", v ? [...draft.days, d] : draft.days.filter((x) => x !== d))}
                />
              ))}
            </div>
          </fieldset>
        )}
        {draft.repeat === "monthly" && (
          <Select label="Day of the month" value={draft.day} onChange={(e) => set("day", Number(e.target.value))}>
            {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => <option key={d} value={d}>{d}</option>)}
          </Select>
        )}
        <Select label="Time zone" value={draft.timezone} onChange={(e) => set("timezone", e.target.value)}>
          {zones.map((z) => <option key={z} value={z}>{z.replace(/_/g, " ")}</option>)}
        </Select>
        <Select label="Model" value={draft.model} onChange={(e) => set("model", e.target.value)}>
          <option value="none">Default</option>
          {MODELS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
        </Select>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">When it finishes</legend>
          <Checkbox label="Send a push notification" checked={draft.push} disabled={!me?.features?.push} onCheckedChange={(v) => set("push", !!v)} />
          <Checkbox label="Email me the result" checked={draft.email} disabled={!me?.features?.email} onCheckedChange={(v) => set("email", !!v)} />
          <p className="text-xs text-muted">
            Results always show here and in your chats.
            {me?.features?.push ? " Turn push on for each browser in Settings → Notifications." : ""}
          </p>
        </fieldset>
        <p className="rounded-md bg-surface-muted px-3 py-2 text-sm" aria-live="polite">
          {problem ?? (next ? `${describe(schedule)}. Next run ${fmtWhen(next.toISOString(), draft.timezone)}.` : "That time has already passed.")}
        </p>
        {error && <Banner tone="danger" title="Not saved">{error}</Banner>}
      </div>
    </Dialog>
  );
}

const RUN_LABEL = { running: "Running", succeeded: "Done", failed: "Didn't finish", awaiting_approval: "Waiting", skipped: "Skipped" } as const;

function TaskCard({ t }: { t: TaskItem }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  async function act(fn: () => Promise<unknown>, done: string) {
    try {
      await fn();
      await mutate("/api/tasks");
      toast({ title: done });
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    }
  }
  return (
    <li className="flex flex-col gap-3 rounded-xl border border-border p-4">
      <div className="flex items-start gap-3">
        <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-surface-muted text-muted"><CalendarClock className="size-4" /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h2 className="flex items-center gap-2 font-medium">
            <span className="truncate">{t.title}</span>
            {t.status === "paused" && <Badge>Paused</Badge>}
            {t.status === "completed" && <Badge>Done</Badge>}
          </h2>
          <p className="text-sm text-muted">
            {t.schedule_text}
            {t.timezone !== browserZone() ? ` (${t.timezone.replace(/_/g, " ")})` : ""}
          </p>
          {t.next_run_at && <p className="text-xs text-muted">Next run {fmtWhen(t.next_run_at)}</p>}
          <p className="flex items-center gap-2 text-xs text-muted">
            {t.notify.includes("push") && <span className="inline-flex items-center gap-1"><Bell aria-hidden className="size-3" /> Push</span>}
            {t.notify.includes("email") && <span className="inline-flex items-center gap-1"><Mail aria-hidden className="size-3" /> Email</span>}
          </p>
        </div>
        <Menu>
          <MenuTrigger asChild>
            <IconButton label={`Options for ${t.title}`} size="sm"><MoreHorizontal /></IconButton>
          </MenuTrigger>
          <MenuContent align="end">
            <MenuItem icon={<Zap />} onSelect={() => act(() => api.runTask(t.id), "Running now. The result will show here.")}>Run now</MenuItem>
            <MenuItem icon={<Pencil />} onSelect={() => setEditing(true)}>Edit</MenuItem>
            {t.status === "active" ? (
              <MenuItem icon={<Pause />} onSelect={() => act(() => api.pauseTask(t.id, true), "Paused.")}>Pause</MenuItem>
            ) : t.status === "paused" ? (
              <MenuItem icon={<Play />} onSelect={() => act(() => api.pauseTask(t.id, false), "Resumed.")}>Resume</MenuItem>
            ) : null}
            <MenuSeparator />
            <MenuItem icon={<Trash2 />} destructive onSelect={() => setConfirm(true)}>Delete</MenuItem>
          </MenuContent>
        </Menu>
      </div>
      {t.runs.length > 0 && (
        <ul aria-label={`Recent runs of ${t.title}`} className="flex flex-col divide-y divide-border rounded-lg bg-surface-muted">
          {t.runs.map((r) => (
            <li key={r.id} className="flex items-center gap-2 px-3 py-2 text-sm">
              {r.status === "running" ? <Loader aria-hidden className="size-4 animate-spin text-muted motion-reduce:animate-none" />
                : r.status === "succeeded" ? <CircleCheck aria-hidden className="size-4 text-success-text" />
                : <CircleAlert aria-hidden className="size-4 text-danger-text" />}
              <span className="shrink-0">{fmtWhen(r.scheduled_for)}</span>
              <span className="shrink-0 text-muted">· {RUN_LABEL[r.status]}</span>
              {!r.seen && r.status !== "running" && <span className="shrink-0 rounded-full bg-accent px-1.5 text-xs leading-5 text-on-accent">New</span>}
              <span className="min-w-0 flex-1 truncate text-muted">{r.summary}</span>
              {r.conversation_id && (
                <Link href={`/c/${r.conversation_id}`} className={cn("shrink-0 text-accent-text underline-offset-2 hover:underline", focusRing)}>
                  Open<span className="sr-only"> the {fmtWhen(r.scheduled_for)} result</span>
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
      {editing && <TaskDialog open={editing} onOpenChange={setEditing} task={t} />}
      <Dialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Delete ${t.title}?`}
        description="It stops running. Chats from earlier runs stay in your history."
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(false)}>Cancel</Button>
            <Button variant="danger" onClick={() => act(() => api.deleteTask(t.id), "Task deleted.").then(() => setConfirm(false))}>Delete task</Button>
          </>
        }
      />
    </li>
  );
}

export default function ScheduledPage() {
  const anyRunning = (d?: TaskItem[]) => !!d?.some((t) => t.runs.some((r) => r.status === "running"));
  const { data } = useSWR<TaskItem[]>("/api/tasks", { refreshInterval: (d) => (anyRunning(d) ? 2000 : 30_000) });
  const [creating, setCreating] = useState(false);
  const unseen = data?.some((t) => t.runs.some((r) => !r.seen && r.status !== "running"));
  // Opening the page counts as seeing new results.
  useEffect(() => {
    if (unseen) api.markTasksSeen().then(() => mutate("/api/me"));
  }, [unseen]);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader right={<Button size="sm" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>New task</Button>} />
      <main id="main" className="mx-auto flex w-full max-w-3xl flex-col gap-6 overflow-y-auto px-4 pb-10">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">Scheduled</h1>
          <p className="text-sm text-muted">Tasks the assistant runs on its own, like a Monday drop recap. Each run saves a chat; results arrive within about five minutes of the set time.</p>
        </div>
        {!data ? (
          <div aria-busy="true" className="flex flex-col gap-3">{[1, 2].map((i) => <Skeleton key={i} className="h-28" />)}</div>
        ) : data.length === 0 ? (
          <EmptyState icon={<CalendarClock />} title="Nothing scheduled" action={<Button size="sm" variant="secondary" onClick={() => setCreating(true)}>New task</Button>}>
            Ask for something once or on repeat: a weekly news roundup, a reminder before a drop, a monthly sales-copy refresh.
          </EmptyState>
        ) : (
          <ul aria-label="Tasks" className="flex flex-col gap-3">{data.map((t) => <TaskCard key={t.id} t={t} />)}</ul>
        )}
      </main>
      {creating && <TaskDialog open={creating} onOpenChange={setCreating} />}
    </div>
  );
}
