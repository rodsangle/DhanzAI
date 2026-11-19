"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import type { AssistantDetail } from "@/lib/data/types";
import { Banner, Skeleton } from "@/components/ui/feedback";
import { PageHeader } from "@/components/shell/app-shell";
import { AssistantForm } from "@/components/assistants/assistant-form";

// S22 Assistant builder: edit, with version history.
export default function EditAssistantPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useSWR<AssistantDetail>(`/api/assistants/${id}`);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader />
      <main id="main" className="mx-auto flex w-full max-w-2xl flex-col gap-6 overflow-y-auto px-4 pb-10">
        {error ? (
          <Banner tone="danger" title="Assistant not found">{error.message} <Link className="underline" href="/assistants">All assistants</Link></Banner>
        ) : !data ? (
          <div role="status" aria-label="Loading assistant" className="flex flex-col gap-3"><Skeleton className="h-8 w-1/2" /><Skeleton className="h-64" /></div>
        ) : !data.can_edit ? (
          <Banner tone="info" title="You can't edit this assistant">Only its author or a workspace admin can. <Link className="underline" href={`/assistants/${id}`}>Chat with it</Link></Banner>
        ) : (
          <>
            <h1 className="text-2xl font-semibold">Edit {data.name}</h1>
            {/* Keyed on the version so a restore reloads the form with the restored settings. */}
            <AssistantForm key={data.current_version} existing={data} />
          </>
        )}
      </main>
    </div>
  );
}
