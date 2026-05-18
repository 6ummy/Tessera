import * as React from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "outline";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary:
    "bg-ink-900 text-cream-50 hover:bg-ink-800 active:bg-ink-900 shadow-[0_1px_0_rgba(255,255,255,0.08)_inset,0_6px_18px_-8px_rgba(31,30,27,0.4)]",
  secondary:
    "bg-coral-500 text-cream-50 hover:bg-coral-600 active:bg-coral-700",
  ghost: "text-ink-800 hover:bg-ink-900/[0.05]",
  outline:
    "border border-ink-900/15 text-ink-800 hover:bg-ink-900/[0.04] bg-transparent",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-base",
};

export const Button = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }
>(({ className, variant = "primary", size = "md", ...props }, ref) => (
  <button
    ref={ref}
    className={cn(
      "inline-flex items-center justify-center gap-2 rounded-full font-medium transition-colors ring-focus disabled:opacity-50 disabled:pointer-events-none",
      variants[variant],
      sizes[size],
      className
    )}
    {...props}
  />
));
Button.displayName = "Button";
