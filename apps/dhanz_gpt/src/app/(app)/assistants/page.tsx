"use client";

import { Bot, Pencil, Plus, Search, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import type { AssistantListItem } from "@/lib/data/types";
import { cn, focusRing } from "@/lib/cn";
import { button } from "@/components/ui/button";
import { Badge, EmptyState, Skeleton } from "@/components/ui/feedback";
import { TextInput } from "@/components/ui/field";
import { PageHeader } from "@/components/shell/app-shell";

// S21 Assistants: your own, and the ones shared with the team.
function Card({ a }: { a: AssistantListItem }) {
  return (
    <li className="relative flex flex-col gap-2 rounded-xl border border-border p-4 hover:bg-surface-hover">
      <div className="flex items-start gap-3">
        <span aria-hidden className="flex size-10 shrink-0 items-center justify-center rounded-full bg-surface-muted text-muted"><Bot className="size-5" /></span>
        <div className="flex min-w-0 flex-1 flex-col">
          {/* The whole card opens a chat; the edit link sits above it. */}
          <Link href={`/assistants/${a.id}`} className={cn("truncate font-medium after:absolute after:inset-0 after:rounded-xl", focusRing)}>
            {a.name}
          </Link>
          <span className="truncate text-xs text-muted">
            {a.owner_name ? `By ${a.owner_name}` : "Team starter"}
            {a.visibility === "workspace" ? " · Shared with the team" : " · Only you"}
          </span>
        </div>
        {a.can_edit && (
          <Link href={`/assistants/${a.id}/edit`} aria-label={`Edit ${a.name}`} className={cn("relative z-10 inline-flex size-8 items-center justify-center rounded-md text-muted hover:bg-surface-active hover:text-fg", focusRing)}>
            <Pencil className="size-4" />
          </Link>
        )}
      </div>
      {a.description && <p className="line-clamp-2 text-sm text-muted">{a.description}</p>}
    </li>
  );
}

export default function AssistantsPage() {
  const { data } = useSWR<{ mine: AssistantListItem[]; team: AssistantListItem[] }>("/api/assistants");
  const [q, setQ] = useState("");
  const match = (a: AssistantListItem) => `${a.name} ${a.description}`.toLowerCase().includes(q.trim().toLowerCase());
  const mine = data?.mine.filter(match) ?? [];
  const team = data?.team.filter(match) ?? [];
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader
        right={
          <Link href="/assistants/new" className={cn(button({ variant: "primary", size: "sm" }), focusRing)}>
            <Plus className="size-4" /> New assistant
          </Link>
        }
      />
      <main id="main" className="mx-auto flex w-full max-w-4xl flex-col gap-6 overflow-y-auto px-4 pb-10">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">Assistants</h1>
          <p className="text-sm text-muted">Presets with their own instructions and files, for jobs the team does again and again.</p>
        </div>
        <TextInput label="Search assistants" hideLabel placeholder="Search assistants" leading={<Search />} value={q} onChange={(e) => setQ(e.target.value)} />
        {!data ? (
          <div aria-busy="true" className="grid gap-3 sm:grid-cols-2">{[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24" />)}</div>
        ) : (
          <>
            <section aria-labelledby="mine" className="flex flex-col gap-3">
              <h2 id="mine" className="text-sm font-semibold">Yours</h2>
              {mine.length ? (
                <ul className="grid gap-3 sm:grid-cols-2">{mine.map((a) => <Card key={a.id} a={a} />)}</ul>
              ) : (
                <EmptyState
                  icon={<Bot />}
                  title={q ? "No matches" : "You haven't made one yet"}
                  action={!q && <Link href="/assistants/new" className={cn(button({ variant: "secondary", size: "sm" }), focusRing)}>New assistant</Link>}
                >
                  {!q && "Give it a job, instructions and reference files, then reuse it whenever that job comes up."}
                </EmptyState>
              )}
            </section>
            <section aria-labelledby="team" className="flex flex-col gap-3">
              <h2 id="team" className="flex items-center gap-2 text-sm font-semibold"><Users aria-hidden className="size-4" /> Shared with the team <Badge>{team.length}</Badge></h2>
              {team.length ? (
                <ul className="grid gap-3 sm:grid-cols-2">{team.map((a) => <Card key={a.id} a={a} />)}</ul>
              ) : (
                <p className="text-sm text-muted">{q ? "No matches." : "Nothing shared yet."}</p>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
