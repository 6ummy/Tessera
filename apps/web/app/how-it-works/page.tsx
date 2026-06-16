import Link from "next/link";
import {
  ArrowLeft, ArrowRight, BookOpen, Eye, FileText, Lock, MessageSquare,
  ShieldCheck, Sparkles, Users,
} from "lucide-react";
import { Header } from "@/components/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export const metadata = {
  title: "How it works · Tessera",
};

export default function HowItWorks() {
  return (
    <main className="min-h-screen">
      <Header variant="solid" />

      {/* ── HERO ── */}
      <section className="relative overflow-hidden border-b border-ink-900/[0.06] bg-cream-50/40">
        <div className="absolute inset-0 -z-10 opacity-50">
          <div className="absolute left-1/2 top-0 h-[520px] w-[1000px] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgba(217,119,87,0.15),transparent_70%)]" />
        </div>
        <div className="mx-auto max-w-5xl px-6 py-20 sm:py-28">
          <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-ink-500 hover:text-ink-800">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to the desk
          </Link>
          <div className="mt-5 max-w-3xl">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">How Tessera works</div>
            <h1 className="display-serif mt-3 text-5xl leading-[1.05] tracking-tightest text-ink-900 sm:text-6xl">
              Four minds on the market.
              <br />
              <span className="italic text-ink-700">One mosaic </span>
              <span className="text-coral-600">for you.</span>
            </h1>
            <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-ink-600">
              An AI research desk of four analysts. Each reads the market daily and writes the
              long-form thesis you'd normally pay a research firm for. You read, compare, decide.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Badge tone="sage">Paper trading pilot</Badge>
              <Badge tone="default">Long-term horizon</Badge>
              <Badge tone="coral">Multi-analyst research</Badge>
            </div>
          </div>
        </div>
      </section>

      {/* ── WHAT YOU GET ── */}
      <section className="border-b border-ink-900/[0.06] py-20">
        <div className="mx-auto max-w-5xl px-6">
          <div className="max-w-2xl">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">What you get</div>
            <h2 className="display-serif mt-3 text-4xl leading-tight tracking-tightest text-ink-900">
              Institutional research, on tap.
            </h2>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-600">
              Not noisy sell-side ratings, not a DIY spreadsheet — a desk of distinct voices,
              written theses, and a shortlist you can act on.
            </p>
          </div>

          <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Tile icon={<Users className="h-4 w-4" />} title="Four analyst personas"
              body="Value, disruptive growth, macro, and GARP. Each writes from a real philosophy, not a generic AI." />
            <Tile icon={<FileText className="h-4 w-4" />} title="Long-form theses"
              body="Why each name is in the book, what would make the analyst wrong, and what to watch." />
            <Tile icon={<Eye className="h-4 w-4" />} title="Four portfolios, side-by-side"
              body="Compare the desk in one view. See where the four analysts agree, and where they disagree." />
            <Tile icon={<MessageSquare className="h-4 w-4" />} title="Chat with the desk"
              body="Ask any analyst about their book, their reasoning, or what they're avoiding right now." />
          </div>
        </div>
      </section>

      {/* ── DAILY FLOW (customer-facing) ── */}
      <section className="border-b border-ink-900/[0.06] bg-cream-50/40 py-20">
        <div className="mx-auto max-w-5xl px-6">
          <div className="max-w-2xl">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">A day on the desk</div>
            <h2 className="display-serif mt-3 text-4xl leading-tight tracking-tightest text-ink-900">
              What happens between close and your morning coffee.
            </h2>
            <p className="mt-4 text-[15px] leading-relaxed text-ink-600">
              No plumbing required — here's what you'll see when you log in.
            </p>
          </div>

          <ol className="mt-12 space-y-3">
            <FlowStep n="01" title="The desk reads everything"
              body="Earnings releases, regulatory filings, macro data, and high-signal news from the trading day. Each analyst reads from their own lens." />
            <FlowStep n="02" title="Each analyst writes their view"
              body="Warren on decade-long businesses, Cathie on AI and crypto platform shifts, Ray on the macro regime, Peter on growth at a fair price. They often disagree — that's the point." />
            <FlowStep n="03" title="The desk lines up side-by-side"
              body="All four portfolios in one view, with a consensus column for the names they agree on. Where they split is visible too." />
            <FlowStep n="04" title="You read, compare, decide"
              body="Open any portfolio, tap any position, see which analyst put it there and why. Follow the philosophy that fits you — or just read along." />
          </ol>
        </div>
      </section>

      {/* ── SAFETY ── */}
      <section className="border-b border-ink-900/[0.06] py-20">
        <div className="mx-auto max-w-5xl px-6">
          <div className="grid gap-10 lg:grid-cols-2">
            <div>
              <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">Safety by design</div>
              <h2 className="display-serif mt-3 text-4xl leading-tight tracking-tightest text-ink-900">
                Built so the AI <span className="italic text-ink-700">can't run away with it.</span>
              </h2>
              <p className="mt-4 text-[15px] leading-relaxed text-ink-600">
                AI can sound confident and still be wrong. So every analyst's output clears three
                guards before it reaches you.
              </p>
            </div>

            <ol className="space-y-3">
              <Guard
                icon={<BookOpen className="h-4 w-4" />}
                title="Facts are computed, not invented"
                body="Returns, valuations, growth — all calculated in code before the AI reads them. The analyst interprets the numbers; it can't make them up."
              />
              <Guard
                icon={<ShieldCheck className="h-4 w-4" />}
                title="Every position is validated"
                body="Each holding is checked against real tradable securities, the analyst's own rules, and the desk's risk limits. Anything inconsistent is dropped."
              />
              <Guard
                icon={<Lock className="h-4 w-4" />}
                title="Risk limits can't be overridden"
                body="Single-name caps, sector concentration, drawdown budgets — enforced in code. The AI proposes; the rules dispose."
              />
            </ol>
          </div>
        </div>
      </section>

      {/* ── PERSONAS LITE ── */}
      <section className="border-b border-ink-900/[0.06] bg-cream-50/40 py-20">
        <div className="mx-auto max-w-5xl px-6">
          <div className="max-w-2xl">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">The desk</div>
            <h2 className="display-serif mt-3 text-4xl leading-tight tracking-tightest text-ink-900">
              Four analysts. <span className="italic text-ink-700">Four philosophies.</span>
            </h2>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-600">
              No safe averaged consensus. The disagreement is the value — the real spectrum of
              views on the same name.
            </p>
          </div>

          <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <PersonaLite name="Warren" archetype="Value" age="67"
              tilt="Buys businesses he'd own for ten years. Sits in cash when nothing meets his bar." accent="bg-ink-900" />
            <PersonaLite name="Cathie" archetype="Disruptive" age="32"
              tilt="AI, robotics, crypto infrastructure. Sizes for asymmetric upside; tolerates volatility." accent="bg-coral-500" />
            <PersonaLite name="Ray" archetype="Macro" age="58"
              tilt="Allocates across regimes, not tickers. Sizes for the distribution of outcomes." accent="bg-plum-500" />
            <PersonaLite name="Peter" archetype="GARP" age="44"
              tilt="Growth at a reasonable price. Walks store aisles. Pre-commits add and trim levels." accent="bg-sage-500" />
          </div>

          <Link href="/" className="mt-8 inline-flex items-center gap-2 text-sm font-medium text-ink-700 hover:text-ink-900">
            Meet each analyst →
          </Link>
        </div>
      </section>

      {/* ── COMPLIANCE ── */}
      <section className="border-b border-ink-900/[0.06] py-20">
        <div className="mx-auto max-w-5xl px-6">
          <div className="max-w-2xl">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-coral-600">Where you stand</div>
            <h2 className="display-serif mt-3 text-4xl leading-tight tracking-tightest text-ink-900">
              We're research. <span className="italic text-ink-700">Not your broker.</span>
            </h2>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-600">
              Tessera publishes ideas. It never holds your money, trades without your say-so, or
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
            Tessera is not a registered investment advisor and gives no individualized advice.
          </p>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-20">
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

function Tile({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-ink-900/[0.06] bg-cream-50 p-5">
      <div className="grid h-9 w-9 place-items-center rounded-full bg-ink-900 text-cream-50">{icon}</div>
      <h3 className="mt-4 text-base font-medium text-ink-900">{title}</h3>
      <p className="mt-1.5 text-[13px] leading-relaxed text-ink-600">{body}</p>
    </div>
  );
}

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

function PersonaLite({ name, archetype, age, tilt, accent }: { name: string; archetype: string; age: string; tilt: string; accent: string }) {
  return (
    <div className="rounded-2xl border border-ink-900/[0.06] bg-cream-50 p-5">
      <div className="flex items-center gap-2">
        <div className={`h-1.5 w-1.5 rounded-full ${accent}`} />
        <span className="text-[10px] uppercase tracking-[0.14em] text-ink-500">{archetype} · {age}</span>
      </div>
      <h3 className="display-serif mt-1 text-2xl text-ink-900">{name}</h3>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-600">{tilt}</p>
    </div>
  );
}

function Guard({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <li className="rounded-2xl border border-ink-900/[0.06] bg-cream-50 p-5">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-coral-50 text-coral-700">
          {icon}
        </div>
        <div>
          <h4 className="text-sm font-medium text-ink-900">{title}</h4>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-600">{body}</p>
        </div>
      </div>
    </li>
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
