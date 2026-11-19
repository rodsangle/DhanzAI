"use client";

import type { ReactNode } from "react";
import { PageHeader } from "@/components/shell/app-shell";
import { Badge, EmptyState } from "@/components/ui/feedback";

/** Placeholder for screens scheduled in a later phase. Routing exists so navigation and the recon IDs are complete. */
export function StubPage({ screen, title, icon, phase, children }: { screen: string; title: string; icon: ReactNode; phase: string; children: ReactNode }) {
  return (
    <main id="main" className="flex flex-1 flex-col overflow-y-auto">
      <PageHeader left={<h1 className="px-2 text-lg font-semibold">{title}</h1>} right={<Badge>{phase}</Badge>} />
      <div className="flex flex-1 items-center justify-center px-4" data-screen={screen}>
        <EmptyState icon={icon} title={`${title} is on the way`}>
          {children}
        </EmptyState>
      </div>
    </main>
  );
}
