"use client";
import { useState } from "react";
import { ChevronDown, FileText } from "lucide-react";
import type { Report } from "@/lib/mock/reports";
import type { Persona } from "@/lib/mock/personas";
import { ACCENT_CLASS } from "@/lib/mock/personas";
import { Badge } from "./ui/badge";
import { cn } from "@/lib/utils";

const TYPE_TONE: Record<Report["type"], "default" | "coral" | "sage" | "plum"> = {
  thesis: "coral",
  update: "default",
  macro: "plum",
  exit: "sage",
};

const TYPE_LABEL: Record<Report["type"], string> = {
  thesis: "Thesis",
  update: "Update",
  macro: "Macro",
  exit: "Exit",
};

export function ReportList({ reports, persona }: { reports: Report[]; persona: Persona }) {
  const [openId, setOpenId] = useState<string | null>(reports[0]?.id ?? null);
  const a = ACCENT_CLASS[persona.accent];

  if (!reports?.length) return null;

  return (
    <div className="space-y-3">
      {reports.map((r) => {
        const open = openId === r.id;
        return (
          <article
            key={r.id}
            className={cn(
              "overflow-hidden rounded-2xl border bg-cream-50 transition-colors",
              open ? "border-ink-900/[0.12]" : "border-ink-900/[0.06]"
            )}
          >
            <button
              onClick={() => setOpenId(open ? null : r.id)}
              className="flex w-full items-start gap-4 px-5 py-4 text-left ring-focus hover:bg-ink-900/[0.02]"
            >
              <div className={cn("mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full", a.bg, a.text)}>
                <FileText className="h-3.5 w-3.5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={TYPE_TONE[r.type]}>{TYPE_LABEL[r.type]}</Badge>
                  {r.tickers.map((t) => (
                    <span key={t} className="num text-[11px] font-medium text-ink-700">
                      {t}
                    </span>
                  ))}
                  <span className="num ml-auto text-[11px] text-ink-500">{r.date}</span>
                </div>
                <h4 className="display-serif mt-1.5 text-lg leading-snug text-ink-900">{r.title}</h4>
                <p className="mt-1 text-[13px] leading-relaxed text-ink-600">{r.summary}</p>
              </div>
              <ChevronDown
                className={cn(
                  "mt-1.5 h-4 w-4 shrink-0 text-ink-400 transition-transform",
                  open && "rotate-180"
                )}
              />
            </button>

            {open && (
              <div className="border-t border-ink-900/[0.06] px-5 pb-5 pt-4">
                <div className="prose prose-sm max-w-none">
                  {r.body.map((p, i) => (
                    <p key={i} className="text-[14px] leading-relaxed text-ink-700">
                      {p}
                    </p>
                  ))}
                </div>

                {r.numerics && r.numerics.length > 0 && (
                  <div className="mt-5">
                    <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-ink-500">
                      Key numerics
                    </div>
                    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-ink-900/[0.06] bg-ink-900/[0.06] sm:grid-cols-3">
                      {r.numerics.map((n) => (
                        <div key={n.label} className="bg-cream-50 px-3 py-2">
                          <div className="text-[10px] uppercase tracking-[0.14em] text-ink-500">
                            {n.label}
                          </div>
                          <div className="num mt-0.5 text-sm font-medium text-ink-900">{n.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {r.whatWouldMakeMeWrong && r.whatWouldMakeMeWrong.length > 0 && (
                  <div className="mt-5 rounded-xl border border-ink-900/[0.06] bg-cream-100/60 p-4">
                    <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-coral-600">
                      What would make me wrong
                    </div>
                    <ul className="space-y-1.5 text-[13px] leading-relaxed text-ink-700">
                      {r.whatWouldMakeMeWrong.map((w, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="mt-2 inline-block h-1 w-1 shrink-0 rounded-full bg-coral-500" />
                          {w}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
