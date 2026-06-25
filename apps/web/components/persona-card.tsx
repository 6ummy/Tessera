"use client";
import { ArrowUpRight } from "lucide-react";
import type { Persona } from "@/lib/mock/personas";
import { ACCENT_CLASS } from "@/lib/mock/personas";
import type { PersonaPerformance } from "@/lib/performance-types";
import { rebase, toPoints } from "@/lib/performance-data";
import { Sparkline } from "./sparkline";
import { Badge } from "./ui/badge";
import { PersonaAvatar } from "./persona-avatar";
import { fmt, signClass, cn } from "@/lib/utils";

const ACCENT_HEX: Record<Persona["accent"], string> = {
  coral: "#D97757",
  sage: "#6B8E6B",
  plum: "#8B6B8E",
  ink: "#1F1E1B", oxblood: "#9A3B2E",
};

export function PersonaCard({
  persona,
  onOpen,
  performance,
}: {
  persona: Persona;
  onOpen: (id: string) => void;
  // Real paper-track data (null while loading / on fetch failure).
  performance?: PersonaPerformance | null;
}) {
  const a = ACCENT_CLASS[persona.accent];
  const m = performance?.metrics ?? null;
  const spark = performance ? rebase(toPoints(performance).slice(-90)) : [];

  return (
    <button
      onClick={() => onOpen(persona.id)}
      className="group relative flex h-full flex-col overflow-hidden rounded-3xl border border-ink-900/[0.06] bg-cream-50 p-4 text-left transition-all hover:-translate-y-0.5 hover:border-ink-900/[0.12] hover:shadow-[0_24px_60px_-20px_rgba(31,30,27,0.18)] ring-focus sm:p-5"
    >
      {/* corner accent — inline accent colour (some accents like plum are
          too muted as a Tailwind bg to read at blur+opacity), brighter on hover */}
      <div
        className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full opacity-0 blur-3xl transition-opacity group-hover:opacity-60"
        style={{ background: ACCENT_HEX[persona.accent] }}
      />

      <div className="flex items-start justify-between gap-3">
        <PersonaAvatar persona={persona} size="md" ring />
        <Badge tone={persona.accent === "ink" ? "default" : persona.accent}>{persona.riskLabel}</Badge>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <div className={cn("h-1.5 w-1.5 rounded-full", a.dot)} />
        <span className="text-xs font-medium uppercase tracking-[0.14em] text-ink-500">
          {persona.archetype}
        </span>
      </div>
      <h3 className="display-serif mt-1 text-2xl text-ink-900">{persona.name}</h3>

      <p className="mt-2 text-sm leading-relaxed text-ink-700">{persona.tagline}</p>

      <div className="mt-5 grid grid-cols-3 gap-2">
        <Metric
          label="1y"
          value={m?.return1y != null ? fmt.pct(m.return1y) : "—"}
          sign={m?.return1y ?? undefined}
        />
        <Metric
          label="Sharpe 30d"
          value={m?.sharpe30d != null ? fmt.num(m.sharpe30d) : "—"}
        />
        <Metric
          label="MDD 30d"
          value={m?.mdd30d != null ? fmt.pct(-m.mdd30d) : "—"}
          sign={m?.mdd30d != null ? -m.mdd30d : undefined}
        />
      </div>

      <div className="mt-4 hidden h-12 sm:block">
        {spark.length > 1 ? (
          <Sparkline data={spark} color={ACCENT_HEX[persona.accent]} height={48} />
        ) : (
          <div className="h-full w-full animate-pulse rounded-lg bg-ink-900/[0.04]" />
        )}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-ink-900/[0.06] pt-4 text-xs">
        <span className="text-ink-500">
          Horizon · <span className="text-ink-700">{persona.horizon}</span>
        </span>
        <span className={cn("inline-flex items-center gap-1 font-medium text-ink-700 transition-transform group-hover:translate-x-0.5", a.text)}>
          View thesis
          <ArrowUpRight className="h-3.5 w-3.5" />
        </span>
      </div>
    </button>
  );
}

function Metric({ label, value, sign }: { label: string; value: string; sign?: number }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.16em] text-ink-500">{label}</div>
      <div className={cn("num mt-1 text-sm font-medium", sign !== undefined ? signClass(sign) : "text-ink-900")}>
        {value}
      </div>
    </div>
  );
}
