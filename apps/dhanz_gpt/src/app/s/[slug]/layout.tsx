import { Suspense } from "react";

export default function ShareLayout({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<div className="min-h-dvh bg-bg" aria-busy="true" />}>{children}</Suspense>;
}
