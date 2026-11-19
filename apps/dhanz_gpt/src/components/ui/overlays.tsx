"use client";

import { Dialog as D, DropdownMenu as M } from "radix-ui";
import { Check, X } from "lucide-react";
import type { ReactNode } from "react";
import { cn, focusRing } from "@/lib/cn";
import { IconButton } from "./button";

/* ------------------------------------------------------------------ Menu */

export const Menu = M.Root;
export const MenuTrigger = M.Trigger;

export function MenuContent({ children, align = "start", className }: { children: ReactNode; align?: "start" | "end" | "center"; className?: string }) {
  return (
    <M.Portal>
      <M.Content
        align={align}
        sideOffset={6}
        className={cn(
          "z-[var(--z-dropdown)] min-w-56 rounded-lg bg-surface-raised p-1.5 text-fg shadow-md animate-enter",
          className,
        )}
      >
        {children}
      </M.Content>
    </M.Portal>
  );
}

const itemBase =
  "flex min-h-9 cursor-default select-none items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-surface-hover data-[disabled]:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0";

export function MenuItem({
  icon, children, description, shortcut, destructive, ...props
}: { icon?: ReactNode; description?: string; shortcut?: string; destructive?: boolean } & M.DropdownMenuItemProps) {
  return (
    <M.Item className={cn(itemBase, destructive && "text-danger-text")} {...props}>
      {icon}
      <span className="flex flex-1 flex-col">
        <span>{children}</span>
        {description && <span className="text-xs text-muted">{description}</span>}
      </span>
      {shortcut && <kbd className="font-sans text-xs text-muted">{shortcut}</kbd>}
    </M.Item>
  );
}

export function MenuCheckItem({
  children, description, ...props
}: { description?: string } & M.DropdownMenuCheckboxItemProps) {
  return (
    <M.CheckboxItem className={itemBase} {...props}>
      <span className="flex flex-1 flex-col">
        <span>{children}</span>
        {description && <span className="text-xs text-muted">{description}</span>}
      </span>
      <M.ItemIndicator>
        <Check />
      </M.ItemIndicator>
    </M.CheckboxItem>
  );
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return <M.Label className="px-2.5 pb-1 pt-2 text-xs font-semibold text-muted">{children}</M.Label>;
}

export function MenuSeparator() {
  return <M.Separator className="my-1.5 h-px bg-border" />;
}

/* ------------------------------------------------------------------ Dialog & Drawer */

const dialogWidth = { sm: "max-w-[var(--modal-sm)]", md: "max-w-[var(--modal-md)]", lg: "max-w-[var(--modal-lg)]" };

export function Dialog({
  open, onOpenChange, trigger, title, description, size = "md", children, footer,
}: {
  open?: boolean;
  onOpenChange?: (o: boolean) => void;
  trigger?: ReactNode;
  title: string;
  description?: string;
  size?: keyof typeof dialogWidth;
  children?: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <D.Trigger asChild>{trigger}</D.Trigger>}
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[var(--z-modal)] bg-overlay animate-enter" />
        <D.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-[var(--z-modal)] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2",
            "max-h-[85vh] overflow-y-auto rounded-xl bg-surface-raised p-6 text-fg shadow-lg",
            dialogWidth[size],
            focusRing,
          )}
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1">
              <D.Title className="text-xl font-semibold">{title}</D.Title>
              {description ? (
                <D.Description className="text-sm text-muted">{description}</D.Description>
              ) : (
                <D.Description className="sr-only">{title}</D.Description>
              )}
            </div>
            <D.Close asChild>
              <IconButton label="Close" size="sm" tooltip={false}>
                <X />
              </IconButton>
            </D.Close>
          </div>
          {children}
          {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

export const DialogClose = D.Close;

export function Drawer({
  open, onOpenChange, trigger, title, side = "right", children,
}: {
  open?: boolean;
  onOpenChange?: (o: boolean) => void;
  trigger?: ReactNode;
  title: string;
  side?: "left" | "right";
  children: ReactNode;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <D.Trigger asChild>{trigger}</D.Trigger>}
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[var(--z-drawer)] bg-overlay" />
        <D.Content
          className={cn(
            "fixed inset-y-0 z-[var(--z-drawer)] flex flex-col bg-surface text-fg shadow-lg",
            side === "left" ? "left-0 w-[var(--sidebar-width)]" : "right-0 w-[min(400px,100vw)]",
            focusRing,
          )}
        >
          <div className="flex h-[var(--header-height)] items-center justify-between px-4">
            <D.Title className="text-base font-semibold">{title}</D.Title>
            <D.Description className="sr-only">{title}</D.Description>
            <D.Close asChild>
              <IconButton label="Close" size="sm" tooltip={false}>
                <X />
              </IconButton>
            </D.Close>
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-4">{children}</div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
