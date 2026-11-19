"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Banner } from "@/components/ui/feedback";
import { PageHeader } from "@/components/shell/app-shell";
import { AppsList } from "@/components/apps/apps-list";

const NAMES: Record<string, string> = { google_drive: "Google Drive", slack: "Slack", shopify: "Shopify" };

/** The result of a connect round trip (?connected=… or ?error=…). */
function Result() {
  const q = useSearchParams();
  const ok = q.get("connected");
  const err = q.get("error");
  if (ok) return <Banner tone="success" title={`${NAMES[ok] ?? "App"} is connected`}>Mention @{NAMES[ok] ?? "it"} in a chat to use it.</Banner>;
  if (err) return <Banner tone="danger" title="Not connected">{err}</Banner>;
  return null;
}

// S20 Apps: connect Google Drive, Slack and Shopify with your own accounts.
export default function AppsPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader />
      <main id="main" className="mx-auto flex w-full max-w-3xl flex-col gap-6 overflow-y-auto px-4 pb-10">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">Apps</h1>
          <p className="text-sm text-muted">
            Connect your own accounts, then mention an app with @ in a chat. The assistant only sees what your account can see, and asks before doing anything you&apos;ve said it should ask about.
          </p>
        </div>
        <Suspense fallback={null}>
          <Result />
        </Suspense>
        <AppsList />
      </main>
    </div>
  );
}
