"use client";

import { Checkbox as C, RadioGroup as R, Switch as S, Tabs as T } from "radix-ui";
import { Check, Minus } from "lucide-react";
import { useId, type ReactNode } from "react";
import { cn, focusRing } from "@/lib/cn";

function Row({ id, label, description, children }: { id: string; label: string; description?: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex flex-col gap-0.5">
        <label htmlFor={id} className="text-sm font-medium text-fg">{label}</label>
        {description && <p id={`${id}-d`} className="text-xs text-muted">{description}</p>}
      </div>
      {children}
    </div>
  );
}

export function Switch({
  label, description, ...props
}: { label: string; description?: string } & S.SwitchProps) {
  const id = useId();
  return (
    <Row id={id} label={label} description={description}>
      <S.Root
        id={id}
        aria-describedby={description ? `${id}-d` : undefined}
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full border border-border-input bg-surface-active transition-colors",
          "data-[state=checked]:border-accent data-[state=checked]:bg-accent disabled:opacity-50",
          focusRing,
        )}
        {...props}
      >
        <S.Thumb className="block size-4 translate-x-px rounded-full bg-surface-raised shadow-sm transition-transform duration-[var(--duration-fast)] data-[state=checked]:translate-x-[17px] data-[state=checked]:bg-on-accent" />
      </S.Root>
    </Row>
  );
}

export function Checkbox({ label, ...props }: { label: string } & C.CheckboxProps) {
  const id = useId();
  return (
    <div className="flex items-center gap-2">
      <C.Root
        id={id}
        className={cn(
          "flex size-[18px] shrink-0 items-center justify-center rounded-[5px] border border-border-input bg-bg",
          "data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=checked]:text-on-accent",
          "data-[state=indeterminate]:border-accent data-[state=indeterminate]:bg-accent data-[state=indeterminate]:text-on-accent",
          "disabled:opacity-50",
          focusRing,
        )}
        {...props}
      >
        <C.Indicator>
          {props.checked === "indeterminate" ? <Minus className="size-3.5" /> : <Check className="size-3.5" strokeWidth={3} />}
        </C.Indicator>
      </C.Root>
      <label htmlFor={id} className="text-sm text-fg">{label}</label>
    </div>
  );
}

export function RadioGroup({
  label, options, ...props
}: {
  label: string;
  options: { value: string; label: string; description?: string; disabled?: boolean }[];
} & R.RadioGroupProps) {
  const gid = useId();
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-1 text-sm font-medium text-fg">{label}</legend>
      <R.Root className="flex flex-col gap-3" {...props}>
        {options.map((o) => (
          <div key={o.value} className="flex items-start gap-2.5">
            <R.Item
              id={`${gid}-${o.value}`}
              value={o.value}
              disabled={o.disabled}
              className={cn(
                "mt-0.5 flex size-[18px] shrink-0 items-center justify-center rounded-full border border-border-input bg-bg",
                "data-[state=checked]:border-accent disabled:opacity-50",
                focusRing,
              )}
            >
              <R.Indicator className="size-2.5 rounded-full bg-accent" />
            </R.Item>
            <label htmlFor={`${gid}-${o.value}`} className="flex flex-col">
              <span className="text-sm text-fg">{o.label}</span>
              {o.description && <span className="text-xs text-muted">{o.description}</span>}
            </label>
          </div>
        ))}
      </R.Root>
    </fieldset>
  );
}

export function Tabs({
  tabs, variant = "underline", ...props
}: {
  tabs: { value: string; label: string; content: ReactNode; disabled?: boolean }[];
  variant?: "underline" | "pill";
} & T.TabsProps) {
  return (
    <T.Root {...props}>
      <T.List className={cn("flex gap-1", variant === "underline" && "border-b border-border")}>
        {tabs.map((t) => (
          <T.Trigger
            key={t.value}
            value={t.value}
            disabled={t.disabled}
            className={cn(
              "px-3 text-sm font-medium text-muted transition-colors hover:text-fg disabled:opacity-50",
              variant === "underline" &&
                "-mb-px h-9 border-b-2 border-transparent data-[state=active]:border-accent data-[state=active]:text-fg",
              variant === "pill" &&
                "h-8 rounded-full data-[state=active]:bg-surface-active data-[state=active]:text-fg",
              focusRing,
            )}
          >
            {t.label}
          </T.Trigger>
        ))}
      </T.List>
      {tabs.map((t) => (
        <T.Content key={t.value} value={t.value} className={cn("pt-4", focusRing)}>
          {t.content}
        </T.Content>
      ))}
    </T.Root>
  );
}
