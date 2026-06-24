"use client";
// App shell for the authenticated/product surface (Dashboard, Analysts,
// Leaderboard, Settings) — a persistent left sidebar that visually separates
// the app from the marketing site (which keeps the public Header). Social Feed
// is intentionally excluded (deactivated 2026-06-19). Mobile: the sidebar
// collapses to a top bar with a slide-in drawer.

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, FileText, Trophy, HelpCircle, LogOut, Menu, X, LogIn } from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { cn } from "@/lib/utils";

// Mirrors the marketing top-nav (Desk / Proposals / How it works) plus the app
// views (Dashboard / Leaderboard) in one place. No "Settings" item — it's just
// a section of the dashboard; reach it from there.
type NavItem = { href: string; label: string; icon: typeof LayoutDashboard };
const NAV: NavItem[] = [
  { href: "/", label: "Desk", icon: Users },
  { href: "/proposals", label: "Proposals", icon: FileText },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/dashboard?tab=leaderboard", label: "Leaderboard", icon: Trophy },
  { href: "/how-it-works", label: "How it works", icon: HelpCircle },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { configured, user, signInWithGoogle, signOut } = useAuth();
  const [drawer, setDrawer] = useState(false);

  const signedIn = configured && !!user;
  const displayName = user?.displayName || user?.email || (configured ? "Account" : "jshin");
  const initial = (displayName.trim()[0] ?? "J").toUpperCase();
  const photoUrl = user?.photoURL ?? null;

  // Active by base path (avoids useSearchParams + its Suspense requirement).
  const isActive = (href: string) => {
    const base = href.split(/[?#]/)[0];
    return pathname === base;
  };

  const nav = (
    <nav className="flex flex-col gap-0.5" aria-label="Product">
      {NAV.map(({ href, label, icon: Icon }) => (
        <Link key={label} href={href} onClick={() => setDrawer(false)}
          className={cn(
            "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm ring-focus transition-colors",
            isActive(href) ? "bg-ink-900 text-cream-50" : "text-ink-600 hover:bg-ink-900/[0.05] hover:text-ink-900",
          )}>
          <Icon className="h-[18px] w-[18px]" /> {label}
        </Link>
      ))}
    </nav>
  );

  const userFooter = signedIn ? (
    <div className="flex items-center gap-2.5 border-t border-ink-900/[0.08] px-2 pt-3">
      {photoUrl
        // eslint-disable-next-line @next/next/no-img-element
        ? <img src={photoUrl} alt="" className="h-8 w-8 rounded-full object-cover" referrerPolicy="no-referrer" />
        : <div className="grid h-8 w-8 place-items-center rounded-full bg-ink-900 text-xs font-medium text-cream-50">{initial}</div>}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-ink-900">{displayName}</div>
      </div>
      <button type="button" onClick={() => void signOut()} title="Sign out"
        className="grid h-8 w-8 place-items-center rounded-lg text-ink-500 hover:bg-ink-900/[0.05] hover:text-ink-900 ring-focus">
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  ) : (
    <button type="button" onClick={() => void signInWithGoogle()}
      className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink-900 px-3 py-2.5 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus">
      <LogIn className="h-4 w-4" /> Sign in
    </button>
  );

  const brand = (
    <Link href="/" className="flex items-center gap-2 rounded-md px-1 ring-focus">
      <span className="display-serif text-lg text-ink-900">Convt</span>
      <span className="rounded-full bg-coral-500/10 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-[0.14em] text-coral-600">Desk</span>
    </Link>
  );

  return (
    <div className="min-h-screen md:pl-60">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-ink-900/[0.08] bg-cream-50/60 px-3 py-5 backdrop-blur md:flex">
        <div className="px-2">{brand}</div>
        <div className="mt-7 flex-1">{nav}</div>
        <div className="mt-4">{userFooter}</div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-ink-900/[0.08] bg-cream-50/80 px-4 py-3 backdrop-blur md:hidden">
        {brand}
        <button type="button" onClick={() => setDrawer(true)} aria-label="Open menu"
          className="grid h-9 w-9 place-items-center rounded-lg text-ink-700 hover:bg-ink-900/[0.05] ring-focus">
          <Menu className="h-5 w-5" />
        </button>
      </header>

      {/* Mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button type="button" aria-label="Close menu" onClick={() => setDrawer(false)} className="absolute inset-0 bg-ink-900/30" />
          <div className="absolute inset-y-0 left-0 flex w-64 flex-col border-r border-ink-900/[0.08] bg-cream-50 px-3 py-5">
            <div className="flex items-center justify-between px-2">
              {brand}
              <button type="button" onClick={() => setDrawer(false)} aria-label="Close menu"
                className="grid h-8 w-8 place-items-center rounded-lg text-ink-500 hover:bg-ink-900/[0.05] ring-focus">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-6 flex-1">{nav}</div>
            <div className="mt-4">{userFooter}</div>
          </div>
        </div>
      )}

      <main className="min-h-screen">{children}</main>
    </div>
  );
}
