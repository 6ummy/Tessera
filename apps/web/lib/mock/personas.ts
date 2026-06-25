export type PersonaStyle = "value" | "growth" | "macro" | "garp" | "contrarian" | "income" | "rotator" | "esg";

export type Persona = {
  id: string;
  name: string;
  archetype: string;
  style: PersonaStyle;
  accent: "coral" | "sage" | "plum" | "ink" | "oxblood";
  tagline: string;
  philosophy: string;
  horizon: string;
  riskLabel: "Conservative" | "Balanced" | "Aggressive";
  age: number;
  photo: string;       // path under /public — falls back to letter avatar if missing
  metrics: {
    return1y: number;   // 0.18 = +18%
    return90d: number;
    return30d: number;
    sharpe: number;
    mdd: number;        // -0.12 = -12%
    hitRate: number;    // 0.61 = 61%
    turnover: string;
    avgHold: string;
  };
  signature: string[]; // 3 short bullet phrases
};

export const PERSONAS: Persona[] = [
  {
    id: "warren",
    name: "Warren",
    archetype: "Value Investor",
    style: "value",
    accent: "ink",
    tagline: "Buy wonderful businesses at fair prices. Hold them.",
    philosophy:
      "Concentrated portfolio of companies with durable moats, strong free cash flow, and management aligned with shareholders. Indifferent to quarterly noise; sized for 5+ year holding periods.",
    horizon: "5+ years",
    riskLabel: "Conservative",
    age: 67,
    photo: "/personas/warren.jpg",
    metrics: {
      return1y: 0.142,
      return90d: 0.038,
      return30d: 0.011,
      sharpe: 1.32,
      mdd: -0.087,
      hitRate: 0.68,
      turnover: "12% / yr",
      avgHold: "3.4 yrs",
    },
    signature: ["Free cash flow yield > 6%", "Net debt / EBITDA < 2x", "ROIC trending up 3 yrs"],
  },
  {
    id: "cathie",
    name: "Cathie",
    archetype: "Disruptive Growth",
    style: "growth",
    accent: "coral",
    tagline: "Own the future. Tolerate the volatility on the way.",
    philosophy:
      "High-conviction bets on platform technologies (AI compute, genomics, energy storage) where 5-year revenue growth can compound above 30%. Position sizing reflects asymmetric upside, not short-term drawdowns.",
    horizon: "3–5 years",
    riskLabel: "Aggressive",
    age: 32,
    photo: "/personas/cathie.jpg",
    metrics: {
      return1y: 0.287,
      return90d: 0.094,
      return30d: -0.024,
      sharpe: 0.91,
      mdd: -0.241,
      hitRate: 0.54,
      turnover: "65% / yr",
      avgHold: "1.1 yrs",
    },
    signature: ["Revenue CAGR > 25%", "TAM expanding > 20% / yr", "Founder-led, R&D > 15% of rev"],
  },
  {
    id: "ray",
    name: "Ray",
    archetype: "Macro Hedger",
    style: "macro",
    accent: "plum",
    tagline: "All-weather. Diversify by economic regime.",
    philosophy:
      "Top-down allocation across equities, treasuries, gold, and inflation-protected assets based on growth and inflation regime probabilities. Goal is smooth equity curve, not maximum return.",
    horizon: "Continuous",
    riskLabel: "Balanced",
    age: 58,
    photo: "/personas/ray.jpg",
    metrics: {
      return1y: 0.094,
      return90d: 0.021,
      return30d: 0.006,
      sharpe: 1.58,
      mdd: -0.052,
      hitRate: 0.72,
      turnover: "28% / yr",
      avgHold: "Regime-based",
    },
    signature: ["Real yields signal", "Yield curve slope", "Inflation breakevens"],
  },
  {
    id: "peter",
    name: "Peter",
    archetype: "GARP",
    style: "garp",
    accent: "sage",
    tagline: "Growth at a reasonable price.",
    philosophy:
      "Companies growing earnings 15–25% per year, trading at PEG < 1.2. Looks for understandable businesses, expanding margins, and conservative balance sheets. Avoids hype.",
    horizon: "2–4 years",
    riskLabel: "Balanced",
    age: 44,
    photo: "/personas/peter.jpg",
    metrics: {
      return1y: 0.184,
      return90d: 0.052,
      return30d: 0.018,
      sharpe: 1.41,
      mdd: -0.118,
      hitRate: 0.63,
      turnover: "32% / yr",
      avgHold: "2.1 yrs",
    },
    signature: ["EPS growth 15–25%", "PEG < 1.2", "Operating margin expanding"],
  },
  {
    id: "michael",
    name: "Michael",
    archetype: "Contrarian Bear",
    style: "contrarian",
    accent: "oxblood",
    tagline: "The bubble is already here — only the burst remains.",
    philosophy:
      "Long-only expression of a bear: inverse ETFs sized to a deterministic bubble signal (fast run-up + collapsing free-cash-flow yield), plus a high cash balance, gold, Treasuries, and deep-value names. Tactical and short-horizon — never marries a hedge.",
    horizon: "Weeks",
    riskLabel: "Aggressive",
    age: 53,
    photo: "/personas/michael.png",
    metrics: {
      return1y: -0.021,
      return90d: 0.014,
      return30d: 0.006,
      sharpe: 0.42,
      mdd: -0.061,
      hitRate: 0.49,
      turnover: "High",
      avgHold: "Weeks",
    },
    signature: ["Run-up + fcf_yield collapse", "Inverse ETF, slippage-capped", "High cash / gold floor"],
  },
];

export const PERSONA_BY_ID = Object.fromEntries(PERSONAS.map((p) => [p.id, p]));

export const ACCENT_CLASS: Record<Persona["accent"], { bg: string; text: string; ring: string; dot: string }> = {
  coral: { bg: "bg-coral-50", text: "text-coral-700", ring: "ring-coral-500/30", dot: "bg-coral-500" },
  sage: { bg: "bg-sage-400/15", text: "text-sage-600", ring: "ring-sage-500/30", dot: "bg-sage-500" },
  plum: { bg: "bg-plum-500/10", text: "text-plum-600", ring: "ring-plum-500/30", dot: "bg-plum-500" },
  // Warren's dot is `ink-900` (the darkest stop) not `ink-800` so its
  // contrast against text-ink-700 / text-ink-500 labels matches the
  // visual weight of the vibrant 500-level dots on Coral / Sage / Plum.
  // Same hue family, just maxed out.
  ink: { bg: "bg-ink-900/[0.04]", text: "text-ink-800", ring: "ring-ink-800/20", dot: "bg-ink-900" },
  oxblood: { bg: "bg-oxblood-500/10", text: "text-oxblood-600", ring: "ring-oxblood-500/30", dot: "bg-oxblood-500" },
};
