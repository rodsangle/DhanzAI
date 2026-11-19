"use client";

import { ImagePlus, Images } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";
import { fileUrl } from "@/lib/api";
import type { ImageGeneration } from "@/lib/data/types";
import { cn, focusRing } from "@/lib/cn";
import { Banner, EmptyState, Skeleton } from "@/components/ui/feedback";
import { PageHeader } from "@/components/shell/app-shell";

// S13 Images (partial: gallery of generated images; templates and the region editor S14 come later)
export default function ImagesPage() {
  const { data } = useSWR<ImageGeneration[]>("/api/images");
  return (
    <main id="main" className="flex flex-1 flex-col overflow-y-auto">
      <PageHeader
        left={<h1 className="px-2 text-lg font-semibold">Images</h1>}
        right={
          <Link href="/" className={cn("inline-flex h-8 items-center gap-2 rounded-full bg-accent px-3 text-sm font-medium text-on-accent hover:bg-accent-hover", focusRing)}>
            <ImagePlus aria-hidden className="size-4" /> Create an image
          </Link>
        }
      />
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 pb-10">
        <Banner tone="info" title="Placeholder renders">Images are drawn by a stand-in generator until an image model is connected. Prompts and history are saved either way.</Banner>
        {!data && <div className="grid grid-cols-2 gap-2 md:grid-cols-4">{[1, 2, 3, 4].map((i) => <Skeleton key={i} className="aspect-square" />)}</div>}
        {data?.length === 0 && (
          <EmptyState icon={<Images />} title="No images yet">Start a chat, choose Create an image from the + menu, and describe what you want.</EmptyState>
        )}
        {data && data.length > 0 && (
          <ul className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
            {data.map((g) => (
              <li key={g.id}>
                <Link href={`/c/${g.conversation_id}`} className={cn("group block overflow-hidden rounded-lg border border-border", focusRing)}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={fileUrl(g.output_file_id!)} alt={g.prompt} className="aspect-square w-full object-cover transition-transform group-hover:scale-[1.02]" />
                  <p className="truncate px-2 py-1.5 text-xs text-muted">{g.prompt}</p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
