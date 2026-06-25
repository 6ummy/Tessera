import { cn } from "@/lib/utils";

export function Badge({
  className,
  children,
  tone = "default",
}: {
  className?: string;
  children: React.ReactNode;
  tone?: "default" | "coral" | "sage" | "plum" | "ink" | "oxblood";
}) {
  const tones = {
    default: "bg-ink-900/[0.05] text-ink-700",
    coral: "bg-coral-50 text-coral-700",
    sage: "bg-sage-400/15 text-sage-600",
    plum: "bg-plum-500/10 text-plum-600",
    ink: "bg-ink-900 text-cream-50",
    oxblood: "bg-oxblood-500/10 text-oxblood-600",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium tracking-wide",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
