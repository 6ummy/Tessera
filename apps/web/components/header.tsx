"use client";
import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { Menu, X } from "lucide-react";
import { ProfileMenu } from "@/components/profile-menu";
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
  const mobileNavId = useId();

  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") setMobileNavOpen(false); };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileNavOpen]);

  useEffect(() => {
    document.body.style.overflow = mobileNavOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [mobileNavOpen]);

  const closeNav = () => setMobileNavOpen(false);

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
        <Link href="/" className="group flex items-center gap-2.5 rounded-md ring-focus" onClick={closeNav}>
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
            onClick={() => setMobileNavOpen((o) => !o)}
          >
            {mobileNavOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>

          {/* Shared account dropdown / sign-in CTA (same component the app shell uses). */}
          <ProfileMenu />
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
