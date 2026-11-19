"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import useSWR, { SWRConfig } from "swr";
import { api, fetcher, type Me } from "@/lib/api";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/feedback";
import { DEFAULT_MODEL, type FileRow } from "@/lib/data/types";

type Theme = "system" | "light" | "dark";

export function applyTheme(theme: Theme) {
  const el = document.documentElement;
  el.classList.toggle("dark", theme === "dark");
  el.classList.toggle("light", theme === "light");
  try {
    localStorage.setItem("theme", theme);
  } catch {}
}

type UI = {
  sidebarOpen: boolean; // desktop: expanded vs rail. mobile: drawer open
  setSidebarOpen: (v: boolean) => void;
  searchOpen: boolean;
  setSearchOpen: (v: boolean) => void;
  settings: string | null; // open settings section, or null
  openSettings: (section: string | null) => void;
  newChatModel: string;
  setNewChatModel: (m: string) => void;
  me: Me | undefined;
  /** Library files handed to the next composer that mounts ("Use in a chat"). */
  pendingFiles: FileRow[];
  setPendingFiles: (f: FileRow[]) => void;
};

const UICtx = createContext<UI | null>(null);
export const useUI = () => {
  const v = useContext(UICtx);
  if (!v) throw new Error("useUI outside Providers");
  return v;
};

function UIProvider({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const [settings, setSettings] = useState<string | null>(null);
  const [newChatModel, setNewChatModel] = useState<string>(DEFAULT_MODEL);
  const [pendingFiles, setPendingFiles] = useState<FileRow[]>([]);
  const { data: me } = useSWR<Me>("/api/me", fetcher, { refreshInterval: 60_000 });

  useEffect(() => {
    if (me?.profile.theme) applyTheme(me.profile.theme);
  }, [me?.profile.theme]);

  // Global shortcuts: ⌘K search, ⌘⇧O new chat, ⌘⇧S toggle sidebar.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      } else if (mod && e.shiftKey && e.key.toLowerCase() === "o") {
        e.preventDefault();
        window.location.assign("/");
      } else if (mod && e.shiftKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        setSidebarOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openSettings = useCallback((section: string | null) => setSettings(section), []);
  const value = useMemo(
    () => ({ sidebarOpen, setSidebarOpen, searchOpen, setSearchOpen, settings, openSettings, newChatModel, setNewChatModel, me, pendingFiles, setPendingFiles }),
    [sidebarOpen, searchOpen, settings, openSettings, newChatModel, me, pendingFiles],
  );
  return <UICtx.Provider value={value}>{children}</UICtx.Provider>;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ fetcher, revalidateOnFocus: true, shouldRetryOnError: false }}>
      <TooltipProvider>
        <ToastProvider>
          <UIProvider>{children}</UIProvider>
        </ToastProvider>
      </TooltipProvider>
    </SWRConfig>
  );
}

export { api };
