"use client";
import { Workflow } from "lucide-react";
import { StubPage } from "@/components/pages/stub-page";
// S16 Work agent
export default function Page() {
  return <StubPage screen="S16" title="Work" icon={<Workflow />} phase="Release 4">Hand off a multi-step job across your apps and files. You approve anything that changes something outside the assistant.</StubPage>;
}
