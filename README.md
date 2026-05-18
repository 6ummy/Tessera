# Tessera — Frontend Demo

An agentic hedge-fund concept demo. Four AI analyst personas, one manager, three portfolios.
This repo is the **frontend-only MVP** (no backend, no API calls, no auth) — mock data lives in `lib/mock/`.

## Stack
- Next.js 14 (App Router) + TypeScript
- Tailwind CSS 3 with a Claude-inspired warm palette (cream + coral + sage + plum)
- Recharts for sparklines and cumulative-return charts
- Radix primitives (Dialog, Tabs) wrapped as shadcn-style components
- Lucide icons, Inter + Fraunces (serif display) + JetBrains Mono via `next/font`

## Run
```bash
npm install
npm run dev
```
Open http://localhost:3000

## Pages
| Route | What it is |
|---|---|
| `/` | Landing **and** analyst marketplace. Hero + comparison chart + 4 persona cards (click for slide-over detail). |
| `/proposals` | Today's research, side-by-side. Toggle between **By analyst** and **Consensus**. |
| `/dashboard` | Personal view. Tabs: **My portfolio**, **Leaderboard**, **Social**. Reached via the top-right user menu. |

## Design language
Warm cream surface (`#F5F4EE`), soft ink-grey text, coral accent (`#D97757`), generous whitespace, a Fraunces serif display + monospaced numerics for a financial-data feel.

## File map
```
app/
  layout.tsx              # fonts, metadata
  page.tsx                # landing / marketplace (the main page)
  proposals/page.tsx      # side-by-side proposals + consensus table
  dashboard/page.tsx      # user dashboard with tabs
  globals.css
components/
  header.tsx              # sticky nav + user menu (dropdown)
  hero/...                # inline in page.tsx
  persona-card.tsx
  persona-detail-sheet.tsx
  sparkline.tsx
  cumulative-chart.tsx
  ui/                     # button, badge, sheet, tabs
lib/
  utils.ts                # cn(), fmt, signClass
  mock/
    personas.ts           # 4 analyst personas (Warren, Cathie, Ray, Peter)
    performance.ts        # seeded random-walk return series + sparklines
    proposals.ts          # current holdings per persona + consensus rollup
```

## Notes for next iteration
- Personas are 4 to start (Value / Disruptive Growth / Macro / GARP). Add more in `lib/mock/personas.ts` and they flow through automatically.
- The “see in proposals” CTA in the persona sheet deep-links to `/proposals?focus=<id>` (highlight not wired yet).
- No real broker, no real LLM, no auth. Wire to backend in a later phase per `architecture.md`.
