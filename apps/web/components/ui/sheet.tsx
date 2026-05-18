"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Sheet = Dialog.Root;
export const SheetTrigger = Dialog.Trigger;
export const SheetClose = Dialog.Close;

export function SheetContent({
  children,
  className,
  side = "right",
}: {
  children: React.ReactNode;
  className?: string;
  side?: "right" | "bottom";
}) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-40 bg-ink-900/30 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in" />
      <Dialog.Content
        className={cn(
          "fixed z-50 bg-cream-50 shadow-2xl outline-none",
          side === "right" &&
            "right-0 top-0 h-full w-full max-w-2xl border-l border-ink-900/10 data-[state=open]:animate-in data-[state=open]:slide-in-from-right",
          side === "bottom" &&
            "bottom-0 left-0 right-0 max-h-[85vh] rounded-t-3xl border-t border-ink-900/10",
          className
        )}
      >
        <Dialog.Close
          aria-label="Close"
          className="absolute right-5 top-5 z-10 rounded-full p-1.5 text-ink-500 hover:bg-ink-900/[0.05] hover:text-ink-800 ring-focus"
        >
          <X className="h-4 w-4" />
        </Dialog.Close>
        {children}
      </Dialog.Content>
    </Dialog.Portal>
  );
}
