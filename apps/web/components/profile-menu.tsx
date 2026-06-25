"use client";
// Top-right account dropdown — used by both the marketing Header and the app
// shell so the menu is identical everywhere (My dashboard / Profile settings /
// Leaderboard / Social feed (soon) / Notifications / Sign out). Renders the
// Sign-in CTA when signed out. Self-managed open state.

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { LayoutDashboard, Trophy, Settings, Users, LogOut, LogIn, ChevronDown } from "lucide-react";
import { useAuth } from "@/lib/firebase/auth-context";
import { NotificationsToggle } from "./notifications-toggle";
import { cn } from "@/lib/utils";

export function ProfileMenu() {
  const { configured, user, signInWithGoogle, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [nickname, setNickname] = useState<string | null>(null);
  const menuId = useId();

  // The user's chosen nickname (if any) replaces their name in the chip.
  useEffect(() => {
    if (!user) { setNickname(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const token = await user.getIdToken();
        const res = await fetch("/api/me/profile", { headers: { authorization: `Bearer ${token}` } });
        if (!res.ok || cancelled) return;
        const d = (await res.json()) as { nickname: string | null };
        if (!cancelled) setNickname(d.nickname ?? null);
      } catch { /* ignore — fall back to the name */ }
    })();
    return () => { cancelled = true; };
  }, [user]);

  const signedIn = configured && !!user;
  const fullName = user?.displayName || user?.email || (configured ? "Account" : "jshin");
  // First name only (or the email local part) so the chip stays compact;
  // a set nickname takes precedence over the real name everywhere.
  const firstName = fullName.includes("@") ? fullName.split("@")[0] : fullName.trim().split(/\s+/)[0];
  const chipName = nickname?.trim() || firstName;
  // Dropdown always shows the real full name (nickname only swaps the chip).
  const headerName = fullName;
  const subtitle = user?.email || (configured ? "Signed in" : "Pilot account");
  const initial = (chipName.trim()[0] ?? "J").toUpperCase();
  const photoUrl = user?.photoURL ?? null;
  const close = () => setOpen(false);

  // configured but no user → show the Sign-in CTA.
  if (configured && !user) {
    return (
      <button type="button" onClick={() => void signInWithGoogle()}
        className="inline-flex h-10 items-center gap-2 rounded-full bg-ink-900 px-4 text-sm font-medium text-cream-50 hover:bg-ink-800 ring-focus">
        <LogIn className="h-4 w-4" /> <span className="hidden sm:inline">Sign in</span>
      </button>
    );
  }

  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)}
        className="group flex items-center gap-2 rounded-full ring-focus sm:bg-cream-50 sm:px-1 sm:py-1 sm:pl-3 sm:ring-1 sm:ring-ink-900/10 sm:hover:ring-ink-900/20"
        aria-expanded={open} aria-haspopup="menu" aria-controls={menuId} aria-label="Account menu">
        <span className="hidden max-w-[14ch] truncate text-sm font-medium text-ink-800 sm:inline">{chipName}</span>
        <ChevronDown className={cn("hidden h-3.5 w-3.5 text-ink-500 transition-transform sm:inline", open && "rotate-180")} />
        {photoUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={photoUrl} alt="" className="h-8 w-8 rounded-full object-cover" referrerPolicy="no-referrer" />
        ) : (
          <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-coral-400 to-plum-500 text-xs font-semibold text-cream-50">{initial}</div>
        )}
      </button>

      {open && (
        <>
          <button type="button" tabIndex={-1} className="fixed inset-0 z-30 cursor-default" onClick={close} aria-label="Close account menu" />
          <div id={menuId} role="menu" className="absolute right-0 z-40 mt-2 w-64 origin-top-right overflow-hidden rounded-2xl border border-ink-900/10 bg-cream-50 shadow-[0_24px_60px_-20px_rgba(31,30,27,0.25)] animate-fade-up">
            <div className="border-b border-ink-900/[0.06] p-4">
              <div className="truncate text-sm font-medium text-ink-900">{headerName}</div>
              <div className="truncate text-xs text-ink-500">{subtitle}</div>
            </div>
            <div className="p-1.5">
              <MenuLink href="/dashboard" icon={<LayoutDashboard className="h-4 w-4" />} label="My dashboard" sub="P&L · positions" onNavigate={close} />
              <MenuLink href="/dashboard?tab=setting" icon={<Settings className="h-4 w-4" />} label="Setting" sub="Profile · email · Alpaca" onNavigate={close} />
              <MenuLink href="/dashboard?tab=leaderboard" icon={<Trophy className="h-4 w-4" />} label="Leaderboard" sub="Persona rankings" onNavigate={close} />
              <MenuItemSoon icon={<Users className="h-4 w-4" />} label="Social feed" sub="Forks · followers" />
              <NotificationsToggle onDone={close} />
            </div>
            {signedIn && (
              <div className="border-t border-ink-900/[0.06] p-1.5">
                <button type="button" role="menuitem" onClick={() => { close(); void signOut(); }}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-ink-600 hover:bg-ink-900/[0.04]">
                  <LogOut className="h-4 w-4" /> Sign out
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
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
