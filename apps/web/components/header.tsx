"use client";
import Link from "next/link";
import { useEffect, useId, useState } from "react";
import {
  ChevronDown,
  LayoutDashboard,
  LogIn,
  LogOut,
  Menu,
  Settings,
  Trophy,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { NotificationsToggle } from "./notifications-toggle";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/", label: "Desk" },
  { href: "/proposals", label: "Proposals" },
  { href: "/how-it-works", label: "How it works" },
] as const;

function ConvtMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 36 36" className={className} xmlns="http://www.w3.org/2000/svg" aria-label="Convt">
      <rect x="1" y="1" width="10" height="10" fill="#D97757" />
      <rect x="13" y="1" width="10" height="10" fill="#EDEBE0" />
      <rect x="13" y="13" width="10" height="10" fill="#1F1E1B" />
      <rect x="25" y="13" width="10" height="10" fill="#EDEBE0" />
      <rect x="13" y="25" width="10" height="10" fill="#EDEBE0" />
      <rect x="25" y="25" width="10" height="10" fill="#6B8E6B" />
    </svg>
  );
}

export function Header({ variant = "transparent" }: { variant?: "transparent" | "solid" }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const mobileNavId = useId();
  const accountMenuId = useId();

  const { configured, user, signInWithGoogle, signOut } = useAuth();
  // When Firebase isn't wired yet, keep the pre-auth pilot identity so the
  // app stays usable. Once configured + signed in, show the real user.
  const signedIn = configured && !!user;
  const displayName = user?.displayName || user?.email || (configured ? "Account" : "jshin");
  const subtitle = user?.email || (configured ? "Signed in" : "Pilot account");
  const initial = (displayName.trim()[0] ?? "J").toUpperCase();
  const photoUrl = user?.photoURL ?? null;
  // Show the sign-in CTA only once we KNOW there's no user (configured but
  // signed out) — never during the pilot fallback or the initial load flash.
  const showSignIn = configured && !user;

  useEffect(() => {
    if (!mobileNavOpen && !accountOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobileNavOpen(false);
        setAccountOpen(false);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileNavOpen, accountOpen]);

  useEffect(() => {
    document.body.style.overflow = mobileNavOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [mobileNavOpen]);

  const closeAll = () => {
    setMobileNavOpen(false);
    setAccountOpen(false);
  };

  return (
    <header
      className={cn(
        "sticky top-0 z-30 w-full transition-colors",
        variant === "solid"
          ? "border-b border-ink-900/[0.06] bg-cream-100/85 backdrop-blur-md"
          : "bg-transparent",
      )}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-6">
        <Link href="/" className="group flex items-center gap-2.5 rounded-md ring-focus" onClick={closeAll}>
          <ConvtMark className="h-7 w-7" />
          <span className="display-serif text-lg font-medium tracking-tightest">Convt</span>
        </Link>

        <nav className="hidden items-center gap-1 text-sm text-ink-600 md:flex" aria-label="Main">
          {NAV_LINKS.map(({ href, label }) => (
            <Link key={href} href={href} className="rounded-full px-3 py-1.5 hover:bg-ink-900/[0.05]">
              {label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-full text-ink-700 ring-1 ring-ink-900/10 hover:bg-ink-900/[0.04] hover:ring-ink-900/20 ring-focus md:hidden"
            aria-expanded={mobileNavOpen}
            aria-controls={mobileNavId}
            aria-label={mobileNavOpen ? "Close navigation menu" : "Open navigation menu"}
            onClick={() => { setAccountOpen(false); setMobileNavOpen((o) => !o); }}
          >
            {mobileNavOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>

          {showSignIn ? (
            <button
              type="button"
              onClick={() => { setMobileNavOpen(false); void signInWithGoogle(); }}
              className="inline-flex h-10 items-center gap-2 rounded-full bg-ink-900 px-4 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus"
            >
              <LogIn className="h-4 w-4" />
              <span className="hidden sm:inline">Sign in</span>
            </button>
          ) : (
          <div className="relative">
            <button
              type="button"
              onClick={() => { setMobileNavOpen(false); setAccountOpen((o) => !o); }}
              className="group flex items-center gap-2 rounded-full bg-cream-50 px-1 py-1 pl-3 ring-1 ring-ink-900/10 hover:ring-ink-900/20 ring-focus"
              aria-expanded={accountOpen}
              aria-haspopup="menu"
              aria-controls={accountMenuId}
              aria-label="Account menu"
            >
              <span className="hidden max-w-[10ch] truncate text-sm font-medium text-ink-800 sm:inline">{displayName}</span>
              <ChevronDown className={cn("hidden h-3.5 w-3.5 text-ink-500 transition-transform sm:inline", accountOpen && "rotate-180")} />
              {photoUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={photoUrl} alt="" className="h-8 w-8 rounded-full object-cover" referrerPolicy="no-referrer" />
              ) : (
                <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-coral-400 to-plum-500 text-xs font-semibold text-cream-50">{initial}</div>
              )}
            </button>

            {accountOpen && (
              <>
                <button type="button" tabIndex={-1} className="fixed inset-0 z-30 cursor-default" onClick={() => setAccountOpen(false)} aria-label="Close account menu" />
                <div id={accountMenuId} role="menu" className="absolute right-0 z-40 mt-2 w-64 origin-top-right overflow-hidden rounded-2xl border border-ink-900/10 bg-cream-50 shadow-[0_24px_60px_-20px_rgba(31,30,27,0.25)] animate-fade-up">
                  <div className="border-b border-ink-900/[0.06] p-4">
                  <div className="truncate text-sm font-medium text-ink-900">{displayName}</div>
                  <div className="truncate text-xs text-ink-500">{subtitle}</div>
                </div>
                <div className="p-1.5">
                  <MenuLink href="/dashboard" icon={<LayoutDashboard className="h-4 w-4" />} label="My dashboard" sub="P&L · positions" onNavigate={closeAll} />
                  <MenuLink href="/dashboard#profile-settings" icon={<Settings className="h-4 w-4" />} label="Profile settings" sub="Nickname · visibility" onNavigate={closeAll} />
                  <MenuLink href="/dashboard?tab=leaderboard" icon={<Trophy className="h-4 w-4" />} label="Leaderboard" sub="Persona rankings" onNavigate={closeAll} />
                  <MenuItemSoon icon={<Users className="h-4 w-4" />} label="Social feed" sub="Forks · followers" />
                  <NotificationsToggle onDone={closeAll} />
                </div>
                {signedIn && (
                  <div className="border-t border-ink-900/[0.06] p-1.5">
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => { closeAll(); void signOut(); }}
                      className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-ink-600 hover:bg-ink-900/[0.04]"
                    >
                      <LogOut className="h-4 w-4" /> Sign out
                    </button>
                  </div>
                )}
              </div>
              </>
            )}
          </div>
          )}
        </div>
      </div>

      {mobileNavOpen && (
        <>
          <button type="button" className="fixed inset-0 z-20 bg-ink-900/20 md:hidden" aria-label="Close navigation menu" onClick={() => setMobileNavOpen(false)} />
          <nav id={mobileNavId} aria-label="Main" className="relative z-30 border-t border-ink-900/[0.06] bg-cream-100/95 px-6 py-4 backdrop-blur-md md:hidden">
            <ul className="flex flex-col gap-1">
              {NAV_LINKS.map(({ href, label }) => (
                <li key={href}>
                  <Link href={href} className="block rounded-xl px-4 py-3 text-[15px] font-medium text-ink-800 hover:bg-ink-900/[0.05] ring-focus" onClick={() => setMobileNavOpen(false)}>
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </>
      )}
    </header>
  );
}

function MenuLink({ href, icon, label, sub, onNavigate }: { href: string; icon: React.ReactNode; label: string; sub: string; onNavigate?: () => void }) {
  return (
    <Link href={href} role="menuitem" className="flex items-start gap-3 rounded-xl px-3 py-2.5 hover:bg-ink-900/[0.04]" onClick={onNavigate}>
      <span className="mt-0.5 text-ink-500">{icon}</span>
      <span>
        <span className="block text-sm font-medium text-ink-900">{label}</span>
        <span className="block text-xs text-ink-500">{sub}</span>
      </span>
    </Link>
  );
}

// Not-yet-shipped menu item: shown but disabled with a "Soon" badge so the
// surface communicates the roadmap without dead-ending into a blank tab.
function MenuItemSoon({ icon, label, sub }: { icon: React.ReactNode; label: string; sub: string }) {
  return (
    <div role="menuitem" aria-disabled className="flex items-start gap-3 rounded-xl px-3 py-2.5 opacity-55">
      <span className="mt-0.5 text-ink-400">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="text-sm font-medium text-ink-700">{label}</span>
          <span className="rounded-full bg-ink-900/[0.06] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-500">Soon</span>
        </span>
        <span className="block text-xs text-ink-500">{sub}</span>
      </span>
    </div>
  );
}
