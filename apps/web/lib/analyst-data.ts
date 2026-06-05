// Client-side fetchers for /api/reports + /api/proposals.
// Both routes proxy to the Cloud Run worker; both Edge-cached for 60s
// at the CDN so the persona-detail-sheet's 4-persona fan-out is fast.

import type { Proposal, Report } from "./thesis-types";

const FETCH_TIMEOUT_MS = 20_000;

async function safeJson<T>(resp: Response, fallback: T): Promise<T> {
  try {
    return (await resp.json()) as T;
  } catch {
    return fallback;
  }
}

export async function fetchReports(
  personaId: string,
  opts: { limit?: number; signal?: AbortSignal } = {},
): Promise<Report[]> {
  const limit = opts.limit ?? 5;
  const url = `/api/reports/${personaId}?limit=${limit}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  const signal = opts.signal
    ? mergeSignals(opts.signal, ctrl.signal)
    : ctrl.signal;
  try {
    const resp = await fetch(url, { signal });
    if (!resp.ok) return [];
    const body = await safeJson<{ reports?: Report[] }>(resp, {});
    return body.reports ?? [];
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchProposal(
  personaId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<Proposal | null> {
  const url = `/api/proposals/${personaId}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  const signal = opts.signal
    ? mergeSignals(opts.signal, ctrl.signal)
    : ctrl.signal;
  try {
    const resp = await fetch(url, { signal });
    if (!resp.ok) return null;
    const body = await safeJson<Proposal | { ok: false }>(resp, { ok: false });
    if ("ok" in body && body.ok === false) return null;
    return body as Proposal;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function mergeSignals(a: AbortSignal, b: AbortSignal): AbortSignal {
  if (a.aborted) return a;
  if (b.aborted) return b;
  const ctrl = new AbortController();
  const onAbort = () => ctrl.abort();
  a.addEventListener("abort", onAbort);
  b.addEventListener("abort", onAbort);
  return ctrl.signal;
}
