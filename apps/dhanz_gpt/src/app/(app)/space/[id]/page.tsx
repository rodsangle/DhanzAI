"use client";

import { use } from "react";
import { PageEditor } from "@/components/space/page-editor";

// S12 a page.
export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <PageEditor key={id} id={id} />;
}
