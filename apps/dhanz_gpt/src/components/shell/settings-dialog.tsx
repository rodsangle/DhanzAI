"use client";

import { Dialog as D, Tabs as T } from "radix-ui";
import { Bell, Database, KeyRound, LayoutGrid, Settings2, Sparkles, UserRound, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import useSWR, { mutate } from "swr";
import { api } from "@/lib/api";
import type { ConversationListItem, Memory, Personalization } from "@/lib/data/types";
import { Dialog } from "@/components/ui/overlays";
import { cn, focusRing } from "@/lib/cn";
import { Button, IconButton, button } from "@/components/ui/button";
import { Badge, Banner, useToast } from "@/components/ui/feedback";
import { Textarea } from "@/components/ui/field";
import { RadioGroup, Switch } from "@/components/ui/controls";
import { applyTheme, useUI } from "./providers";
import { AppsList } from "@/components/apps/apps-list";
import { currentEndpoint, disablePush, enablePush, pushSupported } from "@/lib/push-client";

const SECTIONS = [
  { id: "general", label: "General", icon: Settings2 },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "personalization", label: "Personalization", icon: Sparkles },
  { id: "apps", label: "Apps", icon: LayoutGrid },
  { id: "data", label: "Data controls", icon: Database },
  { id: "security", label: "Security", icon: KeyRound },
  { id: "account", label: "Account", icon: UserRound },
] as const;

function Row({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 border-b border-border py-4 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-col gap-0.5">
        <p className="text-sm font-medium">{title}</p>
        {description && <p className="text-xs text-muted">{description}</p>}
      </div>
      {children}
    </div>
  );
}

function General() {
  const { me } = useUI();
  const toast = useToast();
  async function setTheme(theme: "system" | "light" | "dark") {
    applyTheme(theme);
    await api.updateProfile({ theme });
    mutate("/api/me");
  }
  return (
    <div>
      <div className="border-b border-border py-4">
        <RadioGroup
          label="Theme"
          value={me?.profile.theme ?? "system"}
          onValueChange={(v) => setTheme(v as "system" | "light" | "dark")}
          options={[
            { value: "system", label: "Match my device" },
            { value: "light", label: "Light" },
            { value: "dark", label: "Dark" },
          ]}
        />
      </div>
      <Row title="Language" description="The language of menus and labels.">
        <select
          aria-label="Language"
          value={me?.profile.locale ?? "en"}
          onChange={async (e) => {
            await api.updateProfile({ locale: e.target.value });
            mutate("/api/me");
            toast({ title: "Language saved. More languages are on the way." });
          }}
          className={cn("h-9 rounded-md border border-border-input bg-bg px-2 text-sm", focusRing)}
        >
          <option value="en">English</option>
          <option value="es">Español</option>
        </select>
      </Row>
      <Row title="Keyboard shortcuts" description="⌘K search · ⌘⇧O new chat · ⌘⇧S toggle sidebar · Esc stop answering" />
    </div>
  );
}

function PersonalizationPanel() {
  const { data } = useSWR<Personalization>("/api/personalization");
  if (!data) return <p className="py-4 text-sm text-muted">Loading…</p>;
  return <PersonalizationForm data={data} />;
}

function PersonalizationForm({ data }: { data: Personalization }) {
  const [about, setAbout] = useState(data.about_you);
  const [style, setStyle] = useState(data.response_style);
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  const dirty = about !== data.about_you || style !== data.response_style;
  async function toggle(patch: Partial<Personalization>, done: string) {
    try {
      await mutate("/api/personalization", api.savePersonalization(patch), { optimisticData: { ...data, ...patch }, rollbackOnError: true, revalidate: false });
      toast({ title: done });
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    }
  }
  async function save() {
    setSaving(true);
    try {
      await mutate("/api/personalization", api.savePersonalization({ about_you: about, response_style: style }), { revalidate: false });
      toast({ title: "Saved. New answers will follow these instructions." });
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="flex flex-col gap-4 py-4">
      <Textarea
        label="What should the assistant know about you?"
        placeholder="Your role, what you work on, the brands and products you write about."
        value={about}
        maxLength={3000}
        onChange={(e) => setAbout(e.target.value)}
        hint={`${about.length} / 3,000`}
      />
      <Textarea
        label="How should it respond?"
        placeholder="Tone, length, format. For example: “Direct. Give me options, not essays.”"
        value={style}
        maxLength={3000}
        onChange={(e) => setStyle(e.target.value)}
        hint={`${style.length} / 3,000`}
      />
      <div className="flex justify-end">
        <Button onClick={save} loading={saving} disabled={!dirty}>Save</Button>
      </div>
      <div className="flex flex-col gap-4 border-t border-border pt-4">
        <Switch
          label="Memory"
          description="Remember useful details about you and your work across chats. Never used in temporary chats."
          checked={data.memory_enabled}
          onCheckedChange={(v) => toggle({ memory_enabled: v }, v ? "Memory is on." : "Memory is off. Nothing new will be remembered.")}
        />
        <Switch
          label="Reference chat history"
          description={data.memory_enabled ? "Bring in relevant earlier chats when answering." : "Needs memory to be on."}
          checked={data.memory_enabled && data.reference_chat_history}
          disabled={!data.memory_enabled}
          onCheckedChange={(v) => toggle({ reference_chat_history: v }, v ? "Earlier chats will be used." : "Earlier chats won't be used.")}
        />
        <MemorySummaryRow enabled={data.memory_enabled} />
      </div>
    </div>
  );
}

function MemorySummaryRow({ enabled }: { enabled: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <Row title="Memory summary" description="See and correct what the assistant remembers about you.">
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Memory summary"
        description="What the assistant remembers from your chats. Edit anything that's wrong, or delete it all."
        size="lg"
        trigger={<Button variant="secondary" size="sm">Manage</Button>}
      >
        {open && <MemoryEditor enabled={enabled} onDone={() => setOpen(false)} />}
      </Dialog>
    </Row>
  );
}

function MemoryEditor({ enabled, onDone }: { enabled: boolean; onDone: () => void }) {
  const { data } = useSWR<Memory>("/api/memory");
  if (!data) return <p role="status" className="py-4 text-sm text-muted">Loading memory</p>;
  return <MemoryForm key={data.updated_at ?? "empty"} data={data} enabled={enabled} onDone={onDone} />;
}

function MemoryForm({ data, enabled, onDone }: { data: Memory; enabled: boolean; onDone: () => void }) {
  const [body, setBody] = useState(data.body);
  const [busy, setBusy] = useState<null | "save" | "refresh" | "delete">(null);
  const [confirming, setConfirming] = useState(false);
  const toast = useToast();
  async function run(kind: "save" | "refresh" | "delete", fn: () => Promise<unknown>, done: string) {
    setBusy(kind);
    try {
      await fn();
      toast({ title: done });
      if (kind === "delete") onDone();
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="flex flex-col gap-4">
      {!enabled && <Banner tone="info" title="Memory is off">Nothing new is remembered and this summary isn&apos;t used in answers.</Banner>}
      <Textarea
        label="Remembered"
        placeholder="Nothing yet. As you chat, durable details (your role, projects, preferences) show up here."
        value={body}
        rows={10}
        maxLength={6000}
        onChange={(e) => setBody(e.target.value)}
        hint={data.refreshed_at ? `Last updated from your chats ${new Date(data.refreshed_at).toLocaleString()}` : "Not updated from your chats yet"}
      />
      {confirming ? (
        <Banner
          tone="danger"
          title="Delete memory and turn it off?"
          action={
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button>
              <Button
                size="sm"
                variant="danger"
                loading={busy === "delete"}
                onClick={() =>
                  run("delete", async () => {
                    await api.deleteMemory();
                    await Promise.all([mutate("/api/memory"), mutate("/api/personalization")]);
                  }, "Memory deleted and turned off.")
                }
              >
                Delete
              </Button>
            </div>
          }
        >
          This can&apos;t be undone. Your chats stay; only the summary is deleted.
        </Banner>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button variant="ghost" size="sm" onClick={() => setConfirming(true)} disabled={!data.body && !enabled}>
            Delete memory and turn off
          </Button>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={!enabled}
              loading={busy === "refresh"}
              onClick={() => run("refresh", async () => {
                const m = await api.refreshMemory();
                setBody(m.body);
                await mutate("/api/memory", m, { revalidate: false });
              }, "Memory updated from your recent chats.")}
            >
              Refresh from chats
            </Button>
            <Button
              size="sm"
              disabled={body.trim() === data.body.trim()}
              loading={busy === "save"}
              onClick={() => run("save", async () => {
                const m = await api.saveMemory(body);
                await mutate("/api/memory", m, { revalidate: false });
              }, "Memory saved.")}
            >
              Save
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function DataControls() {
  const { data: shares } = useSWR<{ slug: string; title: string; updated_at: string }[]>("/api/shares");
  const { data: archived } = useSWR<ConversationListItem[]>("/api/conversations?archived=1");
  const toast = useToast();
  return (
    <div>
      <div className="border-b border-border py-4">
        <p className="mb-2 text-sm font-medium">Shared links</p>
        {!shares?.length ? (
          <p className="text-xs text-muted">You haven&apos;t shared any chats.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {shares.map((s) => (
              <li key={s.slug} className="flex items-center justify-between gap-2 text-sm">
                <a href={`/s/${s.slug}`} target="_blank" rel="noreferrer" className={cn("truncate text-accent-text underline-offset-2 hover:underline", focusRing)}>
                  {s.title}
                </a>
                <Button size="sm" variant="ghost" onClick={async () => { await api.deleteShare(s.slug); mutate("/api/shares"); toast({ title: "Link deleted" }); }}>
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="border-b border-border py-4">
        <p className="mb-2 text-sm font-medium">Archived chats</p>
        {!archived?.length ? (
          <p className="text-xs text-muted">Nothing archived.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {archived.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-2 text-sm">
                <Link href={`/c/${c.id}`} className={cn("truncate hover:underline", focusRing)}>{c.title}</Link>
                <Button size="sm" variant="ghost" onClick={async () => { await api.updateConversation(c.id, { archived: false }); mutate("/api/conversations?archived=1"); mutate("/api/conversations"); }}>
                  Restore
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <ExportRow />
      <DeleteAllChatsRow />
    </div>
  );
}

type ExportState = { id: string; status: "queued" | "running" | "ready" | "failed" | "expired"; created_at: string; expires_at: string | null } | null;

function ExportRow() {
  const { data, mutate: refresh } = useSWR<ExportState>("/api/account/export", {
    refreshInterval: (d) => (d && (d.status === "queued" || d.status === "running") ? 2000 : 0),
  });
  const { me } = useUI();
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const working = data?.status === "queued" || data?.status === "running";
  const ready = data?.status === "ready" && !!data.expires_at;
  async function start() {
    setBusy(true);
    try {
      await refresh(await api.requestExport(), { revalidate: false });
      toast({ title: me?.features?.email ? "Preparing your export. We'll email you when it's ready." : "Preparing your export. It'll be ready here in a few minutes." });
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Row
      title="Export your data"
      description={
        working
          ? "Preparing your export…"
          : ready
            ? `Ready. The download works until ${new Date(data!.expires_at!).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}.`
            : data?.status === "failed"
              ? "The last export didn't finish. Try again."
              : data?.status === "expired"
                ? "Your last export expired. Make a new one."
              : "A zip of your chats, projects, assistants, settings, memory and files."
      }
    >
      <div className="flex gap-2" aria-live="polite">
        {ready && (
          <a href={`/api/account/export/${data!.id}/download`} className={cn(button({ variant: "primary", size: "sm" }), focusRing)}>
            Download
          </a>
        )}
        <Button size="sm" variant="secondary" loading={busy || working} disabled={working} onClick={start}>
          {working ? "Preparing" : ready ? "New export" : "Export"}
        </Button>
      </div>
    </Row>
  );
}

function DeleteAllChatsRow() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  async function run() {
    setBusy(true);
    try {
      const { deleted } = await api.deleteAllChats();
      setOpen(false);
      toast({ title: deleted === 1 ? "Deleted 1 chat." : `Deleted ${deleted} chats.` });
      // Whatever chat was open is gone: start fresh.
      window.location.assign("/");
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Row title="Delete all chats" description="Every chat you own, including archived chats and chats in projects. Your Library files and memory stay.">
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Delete all chats?"
        description="This permanently deletes every chat you own and their shared links. It can't be undone."
        size="sm"
        trigger={<Button size="sm" variant="danger">Delete all</Button>}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="danger" loading={busy} onClick={run}>Delete all chats</Button>
          </>
        }
      />
    </Row>
  );
}

type DeviceSession = { id: string; created_at: string; last_active: string; device: string; ip_hint: string | null; current: boolean };

function lastActive(iso: string) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 2) return "Active now";
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (mins < 60) return `Active ${rtf.format(-mins, "minute")}`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `Active ${rtf.format(-hours, "hour")}`;
  return `Active ${rtf.format(-Math.round(hours / 24), "day")}`;
}

function Sessions() {
  const toast = useToast();
  const { data, error, isLoading } = useSWR<DeviceSession[]>("/api/account/sessions");
  const [busy, setBusy] = useState<string | null>(null);
  const others = (data ?? []).filter((x) => !x.current);

  async function signOutOne(x: DeviceSession) {
    setBusy(x.id);
    try {
      await fetch(`/api/account/sessions/${x.id}`, { method: "DELETE" }).then(async (r) => {
        if (!r.ok && r.status !== 404) throw new Error((await r.json().catch(() => null))?.error ?? "Couldn't sign that device out.");
      });
      toast({ title: `Signed out ${x.device}` });
      await mutate("/api/account/sessions");
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setBusy(null);
    }
  }
  async function signOutOthers() {
    setBusy("others");
    try {
      const r = await fetch("/api/account/sessions/others", { method: "POST" });
      if (!r.ok) throw new Error("Couldn't sign the other devices out.");
      const { signed_out } = (await r.json()) as { signed_out: number };
      toast({ title: signed_out === 1 ? "Signed out 1 other device" : `Signed out ${signed_out} other devices` });
      await mutate("/api/account/sessions");
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-labelledby="sessions-h" className="border-b border-border py-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-0.5">
          <h3 id="sessions-h" className="text-sm font-medium">Where you&apos;re signed in</h3>
          <p className="text-xs text-muted">Sign out a device you don&apos;t recognise, or one you&apos;ve lost.</p>
        </div>
        {others.length > 0 && (
          <Button variant="secondary" size="sm" loading={busy === "others"} onClick={signOutOthers}>
            Sign out other devices
          </Button>
        )}
      </div>
      {isLoading ? (
        <ul aria-label="Loading devices" className="mt-3 flex flex-col gap-2">
          {[0, 1].map((i) => <li key={i} className="h-12 animate-pulse rounded-md bg-surface-muted" />)}
        </ul>
      ) : error ? (
        <p className="mt-3 text-sm text-danger-text">Couldn&apos;t load your devices. Close Settings and try again.</p>
      ) : (
        <ul aria-label="Signed-in devices" className="mt-3 flex flex-col divide-y divide-border rounded-md border border-border">
          {(data ?? []).map((x) => (
            <li key={x.id} className="flex items-center justify-between gap-3 px-3 py-2.5">
              <div className="flex min-w-0 flex-col gap-0.5">
                <p className="flex items-center gap-2 text-sm">
                  <span className="truncate">{x.device}</span>
                  {x.current && <Badge tone="success">This device</Badge>}
                </p>
                <p className="text-xs text-muted">
                  {x.current ? "Active now" : lastActive(x.last_active)}
                  {x.ip_hint && <> · {x.ip_hint}</>}
                  {" · "}Signed in {new Date(x.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                </p>
              </div>
              {!x.current && (
                <Button variant="ghost" size="sm" loading={busy === x.id} onClick={() => signOutOne(x)} aria-label={`Sign out ${x.device}, ${lastActive(x.last_active).toLowerCase()}`}>
                  Sign out
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Security() {
  const [busy, setBusy] = useState(false);
  return (
    <div>
      <Row title="Two-step verification" description="Set up in your Google account. Sign-in to the Assistant goes through Google." />
      <Sessions />
      <Row title="Sign out of all devices" description="Ends every session, including this one.">
        <Button
          variant="secondary"
          loading={busy}
          onClick={async () => {
            setBusy(true);
            await api.signOut(true).catch(() => {});
            window.location.href = "/login";
          }}
        >
          Sign out everywhere
        </Button>
      </Row>
    </div>
  );
}

function DeleteAccount() {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <Row title="Delete account" description="Permanently deletes your chats, projects you own, files and settings.">
        <Button variant="ghost" className="text-danger-text" onClick={() => setOpen(true)}>Delete account</Button>
      </Row>
      <D.Root open={open} onOpenChange={setOpen}>
        <D.Portal>
          <D.Overlay className="fixed inset-0 z-[var(--z-modal)] bg-overlay" />
          <D.Content className="fixed left-1/2 top-1/2 z-[var(--z-modal)] w-[calc(100vw-2rem)] max-w-[var(--modal-sm)] -translate-x-1/2 -translate-y-1/2 rounded-xl bg-surface-raised p-6 text-fg shadow-lg">
            <D.Title className="text-xl font-semibold">Delete your account?</D.Title>
            <D.Description className="mt-1 text-sm text-muted">
              This can&apos;t be undone. Chats in projects you own are deleted for everyone in them. Type DELETE to confirm.
            </D.Description>
            <form
              className="mt-4 flex flex-col gap-4"
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                setError(null);
                try {
                  await api.deleteAccount();
                  window.location.href = "/login";
                } catch (err) {
                  setError((err as Error).message);
                  setBusy(false);
                }
              }}
            >
              {error && <Banner tone="danger" title="Not deleted">{error}</Banner>}
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Type DELETE
                <input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" className={cn("h-10 rounded-md border border-border-input bg-bg px-3 text-sm", focusRing)} />
              </label>
              <div className="flex justify-end gap-2">
                <D.Close asChild><Button variant="secondary" autoFocus>Cancel</Button></D.Close>
                <Button type="submit" variant="danger" disabled={typed !== "DELETE"} loading={busy}>Delete account</Button>
              </div>
            </form>
          </D.Content>
        </D.Portal>
      </D.Root>
    </>
  );
}

function Account() {
  const { me } = useUI();
  return (
    <div>
      <Row title="Name" description={me?.profile.name} />
      <Row title="Email" description={me?.profile.email} />
      <Row title="Workspace" description={`${me?.workspace.name} · ${me?.role}`} />
      <Row
        title="Usage today"
        description={me ? `${me.usage.messages} of ${me.usage.limits.messages} messages, ${me.usage.images} of ${me.usage.limits.images} images. Resets at midnight.` : ""}
      />
      <div className="pt-4">
        <Button variant="secondary" onClick={() => api.signOut().then(() => (window.location.href = "/login"))}>Sign out</Button>
      </div>
      <DeleteAccount />
    </div>
  );
}

function NotificationsPanel() {
  const { me } = useUI();
  const toast = useToast();
  const supported = pushSupported();
  const [endpoint, setEndpoint] = useState<string | null | undefined>(undefined);
  const { data: status, mutate: refresh } = useSWR<{ configured: boolean; publicKey: string | null; subscribed: boolean }>(
    endpoint === undefined ? null : `/api/push${endpoint ? `?endpoint=${encodeURIComponent(endpoint)}` : ""}`,
  );
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    currentEndpoint().then(setEndpoint, () => setEndpoint(null));
  }, []);
  async function toggle(on: boolean) {
    setBusy(true);
    try {
      if (on) await enablePush(status!.publicKey!);
      else await disablePush();
      const ep = await currentEndpoint();
      setEndpoint(ep);
      await refresh();
      toast({ title: on ? "Notifications are on for this browser." : "Notifications are off for this browser." });
    } catch (e) {
      toast({ title: (e as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      {status?.configured === false ? (
        <Row title="Push notifications" description="Not set up for this workspace yet. An admin adds the VAPID keys (see backend.md)." />
      ) : !supported ? (
        <Row title="Push notifications" description="This browser can't receive push notifications." />
      ) : (
        <Switch
          label="Push notifications on this browser"
          description="Scheduled task results, even when this tab is closed. Each browser is turned on separately."
          checked={!!status?.subscribed}
          disabled={busy || !status}
          onCheckedChange={toggle}
        />
      )}
      <Row
        title="Email"
        description={
          me?.features?.email
            ? `Tasks set to email you send results to ${me.profile.email}. Pick per task in Scheduled.`
            : "Email isn't set up for this workspace yet."
        }
      />
    </div>
  );
}

const PANELS: Record<string, () => ReactNode> = {
  general: General,
  notifications: NotificationsPanel,
  personalization: PersonalizationPanel,
  apps: () => (
    <div className="py-4">
      <AppsList />
    </div>
  ),
  data: DataControls,
  security: Security,
  account: Account,
};

export function SettingsDialog() {
  const { settings, openSettings } = useUI();
  const section = settings ?? "general";
  return (
    <D.Root open={!!settings} onOpenChange={(o) => !o && openSettings(null)}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[var(--z-modal)] bg-overlay" />
        <D.Content
          aria-describedby={undefined}
          className="fixed inset-0 z-[var(--z-modal)] flex flex-col bg-surface-raised text-fg sm:inset-auto sm:left-1/2 sm:top-1/2 sm:h-[min(640px,85vh)] sm:w-[calc(100vw-2rem)] sm:max-w-[var(--modal-lg)] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-xl sm:shadow-lg"
        >
          <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-5">
            <D.Title className="text-lg font-semibold">Settings</D.Title>
            <D.Close asChild>
              <IconButton label="Close settings" tooltip={false}><X /></IconButton>
            </D.Close>
          </div>
          <T.Root value={section} onValueChange={openSettings} orientation="vertical" className="flex min-h-0 flex-1 flex-col sm:flex-row">
            <T.List aria-label="Settings sections" className="flex shrink-0 gap-1 overflow-x-auto border-b border-border p-2 sm:w-48 sm:flex-col sm:border-b-0 sm:border-r">
              {SECTIONS.map((s) => (
                <T.Trigger
                  key={s.id}
                  value={s.id}
                  className={cn(
                    "flex h-9 shrink-0 items-center gap-2 rounded-md px-2.5 text-sm text-muted hover:bg-surface-hover hover:text-fg data-[state=active]:bg-surface-active data-[state=active]:text-fg [&_svg]:size-4",
                    focusRing, "focus-visible:outline-offset-0",
                  )}
                >
                  <s.icon aria-hidden /> {s.label}
                </T.Trigger>
              ))}
            </T.List>
            {SECTIONS.map((s) => {
              const Panel = PANELS[s.id];
              return (
                <T.Content key={s.id} value={s.id} className="min-h-0 flex-1 overflow-y-auto px-5 outline-hidden">
                  <h3 className="sr-only">{s.label}</h3>
                  <Panel />
                </T.Content>
              );
            })}
          </T.Root>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
