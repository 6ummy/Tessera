"use client";
// Kill switch — Phase F scaffolding (display only). One click → (a confirm
// step →) close every live position. NOT wired to any execution path here;
// in the pilot it's disabled because live trading is off. The real
// close-all lands post-Phase-E.

import { useState } from "react";
import { OctagonX } from "lucide-react";
import { cn } from "@/lib/utils";

export function KillSwitch({
  enabled,
  onConfirmClose,
}: {
  /** False in the pilot (live trading off) → button is disabled. */
  enabled: boolean;
  /** Called only after the user confirms. Display-only here. */
  onConfirmClose?: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  if (!confirming) {
    return (
      <button
        type="button"
        disabled={!enabled}
        onClick={() => setConfirming(true)}
        title={enabled ? "Close all live positions" : "Live trading is not enabled"}
        className={cn(
          "inline-flex h-9 items-center gap-2 rounded-full border px-4 text-sm font-medium ring-focus",
          enabled
            ? "border-coral-500/40 bg-coral-500/10 text-coral-700 hover:bg-coral-500/15"
            : "cursor-not-allowed border-ink-900/10 text-ink-400",
        )}
      >
        <OctagonX className="h-4 w-4" /> Close all positions
      </button>
    );
  }

  return (
    <div className="inline-flex items-center gap-2">
      <span className="text-xs text-ink-600">Close every live position?</span>
      <button
        type="button"
        onClick={() => { setConfirming(false); onConfirmClose?.(); }}
        className="h-8 rounded-full bg-coral-600 px-3 text-xs font-medium text-cream-50 hover:bg-coral-700 ring-focus"
      >
        Yes, close all
      </button>
      <button
        type="button"
        onClick={() => setConfirming(false)}
        className="h-8 rounded-full border border-ink-900/10 px-3 text-xs text-ink-700 hover:bg-ink-900/[0.04] ring-focus"
      >
        Cancel
      </button>
    </div>
  );
}
