"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn, focusRing } from "@/lib/cn";
import { Tooltip } from "./tooltip";

export const button = cva(
  [
    "relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap font-medium",
    "transition-[background-color,color,transform] duration-[var(--duration-fast)] ease-standard",
    "active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100",
    "aria-disabled:cursor-not-allowed aria-disabled:opacity-50",
    focusRing,
  ],
  {
    variants: {
      variant: {
        primary: "rounded-full bg-accent text-on-accent hover:bg-accent-hover",
        secondary: "rounded-full border border-border-strong bg-surface-raised text-fg hover:bg-surface-hover",
        ghost: "rounded-md text-fg hover:bg-surface-hover",
        danger: "rounded-full bg-danger text-on-danger hover:bg-danger-hover",
        link: "rounded-sm px-0! text-accent-text underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-5 text-base",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, loading, icon, children, disabled, type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(button({ variant, size }), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {/* Keep the label in the layout (invisible) while loading so the width stays put and screen readers still read it. */}
      <span className={cn("inline-flex items-center gap-2", loading && "invisible")}>
        {icon}
        {children}
      </span>
      {loading && (
        <Loader2 aria-hidden className="absolute size-4 animate-spin motion-reduce:animate-none" />
      )}
    </button>
  );
});

const iconButton = cva(
  [
    "inline-flex shrink-0 items-center justify-center transition-colors duration-[var(--duration-fast)]",
    "disabled:cursor-not-allowed disabled:opacity-50",
    focusRing,
  ],
  {
    variants: {
      variant: {
        ghost: "rounded-md text-muted hover:bg-surface-hover hover:text-fg aria-pressed:text-fg",
        secondary: "rounded-full border border-border-strong bg-surface-raised text-fg shadow-sm hover:bg-surface-hover",
        solid: "rounded-full bg-accent text-on-accent hover:bg-accent-hover",
      },
      size: { sm: "size-8 [&_svg]:size-4", md: "size-9 [&_svg]:size-[18px]", lg: "size-10 [&_svg]:size-5" },
    },
    defaultVariants: { variant: "ghost", size: "md" },
  },
);

export interface IconButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof iconButton> {
  /** Required: used for aria-label and the tooltip. */
  label: string;
  tooltip?: boolean;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, tooltip = true, className, variant, size, type = "button", children, ...props },
  ref,
) {
  const btn = (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      className={cn(iconButton({ variant, size }), className)}
      {...props}
    >
      {children}
    </button>
  );
  return tooltip ? <Tooltip label={label}>{btn}</Tooltip> : btn;
});
