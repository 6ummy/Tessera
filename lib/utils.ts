import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const fmt = {
  pct: (n: number, digits = 1) => `${n >= 0 ? "+" : ""}${(n * 100).toFixed(digits)}%`,
  pctAbs: (n: number, digits = 1) => `${(n * 100).toFixed(digits)}%`,
  num: (n: number, digits = 2) => n.toFixed(digits),
};

export const signClass = (n: number) =>
  n > 0 ? "text-sage-600" : n < 0 ? "text-coral-600" : "text-ink-500";
