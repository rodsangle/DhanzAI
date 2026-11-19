"use client";
import { Telescope } from "lucide-react";
import { StubPage } from "@/components/pages/stub-page";
// S15 Deep research
export default function Page() {
  return <StubPage screen="S15" title="Deep research" icon={<Telescope />} phase="Release 3">Ask a big question, review the research plan, and get a report with sources you can check.</StubPage>;
}
