"use client";
import Link from "next/link";
import { useState } from "react";
import { ChevronDown, LayoutDashboard, Trophy, Users, LogOut, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export function Header({ variant = "transparent" }: { variant?: "transparent" | "solid" }) {
  const [open, setOpen] = useState(false);

  return (
    <header
      className={cn(
        "sticky top-0 z-30 w-full transition-colors",
        variant === "solid"
          ? "bg-cream-100/85 backdrop-blur-md border-b border-ink-900/[0.06]"
          : "bg-transparent"
      )}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="group flex items-center gap-2.5 ring-focus rounded-full">
          <div className="grid h-7 w-7 place-items-center rounded-full bg-ink-900 text-cream-50">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <span className="display-serif text-lg font-medium tracking-tightest">Tessera</span>
        </Link>

        <nav className="hidden items-center gap-1 text-sm text-ink-600 md:flex">
          <Link href="/" className="rounded-full px-3 py-1.5 hover:bg-ink-900/[0.05]">Analysts</Link>
          <Link href="/proposals" className="rounded-full px-3 py-1.5 hover:bg-ink-900/[0.05]">Proposals</Link>
          <Link href="/how-it-works" className="rounded-full px-3 py-1.5 hover:bg-ink-900/[0.05]">How it works</Link>
        </nav>

        <div className="relative">
          <button
            onClick={() => setOpen((o) => !o)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            className="group flex items-center gap-2 rounded-full bg-cream-50 px-1 py-1 pl-3 ring-1 ring-ink-900/10 hover:ring-ink-900/20 ring-focus"
            aria-label="Account menu"
          >
            <span className="hidden text-sm font-medium text-ink-800 sm:inline">jshin</span>
            <ChevronDown className="hidden h-3.5 w-3.5 text-ink-500 sm:inline" />
            <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-coral-400 to-plum-500 text-cream-50 text-xs font-semibold">
              J
            </div>
          </button>

          {open && (
            <div className="absolute right-0 mt-2 w-64 origin-top-right overflow-hidden rounded-2xl border border-ink-900/10 bg-cream-50 shadow-[0_24px_60px_-20px_rgba(31,30,27,0.25)] animate-fade-up">
              <div className="border-b border-ink-900/[0.06] p-4">
                <div className="text-sm font-medium text-ink-900">jshin</div>
                <div className="text-xs text-ink-500">jshin0407@gmail.com</div>
              </div>
              <div className="p-1.5">
                <MenuLink href="/dashboard" icon={<LayoutDashboard className="h-4 w-4" />} label="My dashboard" sub="P&L · positions" />
                <MenuLink href="/dashboard?tab=leaderboard" icon={<Trophy className="h-4 w-4" />} label="Leaderboard" sub="Persona rankings" />
                <MenuLink href="/dashboard?tab=social" icon={<Users className="h-4 w-4" />} label="Social feed" sub="Forks · followers" />
              </div>
              <div className="border-t border-ink-900/[0.06] p-1.5">
                <button className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-ink-600 hover:bg-ink-900/[0.04]">
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

function MenuLink({ href, icon, label, sub }: { href: string; icon: React.ReactNode; label: string; sub: string }) {
  return (
    <Link
      href={href}
      className="flex items-start gap-3 rounded-xl px-3 py-2.5 hover:bg-ink-900/[0.04]"
    >
      <span className="mt-0.5 text-ink-500">{icon}</span>
      <span>
        <span className="block text-sm font-medium text-ink-900">{label}</span>
        <span className="block text-xs text-ink-500">{sub}</span>
      </span>
    </Link>
  );
}
