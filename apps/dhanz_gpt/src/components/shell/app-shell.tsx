"use client";

import { BRAND } from "@/lib/brand";
import { Dialog as D } from "radix-ui";
import { Menu as MenuIcon, SquarePen } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { IconButton } from "@/components/ui/button";
import { SidebarContent } from "./sidebar";
import { SearchModal } from "./search-modal";
import { SettingsDialog } from "./settings-dialog";
import { useUI } from "./providers";

function useIsDesktop() {
  const [desktop, setDesktop] = useState(true);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const on = () => setDesktop(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return desktop;
}

export function AppShell({ children }: { children: ReactNode }) {
  const { sidebarOpen } = useUI();
  const desktop = useIsDesktop();
  const [drawer, setDrawer] = useState(false);

  return (
    <div className="flex h-dvh overflow-hidden bg-bg text-fg">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:rounded-md focus:bg-surface-raised focus:px-3 focus:py-2 focus:shadow-md">
        Skip to content
      </a>
      {desktop && (
        <aside
          aria-label="Sidebar"
          className={cn(
            "shrink-0 border-r border-border transition-[width] duration-[var(--duration-base)] ease-standard",
            sidebarOpen ? "w-[var(--sidebar-width)]" : "w-[var(--sidebar-rail-width)]",
          )}
        >
          <SidebarContent collapsed={!sidebarOpen} />
        </aside>
      )}
      {!desktop && (
        <D.Root open={drawer} onOpenChange={setDrawer}>
          <D.Portal>
            <D.Overlay className="fixed inset-0 z-[var(--z-drawer)] bg-overlay" />
            <D.Content aria-describedby={undefined} className="fixed inset-y-0 left-0 z-[var(--z-drawer)] w-[min(var(--sidebar-width),85vw)] shadow-lg outline-hidden">
              <D.Title className="sr-only">Menu</D.Title>
              <SidebarContent onNavigate={() => setDrawer(false)} />
            </D.Content>
          </D.Portal>
        </D.Root>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileBar onMenu={() => setDrawer(true)} visible={!desktop} />
        {children}
      </div>
      <SearchModal />
      <SettingsDialog />
    </div>
  );
}

function MobileBar({ onMenu, visible }: { onMenu: () => void; visible: boolean }) {
  if (!visible) return null;
  return (
    <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-2">
      <IconButton label="Open menu" onClick={onMenu}><MenuIcon /></IconButton>
      <span className="text-sm font-semibold tracking-wide">{BRAND.name}</span>
      <Link href="/" aria-label="New chat" className="inline-flex size-9 items-center justify-center rounded-md text-muted hover:bg-surface-hover hover:text-fg">
        <SquarePen className="size-[18px]" />
      </Link>
    </div>
  );
}

/** Page header: left slot (title or model picker) and right slot (actions). */
export function PageHeader({ left, right, className }: { left?: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <header className={cn("flex h-[var(--header-height)] shrink-0 items-center justify-between gap-2 px-3", className)}>
      <div className="flex min-w-0 items-center gap-1">{left}</div>
      <div className="flex shrink-0 items-center gap-1">{right}</div>
    </header>
  );
}
