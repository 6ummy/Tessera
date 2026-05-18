import { PERSONAS } from "./personas";

export type Position = {
  ticker: string;
  name: string;
  sector: string;
  weight: number;        // 0.12 = 12%
  side: "long" | "short";
  conviction: number;    // 0..1
  thesis: string;        // one-paragraph rationale
};

export type Proposal = {
  personaId: string;
  asOf: string;
  horizon: string;
  expectedReturn: number;   // 12-month forward estimate
  expectedVol: number;
  cashWeight: number;
  positions: Position[];
};

export const PROPOSALS: Proposal[] = [
  {
    personaId: "warren",
    asOf: "2026-05-17",
    horizon: "5+ years",
    expectedReturn: 0.11,
    expectedVol: 0.13,
    cashWeight: 0.12,
    positions: [
      { ticker: "BRK.B", name: "Berkshire Hathaway", sector: "Financials", weight: 0.18, side: "long", conviction: 0.92,
        thesis: "Diversified compounder with $180B cash optionality. Float at near-zero cost remains an unmatched structural edge as rates normalize." },
      { ticker: "COST", name: "Costco", sector: "Consumer Staples", weight: 0.14, side: "long", conviction: 0.88,
        thesis: "Membership economics produce predictable 8% comp growth and high renewal rates. Pricing power without inventory risk." },
      { ticker: "MCO", name: "Moody's", sector: "Financials", weight: 0.11, side: "long", conviction: 0.85,
        thesis: "Duopoly in credit ratings with 50%+ operating margins. Issuance volume rebounding as refinancing wall approaches." },
      { ticker: "MA", name: "Mastercard", sector: "Financials", weight: 0.13, side: "long", conviction: 0.86,
        thesis: "Network-effect toll road on global payments. Cross-border travel recovery adds incremental high-margin volume." },
      { ticker: "WMT", name: "Walmart", sector: "Consumer Staples", weight: 0.10, side: "long", conviction: 0.78,
        thesis: "Ad business now $4B+ run-rate at 70% margins. Sam's Club membership growth funds e-commerce flywheel." },
      { ticker: "GOOGL", name: "Alphabet", sector: "Communication Services", weight: 0.12, side: "long", conviction: 0.81,
        thesis: "Search remains a productivity layer even in an AI-mediated world. YouTube + Cloud now > 30% of revenue and growing 20%+." },
      { ticker: "JNJ", name: "Johnson & Johnson", sector: "Healthcare", weight: 0.10, side: "long", conviction: 0.74,
        thesis: "Pharma pipeline de-risked post-Kenvue spin. Talc litigation overhang largely priced in at 14x forward earnings." },
    ],
  },
  {
    personaId: "cathie",
    asOf: "2026-05-17",
    horizon: "3–5 years",
    expectedReturn: 0.34,
    expectedVol: 0.42,
    cashWeight: 0.05,
    positions: [
      { ticker: "NVDA", name: "NVIDIA", sector: "Technology", weight: 0.16, side: "long", conviction: 0.94,
        thesis: "Inference workload is 10x the size of training. CUDA moat keeps gross margins above 70% even as competition emerges." },
      { ticker: "TSLA", name: "Tesla", sector: "Consumer Discretionary", weight: 0.14, side: "long", conviction: 0.82,
        thesis: "Autonomy and robotaxi optionality undervalued in current price. Energy storage business compounding at 40%+." },
      { ticker: "PLTR", name: "Palantir", sector: "Technology", weight: 0.09, side: "long", conviction: 0.78,
        thesis: "AIP is the first defensible enterprise LLM ops layer. Commercial bookings now growing faster than government." },
      { ticker: "CRWD", name: "CrowdStrike", sector: "Technology", weight: 0.10, side: "long", conviction: 0.84,
        thesis: "Falcon platform consolidates 6+ point products. Identity and cloud workload modules drive net retention above 120%." },
      { ticker: "TEM", name: "Tempus AI", sector: "Healthcare", weight: 0.07, side: "long", conviction: 0.71,
        thesis: "Multimodal oncology data moat. Generative biology pipeline a free option on top of high-margin genomics business." },
      { ticker: "COIN", name: "Coinbase", sector: "Financials", weight: 0.08, side: "long", conviction: 0.69,
        thesis: "Stablecoin distribution and L2 base layer compound regardless of trading volume. Regulatory clarity expanding TAM." },
      { ticker: "SHOP", name: "Shopify", sector: "Technology", weight: 0.11, side: "long", conviction: 0.83,
        thesis: "Operating leverage finally visible as cloud-cost optimization completes. Cross-border merchant volume growing 30%+." },
      { ticker: "RBLX", name: "Roblox", sector: "Communication Services", weight: 0.08, side: "long", conviction: 0.65,
        thesis: "User-generated 3D content engine becoming the iOS of immersive media. Ad platform monetization just beginning." },
      { ticker: "ASML", name: "ASML", sector: "Technology", weight: 0.12, side: "long", conviction: 0.89,
        thesis: "Sole EUV provider. High-NA lithography ramp through 2027 gives multi-year revenue visibility no peer can match." },
    ],
  },
  {
    personaId: "ray",
    asOf: "2026-05-17",
    horizon: "Continuous",
    expectedReturn: 0.085,
    expectedVol: 0.08,
    cashWeight: 0.08,
    positions: [
      { ticker: "VTI",  name: "US Total Market",  sector: "Equity ETF",   weight: 0.28, side: "long", conviction: 0.80,
        thesis: "Core equity exposure sized for current growth regime (above-trend, moderating). Re-balance trigger at ±5% drift." },
      { ticker: "VXUS", name: "Intl ex-US",       sector: "Equity ETF",   weight: 0.12, side: "long", conviction: 0.72,
        thesis: "Valuation gap with US near 20-year wide. Dollar mean-reversion provides FX tailwind over the cycle." },
      { ticker: "IEF",  name: "7–10y Treasuries", sector: "Govt Bond",    weight: 0.18, side: "long", conviction: 0.78,
        thesis: "Duration hedge against recession scenario. Real yields above 2% offer carry not seen since 2009." },
      { ticker: "TLT",  name: "20+y Treasuries",  sector: "Govt Bond",    weight: 0.10, side: "long", conviction: 0.66,
        thesis: "Long-duration kicker if Fed cuts faster than market expects. Sized smaller given fiscal supply risk." },
      { ticker: "TIP",  name: "TIPS",             sector: "Inflation",    weight: 0.10, side: "long", conviction: 0.70,
        thesis: "Inflation breakevens still below long-run trend. Protects portfolio if energy or wage pressures reaccelerate." },
      { ticker: "GLD",  name: "Gold",             sector: "Commodities",  weight: 0.08, side: "long", conviction: 0.74,
        thesis: "Central bank buying continues at multi-decade highs. Negative correlation to real yields restored." },
      { ticker: "DBC",  name: "Broad Commodities",sector: "Commodities",  weight: 0.06, side: "long", conviction: 0.60,
        thesis: "Industrial metals exposure for electrification capex cycle. Diversifies energy concentration." },
    ],
  },
  {
    personaId: "peter",
    asOf: "2026-05-17",
    horizon: "2–4 years",
    expectedReturn: 0.16,
    expectedVol: 0.18,
    cashWeight: 0.08,
    positions: [
      { ticker: "META", name: "Meta Platforms", sector: "Communication Services", weight: 0.13, side: "long", conviction: 0.85,
        thesis: "EPS growing 20%+ at sub-20x forward. Reels monetization closing gap to feed; AI capex starting to pay back in ad targeting." },
      { ticker: "ANET", name: "Arista Networks", sector: "Technology", weight: 0.11, side: "long", conviction: 0.82,
        thesis: "AI back-end networking displaces Infiniband at hyperscalers. EPS CAGR 18% with PEG of 1.1." },
      { ticker: "BKNG", name: "Booking Holdings", sector: "Consumer Discretionary", weight: 0.10, side: "long", conviction: 0.79,
        thesis: "Direct booking mix expanding, marketing spend leverage. Mid-teens EPS growth at 18x — classic GARP setup." },
      { ticker: "ISRG", name: "Intuitive Surgical", sector: "Healthcare", weight: 0.09, side: "long", conviction: 0.81,
        thesis: "Da Vinci 5 launch drives utilization step-up. Recurring instrument revenue 70%+ with margin expansion." },
      { ticker: "LRCX", name: "Lam Research", sector: "Technology", weight: 0.10, side: "long", conviction: 0.77,
        thesis: "HBM and 3D NAND capex inflection. Memory recovery + AI accelerator demand drives 20% EPS CAGR through 2027." },
      { ticker: "TSM",  name: "TSMC", sector: "Technology", weight: 0.12, side: "long", conviction: 0.86,
        thesis: "2nm node ramp and Arizona fab subsidies improve margin trajectory. Trading at 18x with 22% EPS growth." },
      { ticker: "NOW",  name: "ServiceNow", sector: "Technology", weight: 0.09, side: "long", conviction: 0.74,
        thesis: "Now Assist attach rate accelerating. RPO growth re-accelerating after 2023 deceleration; PEG back below 1.5." },
      { ticker: "DECK", name: "Deckers Outdoor", sector: "Consumer Discretionary", weight: 0.08, side: "long", conviction: 0.69,
        thesis: "HOKA international runway. Inventory normalized; mid-teens EPS growth at 22x with net cash balance sheet." },
      { ticker: "URI",  name: "United Rentals", sector: "Industrials", weight: 0.10, side: "long", conviction: 0.72,
        thesis: "Mega-project backlog (chip, data center, reshoring) supports utilization through 2028. EPS CAGR 14% at 14x." },
    ],
  },
];

export const PROPOSAL_BY_PERSONA = Object.fromEntries(PROPOSALS.map((p) => [p.personaId, p]));

// All unique tickers across all proposals (for "consensus" view)
export const ALL_TICKERS = Array.from(
  new Set(PROPOSALS.flatMap((p) => p.positions.map((pos) => pos.ticker)))
).sort();

// Consensus: which personas mentioned each ticker?
export type ConsensusRow = {
  ticker: string;
  name: string;
  sector: string;
  mentions: { personaId: string; weight: number; conviction: number }[];
  avgConviction: number;
  totalWeight: number;
};

export const CONSENSUS: ConsensusRow[] = ALL_TICKERS.map((ticker) => {
  const mentions = PROPOSALS.flatMap((p) =>
    p.positions
      .filter((pos) => pos.ticker === ticker)
      .map((pos) => ({ personaId: p.personaId, weight: pos.weight, conviction: pos.conviction, name: pos.name, sector: pos.sector }))
  );
  const first = mentions[0];
  return {
    ticker,
    name: first.name,
    sector: first.sector,
    mentions: mentions.map(({ personaId, weight, conviction }) => ({ personaId, weight, conviction })),
    avgConviction: mentions.reduce((s, m) => s + m.conviction, 0) / mentions.length,
    totalWeight: mentions.reduce((s, m) => s + m.weight, 0),
  };
}).sort((a, b) => b.mentions.length - a.mentions.length || b.avgConviction - a.avgConviction);
