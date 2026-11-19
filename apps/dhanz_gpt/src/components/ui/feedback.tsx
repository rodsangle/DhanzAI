"use client";

import { Avatar as A, Toast as T } from "radix-ui";
import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { cn, focusRing } from "@/lib/cn";
import { IconButton } from "./button";

/* ------------------------------------------------------------------ Badge */

const badgeTone = {
  neutral: "bg-surface-muted text-muted",
  accent: "bg-accent text-on-accent",
  success: "bg-success-subtle text-success-text",
  warning: "bg-warning-subtle text-warning-text",
  danger: "bg-danger-subtle text-danger-text",
  info: "bg-info-subtle text-info-text",
};

export function Badge({ tone = "neutral", children }: { tone?: keyof typeof badgeTone; children: ReactNode }) {
  return (
    <span className={cn("inline-flex h-5 items-center rounded-full px-2 text-xs font-medium", badgeTone[tone])}>
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ Banner */

const bannerTone = {
  info: { box: "bg-info-subtle", title: "text-info-text", Icon: Info, role: "status" },
  warning: { box: "bg-warning-subtle", title: "text-warning-text", Icon: AlertTriangle, role: "status" },
  danger: { box: "bg-danger-subtle", title: "text-danger-text", Icon: XCircle, role: "alert" },
  success: { box: "bg-success-subtle", title: "text-success-text", Icon: CheckCircle2, role: "status" },
  neutral: { box: "bg-surface-muted", title: "text-fg", Icon: Info, role: "status" },
} as const;

export function Banner({
  tone = "info", title, children, action, onDismiss,
}: {
  tone?: keyof typeof bannerTone;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  onDismiss?: () => void;
}) {
  const t = bannerTone[tone];
  return (
    <div role={t.role} className={cn("flex items-start gap-3 rounded-lg p-3", t.box)}>
      <t.Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", t.title)} />
      <div className="flex flex-1 flex-col gap-0.5 text-sm">
        <p className={cn("font-semibold", t.title)}>{title}</p>
        {children && <div className="text-fg">{children}</div>}
      </div>
      {action}
      {onDismiss && (
        <IconButton label="Dismiss" size="sm" tooltip={false} onClick={onDismiss} className="-m-1">
          <X />
        </IconButton>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Avatar */

export function Avatar({ name, src, size = 32 }: { name: string; src?: string; size?: 24 | 28 | 32 | 40 }) {
  const initials = name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <A.Root
      className="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-surface-active text-fg"
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {src && <A.Image src={src} alt={name} className="size-full object-cover" />}
      <A.Fallback delayMs={src ? 300 : 0} className="font-semibold" aria-label={name}>
        {initials}
      </A.Fallback>
    </A.Root>
  );
}

/* ------------------------------------------------------------------ Skeleton / Spinner */

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("rounded-md bg-surface-muted animate-shimmer", className)} />;
}

export function Spinner({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center", className)}>
      <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

/* ------------------------------------------------------------------ EmptyState */

export function EmptyState({
  icon, title, children, action,
}: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-[360px] flex-col items-center gap-3 py-10 text-center">
      <div aria-hidden className="text-subtle [&_svg]:size-8">{icon}</div>
      <p className="text-lg font-semibold text-fg">{title}</p>
      {children && <p className="text-sm text-muted">{children}</p>}
      {action}
    </div>
  );
}

/* ------------------------------------------------------------------ Toast */

type ToastItem = { id: number; title: string; tone?: "neutral" | "error"; action?: { label: string; onClick: () => void } };
const ToastCtx = createContext<(t: Omit<ToastItem, "id">) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((t: Omit<ToastItem, "id">) => setItems((xs) => [...xs, { ...t, id: Date.now() }]), []);
  return (
    <ToastCtx.Provider value={push}>
      <T.Provider duration={5000} swipeDirection="down">
        {children}
        {items.map((t) => (
          <T.Root
            key={t.id}
            type={t.tone === "error" ? "foreground" : "background"}
            onOpenChange={(o) => !o && setItems((xs) => xs.filter((x) => x.id !== t.id))}
            className={cn(
              "flex items-center gap-3 rounded-lg px-4 py-3 text-sm shadow-md animate-enter",
              t.tone === "error" ? "bg-danger-subtle text-danger-text" : "bg-fg text-bg",
            )}
          >
            <T.Title className="flex-1 font-medium">{t.title}</T.Title>
            {t.action && (
              <T.Action altText={t.action.label} asChild>
                <button
                  onClick={t.action.onClick}
                  className={cn("rounded-sm text-sm font-semibold underline underline-offset-4", focusRing)}
                >
                  {t.action.label}
                </button>
              </T.Action>
            )}
            <T.Close aria-label="Dismiss" className={cn("rounded-sm opacity-80 hover:opacity-100", focusRing)}>
              <X className="size-4" />
            </T.Close>
          </T.Root>
        ))}
        <T.Viewport className="fixed bottom-6 left-1/2 z-[var(--z-toast)] flex w-[min(420px,calc(100vw-2rem))] -translate-x-1/2 flex-col gap-2 outline-none" />
      </T.Provider>
    </ToastCtx.Provider>
  );
}
