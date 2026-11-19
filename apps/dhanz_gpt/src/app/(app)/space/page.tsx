"use client";

import { FilePlus2, FileStack } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";
import { cn, focusRing } from "@/lib/cn";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { SPACES_KEY, untitled, useNewPage, type SpacesData } from "@/components/space/page-tree";

// S12 Space home: start a page, or pick up where you left off.
export default function Page() {
  const { data } = useSWR<SpacesData>(SPACES_KEY);
  const newPage = useNewPage();
  const personal = data?.spaces.find((s) => s.is_personal);
  const shared = data?.pages.filter((p) => p.space_id !== personal?.id).slice(0, 12) ?? [];
  const mine = data?.pages.filter((p) => p.space_id === personal?.id && !p.parent_page_id).slice(0, 12) ?? [];
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-6 pb-16 pt-14 sm:px-10">
        <h2 className="text-2xl font-semibold">Pages</h2>
        <p className="mt-1 text-sm text-muted">Briefs, lookbook notes and campaign docs, written with the team and the assistant.</p>
        <div className="mt-5">
          <Button icon={<FilePlus2 className="size-4" />} onClick={() => newPage({ space_id: personal?.id })} disabled={!personal}>New page</Button>
        </div>
        {!data ? (
          <div className="mt-8 flex flex-col gap-2" aria-busy="true">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}</div>
        ) : !data.pages.length ? (
          <div className="mt-10">
            <EmptyState icon={<FileStack />} title="No pages yet">
              Start a page here, or open a chat and choose Save as a page to turn an answer into a doc.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-10 grid gap-8 sm:grid-cols-2">
            {[{ label: "Your pages", list: mine }, { label: "Team pages", list: shared }].map(({ label, list }) => (
              <section key={label} aria-label={label}>
                <h3 className="text-xs font-semibold text-muted">{label}</h3>
                {list.length ? (
                  <ul className="mt-2 flex flex-col gap-1">
                    {list.map((p) => (
                      <li key={p.id}>
                        <Link href={`/space/${p.id}`} className={cn("block truncate rounded-md px-2 py-1.5 text-sm hover:bg-surface-hover", focusRing)}>
                          {untitled(p.title)}
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 px-2 text-sm text-muted">None yet.</p>
                )}
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
