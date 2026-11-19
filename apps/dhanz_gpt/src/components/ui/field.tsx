"use client";

import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn, focusRing } from "@/lib/cn";

const control = cn(
  "w-full rounded-md border border-border-input bg-bg px-3 text-sm text-fg placeholder:text-subtle",
  "transition-colors duration-[var(--duration-fast)] hover:border-fg/60",
  "disabled:cursor-not-allowed disabled:opacity-50 read-only:bg-surface-muted",
  "aria-invalid:border-danger",
  focusRing,
  "focus-visible:outline-offset-0",
);

type FieldProps = { label: string; hideLabel?: boolean; hint?: ReactNode; error?: ReactNode; leading?: ReactNode };

function FieldShell({
  id, label, hideLabel, hint, error, children,
}: FieldProps & { id: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className={cn("text-sm font-medium text-fg", hideLabel && "sr-only")}>
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-msg`} className="text-xs text-danger-text">{error}</p>
      ) : hint ? (
        <p id={`${id}-msg`} className="text-xs text-muted">{hint}</p>
      ) : null}
    </div>
  );
}

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & FieldProps>(
  function TextInput({ label, hideLabel, hint, error, leading, className, id: idProp, ...props }, ref) {
    const auto = useId();
    const id = idProp ?? auto;
    return (
      <FieldShell id={id} label={label} hideLabel={hideLabel} hint={hint} error={error}>
        <div className="relative">
          {leading && (
            <span aria-hidden className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-muted [&_svg]:size-4">
              {leading}
            </span>
          )}
          <input
            ref={ref}
            id={id}
            aria-invalid={!!error || undefined}
            aria-describedby={hint || error ? `${id}-msg` : undefined}
            className={cn(control, "h-10", leading && "pl-9", className)}
            {...props}
          />
        </div>
      </FieldShell>
    );
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & FieldProps>(
  function Textarea({ label, hideLabel, hint, error, className, id: idProp, ...props }, ref) {
    const auto = useId();
    const id = idProp ?? auto;
    return (
      <FieldShell id={id} label={label} hideLabel={hideLabel} hint={hint} error={error}>
        <textarea
          ref={ref}
          id={id}
          aria-invalid={!!error || undefined}
          aria-describedby={hint || error ? `${id}-msg` : undefined}
          className={cn(control, "min-h-24 resize-y py-2 leading-5", className)}
          {...props}
        />
      </FieldShell>
    );
  },
);

/** A native select: keyboard and screen-reader behaviour come from the browser. */
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement> & FieldProps>(
  function Select({ label, hideLabel, hint, error, className, id: idProp, children, ...props }, ref) {
    const auto = useId();
    const id = idProp ?? auto;
    return (
      <FieldShell id={id} label={label} hideLabel={hideLabel} hint={hint} error={error}>
        <select
          ref={ref}
          id={id}
          aria-invalid={!!error || undefined}
          aria-describedby={hint || error ? `${id}-msg` : undefined}
          className={cn(control, "h-10 pr-8", className)}
          {...props}
        >
          {children}
        </select>
      </FieldShell>
    );
  },
);
