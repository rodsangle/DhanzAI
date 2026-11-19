"use client";

import { BRAND } from "@/lib/brand";
import { FileText } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { fetcher, fileUrl, ApiError } from "@/lib/api";
import type { SharedLink } from "@/lib/data/types";
import { cn, focusRing } from "@/lib/cn";
import { Banner, Skeleton } from "@/components/ui/feedback";
import { Markdown } from "@/components/chat/markdown";
import { SourcesRow } from "@/components/chat/sources";
import { TooltipProvider } from "@/components/ui/tooltip";

type Share = { snapshot: SharedLink["snapshot"]; owner_name: string; is_owner: boolean };

// S30 Shared conversation (read-only snapshot)
export default function SharedPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data, error } = useSWR<Share>(`/api/share/${slug}`, fetcher, { shouldRetryOnError: false });

  return (
    <TooltipProvider>
      <div className="min-h-dvh bg-bg text-fg">
        <header className="sticky top-0 z-10 flex h-[var(--header-height)] items-center justify-between border-b border-border bg-bg px-4">
          <Link href="/" className={cn("rounded-md text-sm font-semibold tracking-wide", focusRing)}>{BRAND.name} <span className="font-normal text-muted">by {BRAND.company}</span></Link>
          <Link href="/" className={cn("inline-flex h-8 items-center rounded-full bg-accent px-3 text-sm font-medium text-on-accent hover:bg-accent-hover", focusRing)}>Start your own chat</Link>
        </header>
        <main id="main" className="mx-auto flex max-w-[var(--thread-max-width)] flex-col gap-8 px-4 py-8">
          {error && (
            <Banner tone={(error as ApiError).status === 401 ? "info" : "danger"} title={(error as ApiError).status === 401 ? "Sign in to view" : "This link doesn't work"}>
              {(error as Error).message}{" "}
              {(error as ApiError).status === 401 && <Link className="underline" href={`/login?next=/s/${slug}`}>Sign in</Link>}
            </Banner>
          )}
          {!data && !error && <div className="flex flex-col gap-4" aria-busy="true"><Skeleton className="h-8 w-2/3" /><Skeleton className="h-32" /></div>}
          {data && (
            <>
              <div className="flex flex-col gap-1 border-b border-border pb-6">
                <h1 className="text-2xl font-semibold">{data.snapshot.title}</h1>
                <p className="text-sm text-muted">Shared by {data.owner_name} · {new Date(data.snapshot.shared_at).toLocaleDateString(undefined, { dateStyle: "medium" })}</p>
              </div>
              {data.snapshot.messages.map((m) =>
                m.role === "user" ? (
                  <article key={m.id} className="flex flex-col items-end gap-2">
                    <h2 className="sr-only">{data.owner_name} said:</h2>
                    {m.content.filter((b) => b.type === "file_ref").map((b) => b.type === "file_ref" && (
                      <span key={b.file_id} className="flex items-center gap-2 rounded-md bg-surface-muted px-3 py-2 text-sm"><FileText aria-hidden className="size-4 text-muted" />{b.name}</span>
                    ))}
                    <div className="max-w-[85%] whitespace-pre-wrap rounded-xl bg-surface-muted px-4 py-2.5 sm:max-w-[70%]">{m.text}</div>
                  </article>
                ) : (
                  <article key={m.id} className="flex flex-col gap-3">
                    <h2 className="sr-only">Assistant said:</h2>
                    <Markdown text={m.text} />
                    {m.content.filter((b) => b.type === "image").map((b) => b.type === "image" && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img key={b.file_id} src={fileUrl(b.file_id)} alt={b.alt} className="max-w-[420px] rounded-lg border border-border" />
                    ))}
                    {m.content.map((b, i) => (b.type === "sources" ? <SourcesRow key={i} items={b.items.filter((x) => x.kind === "web")} /> : null))}
                  </article>
                ),
              )}
              <p className="border-t border-border pt-6 text-center text-xs text-muted">This is a read-only copy. It doesn&apos;t update when the original chat changes.</p>
            </>
          )}
        </main>
      </div>
    </TooltipProvider>
  );
}
