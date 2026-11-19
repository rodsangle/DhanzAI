"use client";

import { BRAND } from "@/lib/brand";
import {
  Archive, FolderOpen, Hash, ImagePlus, Moon, Pencil, Plus, Search, Share, ShoppingBag, Sun, Trash2,
} from "lucide-react";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { Button, IconButton } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { TextInput, Textarea } from "@/components/ui/field";
import { Checkbox, RadioGroup, Switch, Tabs } from "@/components/ui/controls";
import { Dialog, DialogClose, Drawer, Menu, MenuCheckItem, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@/components/ui/overlays";
import { Avatar, Badge, Banner, EmptyState, Skeleton, Spinner, ToastProvider, useToast } from "@/components/ui/feedback";
import { Composer, type Attachment } from "@/components/chat/composer";
import { AssistantMessage, BranchSwitcher, CitationChip, CodeBlock, MessageActions, ThinkingIndicator, UserMessage } from "@/components/chat/message";
import { ApprovalCard, ChatRow, ProgressTimeline, SidebarSection, TaskCard } from "@/components/chat/cards";

const COLOR_ROLES = [
  "bg", "surface", "surface-raised", "surface-muted", "surface-hover", "surface-active", "code-bg", "border", "border-strong",
  "border-input", "text", "text-muted", "text-subtle", "accent", "accent-hover", "on-accent", "accent-text", "focus",
  "danger", "danger-text", "danger-subtle", "success-text", "success-subtle", "warning-text", "warning-subtle", "info-text", "info-subtle",
];

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="flex flex-col gap-4 border-t border-border pt-8">
      <h2 id={`${id}-h`} className="text-2xl font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Sub({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-muted">{title}</h3>
      {children}
    </div>
  );
}

function DemoComposer(props: { variant?: "home" | "thread"; initialAttachments?: Attachment[]; streaming?: boolean; disabled?: boolean; placeholder?: string }) {
  const [value, setValue] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>(props.initialAttachments ?? []);
  return (
    <Composer
      value={value}
      onChange={setValue}
      onSend={() => setValue("")}
      attachments={attachments}
      onRemoveAttachment={(id) => setAttachments((a) => a.filter((x) => x.id !== id))}
      variant={props.variant}
      streaming={props.streaming}
      disabled={props.disabled}
      disabledReason={props.placeholder}
      placeholder={props.placeholder}
    />
  );
}

function ToastDemo() {
  const toast = useToast();
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" onClick={() => toast({ title: "Link copied" })}>Neutral toast</Button>
      <Button variant="secondary" onClick={() => toast({ title: "Chat deleted", action: { label: "Undo", onClick: () => {} } })}>Toast with Undo</Button>
      <Button variant="secondary" onClick={() => toast({ title: "Upload failed: file is over 512 MB", tone: "error" })}>Error toast</Button>
    </div>
  );
}

function setTheme(dark: boolean) {
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.classList.toggle("light", !dark);
}

/** Reads the theme from the <html> class so the toggle stays in sync without effects. */
function useIsDark() {
  return useSyncExternalStore(
    (cb) => {
      const mo = new MutationObserver(cb);
      mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
      return () => mo.disconnect();
    },
    () => document.documentElement.classList.contains("dark"),
    () => false,
  );
}

export default function DesignPage() {
  const dark = useIsDark();
  const [model, setModel] = useState("sonnet");

  // ?theme=dark|light sets the starting theme (used for screenshots).
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("theme");
    if (q === "dark" || q === "light") setTheme(q === "dark");
  }, []);

  return (
    <TooltipProvider>
      <ToastProvider>
        <main className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-10 text-fg">
          <header className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1">
              <h1 className="text-3xl font-semibold">{BRAND.name}: design system</h1>
              <p className="text-sm text-muted">
                Tokens from <code className="rounded-sm bg-surface-muted px-1 font-mono text-[0.9em]">replica/design/tokens.json</code>.
                Accent is a neutral placeholder until /replica-brand.
              </p>
            </div>
            <Button variant="secondary" icon={dark ? <Sun className="size-4" /> : <Moon className="size-4" />} onClick={() => setTheme(!dark)}>
              {dark ? "Light" : "Dark"} mode
            </Button>
          </header>

          <Section id="color" title="Colour roles">
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {COLOR_ROLES.map((r) => (
                <li key={r} className="flex items-center gap-2.5">
                  <span aria-hidden className="size-9 shrink-0 rounded-md border border-border" style={{ background: `var(--${r})` }} />
                  <span className="font-mono text-xs">{r}</span>
                </li>
              ))}
            </ul>
          </Section>

          <Section id="type" title="Type, radius, shadow">
            <div className="flex flex-col gap-2">
              {(["3xl", "2xl", "xl", "lg", "base", "sm", "xs"] as const).map((s) => (
                <p key={s} className={`text-${s}`}>
                  <span className="inline-block w-14 font-mono text-xs text-muted">{s}</span> Built for the drop, not the algorithm
                </p>
              ))}
              <p className="font-mono text-sm"><span className="inline-block w-14 text-xs text-muted">mono</span>const drop = await getCollection(&quot;FW26&quot;)</p>
            </div>
            <div className="flex flex-wrap gap-4">
              {["sm", "md", "lg", "xl", "full"].map((r) => (
                <div key={r} className="flex size-20 items-center justify-center border border-border-strong bg-surface-muted text-xs" style={{ borderRadius: `var(--radius-${r})` }}>
                  {r}
                </div>
              ))}
              {["sm", "md", "lg"].map((s) => (
                <div key={s} className="flex size-20 items-center justify-center rounded-lg bg-surface-raised text-xs" style={{ boxShadow: `var(--shadow-${s})` }}>
                  shadow {s}
                </div>
              ))}
            </div>
          </Section>

          <Section id="buttons" title="Buttons">
            <Sub title="Variants">
              <div className="flex flex-wrap items-center gap-2">
                <Button>Primary</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="ghost">Ghost</Button>
                <Button variant="danger" icon={<Trash2 className="size-4" />}>Delete</Button>
                <Button variant="link">Link</Button>
              </div>
            </Sub>
            <Sub title="Sizes and states">
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm">Small</Button>
                <Button size="md">Medium</Button>
                <Button size="lg">Large</Button>
                <Button loading>Saving</Button>
                <Button disabled>Disabled</Button>
                <Button variant="secondary" loading>Creating link</Button>
              </div>
            </Sub>
            <Sub title="Icon buttons (hover for tooltips)">
              <div className="flex flex-wrap items-center gap-2">
                <IconButton label="Search chats"><Search /></IconButton>
                <IconButton label="New chat" variant="secondary"><Plus /></IconButton>
                <IconButton label="Share" size="lg"><Share /></IconButton>
                <IconButton label="Create image" variant="solid"><ImagePlus /></IconButton>
                <IconButton label="Archive" disabled><Archive /></IconButton>
              </div>
            </Sub>
          </Section>

          <Section id="forms" title="Form controls">
            <div className="grid gap-6 md:grid-cols-2">
              <div className="flex flex-col gap-4">
                <TextInput label="Project name" placeholder="FW26 drop" hint="Shown in the sidebar." />
                <TextInput label="Search" hideLabel leading={<Search />} placeholder="Search chats and files" />
                <TextInput label="Shop domain" defaultValue="your-store.myshopify" error="Add .com to the end of the domain." />
                <TextInput label="Disabled" disabled placeholder="Can't edit" />
                <Textarea label="Project instructions" placeholder="How should the assistant write for this project?" hint="Applied to every chat in this project." />
              </div>
              <div className="flex flex-col gap-5">
                <Switch label="Memory" description="Let the assistant remember useful details across chats." defaultChecked />
                <Switch label="Reference chat history" description="Use past chats to personalise answers." />
                <Switch label="Disabled switch" disabled />
                <div className="flex flex-col gap-2">
                  <Checkbox label="Email me when a task finishes" defaultChecked />
                  <Checkbox label="Push notifications" />
                  <Checkbox label="Select all files" checked="indeterminate" />
                </div>
                <RadioGroup
                  label="When should it ask before using an app?"
                  defaultValue="important"
                  options={[
                    { value: "always_ask", label: "Always ask", description: "Ask before reading or changing anything." },
                    { value: "any_changes", label: "Before any change", description: "Read freely, ask before changing anything." },
                    { value: "important", label: "Before important actions", description: "Recommended." },
                    { value: "never_ask", label: "Never ask", description: "Actions run without a confirmation." },
                  ]}
                />
              </div>
            </div>
          </Section>

          <Section id="overlays" title="Menus, dialogs, drawers, tabs">
            <div className="flex flex-wrap gap-2">
              <Menu>
                <MenuTrigger asChild><Button variant="ghost" size="lg" className="text-lg font-semibold">Model: {model === "sonnet" ? "Balanced" : model === "opus" ? "Deep" : "Fast"}</Button></MenuTrigger>
                <MenuContent>
                  <MenuLabel>Model</MenuLabel>
                  <MenuCheckItem checked={model === "sonnet"} onCheckedChange={() => setModel("sonnet")} description="Everyday writing and ideas">Balanced</MenuCheckItem>
                  <MenuCheckItem checked={model === "opus"} onCheckedChange={() => setModel("opus")} description="Thinks longer for hard problems">Deep</MenuCheckItem>
                  <MenuCheckItem checked={model === "haiku"} onCheckedChange={() => setModel("haiku")} description="Quick answers">Fast</MenuCheckItem>
                </MenuContent>
              </Menu>
              <Menu>
                <MenuTrigger asChild><Button variant="secondary">Chat options</Button></MenuTrigger>
                <MenuContent>
                  <MenuItem icon={<Share />}>Share</MenuItem>
                  <MenuItem icon={<Pencil />}>Rename</MenuItem>
                  <MenuItem icon={<FolderOpen />}>Move to project</MenuItem>
                  <MenuItem icon={<Archive />}>Archive</MenuItem>
                  <MenuSeparator />
                  <MenuItem icon={<Trash2 />} destructive>Delete</MenuItem>
                </MenuContent>
              </Menu>
              <Dialog
                trigger={<Button variant="secondary">Confirm dialog</Button>}
                size="sm"
                title="Delete this chat?"
                description="This deletes “Hang tag copy, round 3” for good. You can't undo this."
                footer={
                  <>
                    <DialogClose asChild><Button variant="secondary" autoFocus>Cancel</Button></DialogClose>
                    <Button variant="danger">Delete</Button>
                  </>
                }
              />
              <Dialog trigger={<Button variant="secondary">Share dialog</Button>} title="Share chat" description="Anyone at RODRECH with the link can read this chat as it is now.">
                <div className="flex flex-col gap-3">
                  <TextInput label="Link" readOnly value="https://gpt.dhanzai.com/s/9f2c41e0a7b3" className="font-mono" />
                  <div className="flex justify-end gap-2"><Button variant="ghost">Delete link</Button><Button>Copy link</Button></div>
                </div>
              </Dialog>
              <Drawer trigger={<Button variant="secondary">Sources drawer</Button>} title="Sources">
                <ul className="flex flex-col gap-3 text-sm">
                  <li><p className="font-medium">Shopify Admin: Product listing guide</p><p className="text-xs text-muted">shopify.com</p></li>
                  <li><p className="font-medium">FW26 lookbook brief.pdf</p><p className="text-xs text-muted">Project file</p></li>
                </ul>
              </Drawer>
            </div>
            <Tabs
              defaultValue="all"
              variant="pill"
              tabs={[
                { value: "all", label: "All files", content: <p className="text-sm text-muted">All files you’ve uploaded or created.</p> },
                { value: "images", label: "Images", content: <p className="text-sm text-muted">Generated and uploaded images.</p> },
                { value: "docs", label: "Documents", content: <p className="text-sm text-muted">PDFs, docs and sheets.</p> },
              ]}
            />
            <Tabs
              defaultValue="general"
              tabs={[
                { value: "general", label: "General", content: <p className="text-sm text-muted">Theme and language.</p> },
                { value: "personal", label: "Personalization", content: <p className="text-sm text-muted">Custom instructions and memory.</p> },
                { value: "data", label: "Data controls", content: <p className="text-sm text-muted">Shared links, export, delete.</p> },
              ]}
            />
          </Section>

          <Section id="feedback" title="Feedback and status">
            <div className="flex flex-col gap-3">
              <Banner tone="info" title="Temporary chat">This chat won’t be saved to your history or used for memory.</Banner>
              <Banner tone="warning" title="You’ve used 92 of 100 images today" onDismiss={() => {}}>The limit resets at midnight ET.</Banner>
              <Banner tone="danger" title="You're offline">Messages will send when you reconnect.</Banner>
              <Banner tone="success" title="Google Drive connected">Ask about any file with @Drive.</Banner>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge>Generated</Badge><Badge tone="accent">New</Badge><Badge tone="success">Connected</Badge>
              <Badge tone="warning">Paused</Badge><Badge tone="danger">Expired</Badge><Badge tone="info">Beta</Badge>
              <Avatar name="Dante Rodriguez" size={24} /><Avatar name="Dante Rodriguez" /><Avatar name="Maya Lee" size={40} />
              <Spinner />
            </div>
            <ToastDemo />
            <div className="grid gap-4 md:grid-cols-2">
              <div className="flex flex-col gap-2 rounded-lg border border-border p-4">
                <Skeleton className="h-4 w-2/3" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" />
              </div>
              <div className="rounded-lg border border-border">
                <EmptyState icon={<FolderOpen />} title="No files yet" action={<Button size="sm" variant="secondary">Upload a file</Button>}>
                  Files you upload or create show up here, ready to reuse in any chat.
                </EmptyState>
              </div>
            </div>
          </Section>

          <Section id="chat" title="Chat">
            <Sub title="Composer: home, with attachments, streaming, disabled">
              <div className="flex flex-col gap-4">
                <DemoComposer variant="home" placeholder="What are we making today?" />
                <DemoComposer
                  initialAttachments={[
                    { id: "1", name: "fw26-lookbook-brief.pdf", kind: "document", status: "ready", meta: "PDF · 2.4 MB" },
                    { id: "2", name: "shoot-notes.m4a", kind: "audio", status: "uploading", progress: 60, meta: "Audio" },
                    { id: "3", name: "hat-mockup.psd", kind: "document", status: "error" },
                  ]}
                />
                <DemoComposer streaming placeholder={`Message ${BRAND.name}`} />
                <DemoComposer disabled placeholder="Daily limit reached. Resets at midnight ET" />
              </div>
            </Sub>
            <Sub title="Thread">
              <div className="mx-auto flex w-full max-w-[var(--thread-max-width)] flex-col gap-8 rounded-xl border border-border bg-bg p-6">
                <UserMessage>Write three caption options for the FW26 snapback drop. Keep it lowercase and short.</UserMessage>
                <AssistantMessage
                  thinking={<ThinkingIndicator seconds={4} summary="Matched the brand voice from project instructions: lowercase, short, no emojis." />}
                  footer={
                    <div className="flex items-center gap-1">
                      <BranchSwitcher index={2} total={3} />
                      <MessageActions alwaysVisible />
                    </div>
                  }
                >
                  <p>Here are three takes, all under ten words:</p>
                  <ol className="list-decimal space-y-1 pl-6">
                    <li>built for the block. fw26 snapbacks, out friday.</li>
                    <li>new season, same crown. fw26 drops friday.</li>
                    <li>cap game, upgraded. limited run, friday 12pm.</li>
                  </ol>
                  <p>
                    Friday noon drops tend to do well for streetwear audiences<CitationChip title="shopify.com" href="https://www.shopify.com" />.
                    Want versions for stories too?
                  </p>
                  <CodeBlock language="json" code={`{\n  "product": "FW26 Snapback",\n  "drop": "2026-11-20T12:00:00-05:00",\n  "units": 250\n}`} />
                </AssistantMessage>
                <UserMessage>Now one for the hang tag.</UserMessage>
                <AssistantMessage status="streaming" thinking={<ThinkingIndicator running />}>
                  <p>For the hang tag, keep it to one line that works on a 2-inch card</p>
                </AssistantMessage>
                <AssistantMessage status="stopped"><p>Option one: crown</p></AssistantMessage>
                <AssistantMessage status="error"><p className="sr-only">No content</p></AssistantMessage>
              </div>
            </Sub>
          </Section>

          <Section id="agentic" title="Approvals, progress, tasks">
            <div className="grid gap-6 md:grid-cols-2">
              <div className="flex flex-col gap-4">
                <ApprovalCard
                  app="Slack" appIcon={<Hash />} action="post a message"
                  preview={[{ label: "Channel", value: "#fw26-launch" }, { label: "Message", value: "Caption options are ready for review: see the thread." }]}
                />
                <ApprovalCard
                  app="Shopify" appIcon={<ShoppingBag />} action="publish a product" importance="important"
                  preview={[{ label: "Product", value: "FW26 Snapback, Black" }, { label: "Status", value: "Draft → Active" }]}
                />
                <ApprovalCard app="Slack" appIcon={<Hash />} action="post a message" initial="denied" preview={[{ label: "Channel", value: "#general" }]} />
              </div>
              <div className="flex flex-col gap-4">
                <div className="rounded-lg border border-border p-4">
                  <ProgressTimeline
                    steps={[
                      { label: "Clarified the goal", status: "done", time: "0:04" },
                      { label: "Searched 14 sources on cap pricing", status: "done", detail: "Web, Shopify orders", time: "1:12" },
                      { label: "Reading competitor drops", status: "running", detail: "6 of 9 pages" },
                      { label: "Pull Shopify sales by colourway", status: "failed", detail: "Shopify connection expired" },
                      { label: "Write the report", status: "pending" },
                    ]}
                  />
                </div>
                <TaskCard title="Weekly drop recap" schedule="Mondays at 9:00 AM ET" next="Mon, Nov 23" status="active" />
                <TaskCard title="Restock watch: black snapback" schedule="Every day at 8:00 AM ET" next="Paused after 30 days without opens" status="paused" />
              </div>
            </div>
          </Section>

          <Section id="sidebar" title="Sidebar">
            <nav aria-label="Chats" className="h-96 w-[var(--sidebar-width)] overflow-y-auto rounded-lg border border-border bg-surface p-2">
              <div className="flex flex-col gap-px pb-1">
                <Button variant="ghost" className="justify-start" icon={<Pencil className="size-4" />}>New chat</Button>
                <Button variant="ghost" className="justify-start" icon={<Search className="size-4" />}>Search chats</Button>
              </div>
              <SidebarSection label="Projects">
                <ChatRow title="FW26 drop" />
                <ChatRow title="Hang tags & packaging" />
              </SidebarSection>
              <SidebarSection label="Today">
                <ChatRow title="Hang tag copy, round 3" active />
                <ChatRow title="Snapback caption options for Instagram stories and reels" streaming />
              </SidebarSection>
              <SidebarSection label="Previous 7 days">
                <ChatRow title="Lookbook shot list" />
                <ChatRow title="Shopify product descriptions" />
                <ChatRow title="Influencer outreach email" />
              </SidebarSection>
            </nav>
          </Section>
        </main>
      </ToastProvider>
    </TooltipProvider>
  );
}
