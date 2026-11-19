"use client";

import { FileStack, PanelLeft } from "lucide-react";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import useSWR from "swr";
import { IconButton } from "@/components/ui/button";
import { Drawer } from "@/components/ui/overlays";
import type { PageDetail } from "@/lib/data/space-types";
import { PageTree } from "./page-tree";

/** S12 frame: the page tree on the left (a drawer on narrow screens), the page on the right. */
export function SpaceShell({ children }: { children: ReactNode }) {
  const params = useParams<{ id?: string }>();
  const id = params?.id;
  const { data } = useSWR<PageDetail>(id ? `/api/pages/${id}` : null, { revalidateOnFocus: false });
  const ancestors = data?.breadcrumbs.map((b) => b.id) ?? [];
  const [drawer, setDrawer] = useState(false);
  return (
    <div id="main" className="flex min-h-0 flex-1">
      <div className="hidden w-64 shrink-0 overflow-y-auto border-r border-border bg-surface md:block">
        <div className="flex h-[var(--header-height)] items-center gap-2 px-3">
          <FileStack aria-hidden className="size-4 text-muted" />
          <h1 className="text-sm font-semibold">Space</h1>
        </div>
        <PageTree activeId={id} ancestors={ancestors} />
      </div>
      <div className="relative flex min-w-0 flex-1 flex-col">
        <div className="absolute left-2 top-2 z-[2] md:hidden">
          <Drawer
            open={drawer}
            onOpenChange={setDrawer}
            side="left"
            title="Pages"
            trigger={<IconButton label="Show pages"><PanelLeft /></IconButton>}
          >
            <div onClick={(e) => { if ((e.target as HTMLElement).closest("a")) setDrawer(false); }}>
              <PageTree activeId={id} ancestors={ancestors} />
            </div>
          </Drawer>
        </div>
        {children}
      </div>
    </div>
  );
}
