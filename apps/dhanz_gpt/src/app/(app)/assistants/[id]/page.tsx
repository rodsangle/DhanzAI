"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import type { AssistantDetail } from "@/lib/data/types";
import { Banner, Skeleton } from "@/components/ui/feedback";
import { PageHeader } from "@/components/shell/app-shell";
import { ChatView } from "@/components/chat/chat-view";

// A new chat with an assistant: its name, description and conversation starters, then the usual chat.
export default function AssistantChatPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = useSWR<AssistantDetail>(`/api/assistants/${id}`);
  if (error)
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <PageHeader />
        <main id="main" className="m-auto max-w-md px-4">
          <Banner tone="danger" title="Assistant not found">{error.message} <Link className="underline" href="/assistants">All assistants</Link></Banner>
        </main>
      </div>
    );
  if (!data)
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <PageHeader />
        <div role="status" aria-label="Loading assistant" className="m-auto flex w-full max-w-md flex-col items-center gap-3 px-4"><Skeleton className="size-12 rounded-full" /><Skeleton className="h-8 w-1/2" /></div>
      </div>
    );
  return <ChatView key={id} assistant={data} assistantEditable={data.can_edit} />;
}
