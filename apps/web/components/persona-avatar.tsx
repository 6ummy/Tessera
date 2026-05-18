"use client";
import { useState } from "react";
import Image from "next/image";
import type { Persona } from "@/lib/mock/personas";
import { ACCENT_CLASS } from "@/lib/mock/personas";
import { cn } from "@/lib/utils";

type Size = "xs" | "sm" | "md" | "lg" | "xl";

const SIZES: Record<Size, { box: string; text: string; px: number }> = {
  xs: { box: "h-7 w-7",   text: "text-[11px]", px: 28 },
  sm: { box: "h-9 w-9",   text: "text-xs",     px: 36 },
  md: { box: "h-12 w-12", text: "text-sm",     px: 48 },
  lg: { box: "h-16 w-16", text: "text-lg",     px: 64 },
  xl: { box: "h-24 w-24", text: "text-2xl",    px: 96 },
};

export function PersonaAvatar({
  persona,
  size = "md",
  className,
  ring = false,
}: {
  persona: Persona;
  size?: Size;
  className?: string;
  ring?: boolean;
}) {
  const [errored, setErrored] = useState(false);
  const a = ACCENT_CLASS[persona.accent];
  const s = SIZES[size];
  const showPhoto = persona.photo && !errored;

  return (
    <div
      className={cn(
        "relative shrink-0 overflow-hidden rounded-full",
        s.box,
        ring && "ring-2 ring-cream-50 ring-offset-2 ring-offset-cream-100",
        className
      )}
    >
      {showPhoto ? (
        <Image
          src={persona.photo}
          alt={persona.name}
          width={s.px}
          height={s.px}
          className="h-full w-full object-cover"
          onError={() => setErrored(true)}
          priority={size === "xl"}
        />
      ) : (
        <div
          className={cn(
            "flex h-full w-full items-center justify-center font-semibold text-cream-50",
            a.dot,
            s.text
          )}
          aria-label={persona.name}
        >
          {persona.name[0]}
        </div>
      )}
    </div>
  );
}
