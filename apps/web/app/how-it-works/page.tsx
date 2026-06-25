import Link from "next/link";
import {
  ArrowLeft, ArrowRight, Calculator, Clock, Gauge, Lock, Scale, ShieldCheck,
} from "lucide-react";
import { Header } from "@/components/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export const metadata = {
  title: "How it works · Convt",
};

export default function HowItWorks() {
  return (
    <main className="min-h-screen">
      <Header variant="solid" />

      {/* ── HERO ── */}
      <section className="relative overflow-hidden border-b border-ink-900/[0.06] bg-cream-50/40">
        <div className="absolute inset-0 -z-10 opacity-50">
          <div className="absolute left-1/2 top-0 h-[460px] w-[1000px] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgba(217,119,87,0.15),transparent_70%)]" />
        </div>
        <div className="mx-auto max-w-5xl px-6 py-10 sm:py-20">
          <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-ink-500 hover:text-ink-800">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to the desk
          </Link>
          <div className="mt-5 max-w-3xl">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">How Convt works</div>
            <h1 className="display-serif mt-3 text-3xl leading-[1.08] tracking-tightest text-ink-900 sm:text-6xl sm:leading-[1.05]">
              Five minds on the market.
              <br />
              <span className="italic text-ink-700">Conviction </span>
              <span className="text-coral-600">you can follow.</span>
            </h1>
            <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-ink-600">
              An AI research desk of five analysts — value, growth, macro, GARP, and a contrarian
              bear. Each reads the market daily and writes the long-form thesis you'd normally pay a
              research firm for. You read, compare, decide.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Badge tone="sage">Paper trading pilot</Badge>
              <Badge tone="default">Long-term horizon</Badge>
              <Badge tone="coral">Multi-analyst research</Badge>
            </div>
          </div>
        </div>
      </section>

      {/* ── A DAY ON THE DESK ── */}
      <section className="border-b border-ink-900/[0.06] py-10 sm:py-16">
        <div className="mx-auto max-w-5xl px-6">
          <div className="max-w-2xl">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">A day on the desk</div>
            <h2 className="display-serif mt-3 text-3xl leading-tight tracking-tightest sm:text-4xl text-ink-900">
              From market close to your morning coffee.
            </h2>
          </div>

          <ol className="mt-10 space-y-3">
            <FlowStep n="01" title="The desk reads everything"
              body="Earnings, filings, macro data, and high-signal news from the trading day — each analyst through their own lens." />
            <FlowStep n="02" title="Each analyst writes their view"
              body="Warren on decade-long businesses, Cathie on AI and crypto platform shifts, Ray on the macro regime, Peter on growth at a fair price, Michael on where the bubble breaks. They often disagree — that's the point." />
            <FlowStep n="03" title="The desk lines up side-by-side"
              body="All five portfolios in one view, with a consensus column for the names they agree on. Where they split is visible too." />
            <FlowStep n="04" title="You read, compare, decide"
              body="Open any portfolio, tap any position, see which analyst put it there and why. Follow the philosophy that fits you — or just read along." />
          </ol>

          <Link href="/" className="mt-8 inline-flex items-center gap-2 text-sm font-medium text-ink-700 hover:text-ink-900">
            Meet the analysts <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </section>

      {/* ── VALIDATED SAFEGUARDS ── */}
      <section className="border-b border-ink-900/[0.06] bg-cream-50/40 py-10 sm:py-16">
        <div className="mx-auto max-w-5xl px-6">
          <div className="max-w-2xl">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">Validated safeguards</div>
            <h2 className="display-serif mt-3 text-3xl leading-tight tracking-tightest sm:text-4xl text-ink-900">
              Built so the AI <span className="italic text-ink-700">can't run away with it.</span>
            </h2>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-600">
              AI sounds confident even when it's wrong. So every output clears the same
              deterministic guards — the ones we've hardened in production.
            </p>
          </div>

          <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Safeguard icon={<Calculator className="h-4 w-4" />} title="Numbers come from code"
              body="Returns, valuations, growth, P&L — all computed in Python. The AI reads the numbers; it never makes them up." />
            <Safeguard icon={<ShieldCheck className="h-4 w-4" />} title="No invented tickers"
              body="Every position is checked against the real tradable universe. Hallucinated symbols are dropped at the gate." />
            <Safeguard icon={<Lock className="h-4 w-4" />} title="Hard risk limits"
              body="Single-name caps, sector limits, value-at-risk, drawdown floors — enforced in code. The AI proposes; the rules dispose." />
            <Safeguard icon={<Clock className="h-4 w-4" />} title="No stale data"
              body="Each data point carries its age. Anything past a freshness bound or outside a sanity range is dropped before the analyst sees it." />
            <Safeguard icon={<Scale className="h-4 w-4" />} title="Portfolios always add up"
              body="Weights are normalized in code to sum to exactly 100%. The model's sizing intent is honored; the arithmetic is guaranteed." />
            <Safeguard icon={<Gauge className="h-4 w-4" />} title="Budgeted & rate-limited"
              body="Daily cost ceilings and per-user limits keep the desk — and public chat — inside predictable bounds." />
          </div>
        </div>
      </section>

      {/* ── COMPLIANCE ── */}
      <section className="border-b border-ink-900/[0.06] py-10 sm:py-16">
        <div className="mx-auto max-w-5xl px-6">
          <div className="max-w-2xl">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">Where you stand</div>
            <h2 className="display-serif mt-3 text-3xl leading-tight tracking-tightest sm:text-4xl text-ink-900">
              We're research. <span className="italic text-ink-700">Not your broker.</span>
            </h2>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-600">
              Convt publishes ideas. It never holds your money, trades without your say-so, or
              tells you what's right for your account.
            </p>
          </div>

          <div className="mt-10 grid gap-4 md:grid-cols-2">
            <ComplianceCard
              tone="ok"
              title="What we do"
              items={[
                "Publish written theses and curated portfolios.",
                "Show you the analyst behind every position.",
                "Track each analyst's performance, openly.",
                "Let you follow a portfolio on paper at no risk.",
              ]}
            />
            <ComplianceCard
              tone="bad"
              title="What we don't do"
              items={[
                "Hold or move your funds. Ever.",
                "Place live trades without your explicit approval.",
                "Provide personalized advice for your situation.",
                "Promise returns. Nobody can.",
              ]}
            />
          </div>

          <p className="mt-8 max-w-2xl text-[13px] leading-relaxed text-ink-500">
            Pilot phase is paper trading only — no real money, no brokerage connection. Any future
            live execution would route through your own brokerage and require your confirmation on
            every order. Past performance, paper or otherwise, doesn't predict future results.
            Convt is not a registered investment advisor and gives no individualized advice.
          </p>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-16">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">Ready</div>
          <h2 className="display-serif mt-3 text-5xl leading-[1.05] tracking-tightest text-ink-900">
            Read what the desk thinks <span className="italic text-ink-700">today.</span>
          </h2>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link href="/proposals"><Button size="lg">See today's proposals <ArrowRight className="h-4 w-4" /></Button></Link>
            <Link href="/"><Button size="lg" variant="outline">Meet the analysts</Button></Link>
          </div>
        </div>
      </section>
    </main>
  );
}

/* ──────────────────── COMPONENTS ──────────────────── */

function FlowStep({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <li className="grid grid-cols-[56px_1fr] gap-5 rounded-2xl border border-ink-900/[0.06] bg-cream-50 p-6 transition-colors hover:border-ink-900/[0.12]">
      <div className="display-serif text-3xl text-coral-600">{n}</div>
      <div>
        <h3 className="text-base font-medium text-ink-900">{title}</h3>
        <p className="mt-1.5 text-[14px] leading-relaxed text-ink-600">{body}</p>
      </div>
    </li>
  );
}

function Safeguard({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-ink-900/[0.06] bg-cream-50 p-5">
      <div className="flex items-center gap-2.5">
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-coral-50 text-coral-700">
          {icon}
        </div>
        <h3 className="text-sm font-medium text-ink-900">{title}</h3>
      </div>
      <p className="mt-2.5 text-[13px] leading-relaxed text-ink-600">{body}</p>
    </div>
  );
}

function ComplianceCard({ tone, title, items }: { tone: "ok" | "bad"; title: string; items: string[] }) {
  const dot = tone === "ok" ? "bg-sage-500" : "bg-coral-500";
  return (
    <div className="rounded-3xl border border-ink-900/[0.06] bg-cream-50 p-7">
      <h3 className="display-serif text-2xl text-ink-900">{title}</h3>
      <ul className="mt-4 space-y-2.5">
        {items.map((i) => (
          <li key={i} className="flex items-start gap-3 text-[14px] leading-relaxed text-ink-700">
            <span className={`mt-2 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
            {i}
          </li>
        ))}
      </ul>
    </div>
  );
}
