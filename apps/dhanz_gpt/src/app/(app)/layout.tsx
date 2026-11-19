import { Suspense } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { Providers } from "@/components/shell/providers";

// Everything under (app) is signed-in and URL-driven, so it renders at request time inside one Suspense boundary.
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" aria-busy="true" />}>
      <Providers>
        <AppShell>{children}</AppShell>
      </Providers>
    </Suspense>
  );
}
