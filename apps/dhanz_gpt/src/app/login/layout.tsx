import { Suspense } from "react";

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<div className="min-h-dvh bg-surface" aria-busy="true" />}>{children}</Suspense>;
}
