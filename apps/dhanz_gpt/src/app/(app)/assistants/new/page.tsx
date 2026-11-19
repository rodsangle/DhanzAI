"use client";

import { PageHeader } from "@/components/shell/app-shell";
import { AssistantForm } from "@/components/assistants/assistant-form";

// S22 Assistant builder: create.
export default function NewAssistantPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader />
      <main id="main" className="mx-auto flex w-full max-w-2xl flex-col gap-6 overflow-y-auto px-4 pb-10">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">New assistant</h1>
          <p className="text-sm text-muted">Set it up once, then reuse it whenever this job comes up. You can change it any time.</p>
        </div>
        <AssistantForm />
      </main>
    </div>
  );
}
