export type Report = {
  id: string;
  personaId: string;
  date: string;
  title: string;
  tickers: string[];
  type: "thesis" | "update" | "macro" | "exit";
  summary: string;         // one-line hook shown in list
  body: string[];          // markdown-ish paragraphs
  numerics?: { label: string; value: string }[];
  whatWouldMakeMeWrong?: string[];
};

export const REPORTS: Report[] = [
  // ──────────────── WARREN ────────────────
  {
    id: "warren-2026-05-12-cost",
    personaId: "warren",
    date: "2026-05-12",
    title: "Costco at 48x — paying for the right things",
    tickers: ["COST"],
    type: "thesis",
    summary:
      "The multiple looks rich until you decompose what you're actually buying. Membership renewal is the asset.",
    body: [
      "Most investors look at Costco and see a 48x earnings multiple on a grocer. That framing is wrong. We are not buying a grocer; we are buying a 93% renewal-rate membership annuity attached to a working-capital-negative distribution engine.",
      "The membership fee line is approximately $4.8B annually and translates almost dollar-for-dollar to operating income. Strip that out and the merchandise business runs at roughly breakeven by design. This is the model: charge a toll for access, sell merchandise at 11% gross margin, and let scale do the rest.",
      "Renewal rates have stayed within 90–93% through three recessions and a pandemic. There is no software business in the S&P 500 with a more durable retention curve. The membership fee was raised last year and we saw zero detectable churn. That is pricing power without a feature roadmap.",
      "Our entry-yield bar is 6% free cash flow yield. Costco does not clear that today. We size at 14% rather than 18% because of valuation, not business quality. We will buy more on any 20% drawdown without further analysis.",
    ],
    numerics: [
      { label: "FCF yield", value: "3.1%" },
      { label: "Renewal rate", value: "93%" },
      { label: "Net cash / market cap", value: "2.4%" },
      { label: "10-yr same-store CAGR", value: "+6.8%" },
      { label: "Position weight", value: "14%" },
    ],
    whatWouldMakeMeWrong: [
      "Membership renewals drop below 88% for two consecutive quarters.",
      "Ron Vachris reverses on the no-online-pricing-game discipline.",
      "Sam's Club closes the gap on membership perceived value (we track NPS quarterly).",
    ],
  },
  {
    id: "warren-2026-04-28-trim",
    personaId: "warren",
    date: "2026-04-28",
    title: "Trimming Mastercard — not selling, just sizing",
    tickers: ["MA"],
    type: "update",
    summary:
      "Position grew from 9% to 16% on price appreciation. We are not predicting weakness; we are respecting risk.",
    body: [
      "Mastercard has done nothing wrong. Cross-border volumes are running 17% above 2019, network economics remain intact, and ad-supported merchant solutions are growing 40% off a small base. The business is better than when we sized it.",
      "But position discipline is a separate question from business quality. A 16% single-name weight requires us to ask: if this name dropped 50% tomorrow on a regulatory event we did not foresee, would we still sleep? Honest answer: not at 16%. We are trimming to 13%.",
      "We will not redeploy the proceeds today. Cash earning 4.8% is a perfectly acceptable parking spot. If valuations elsewhere on the watch list improve by 15% or more, we redeploy then.",
      "Patience is a position too.",
    ],
    numerics: [
      { label: "Trim from", value: "16% → 13%" },
      { label: "Proceeds", value: "to cash" },
      { label: "Position cost basis", value: "$312" },
      { label: "Current price", value: "$548" },
    ],
  },

  // ──────────────── CATHIE ────────────────
  {
    id: "cathie-2026-05-15-asml",
    personaId: "cathie",
    date: "2026-05-15",
    title: "ASML: the only path to sub-2nm",
    tickers: ["ASML"],
    type: "thesis",
    summary:
      "High-NA EUV is not a feature upgrade — it is the entire roadmap. We are buyers into any 20%+ drawdown.",
    body: [
      "Every chip below 3nm in the next decade will be patterned by an ASML machine. Not most. All. Intel, TSMC, and Samsung have publicly committed to High-NA EUV for their 2nm and below nodes, and ASML is the sole supplier of those tools at the price point of approximately $380M per unit.",
      "Bears point to lumpiness in TWINSCAN orders. We see lumpiness as feature, not bug — these are $300M+ capital assets sold in single-digit annual unit counts. Bookings move in chunks. What matters is multi-year backlog visibility, currently extending into 2028.",
      "Our base case assumes 22% revenue CAGR through 2028, driven by High-NA ramp (zero today, ~25% of EUV revenue by 2027). Operating margins expand from 31% to 36% as High-NA achieves install-base scale. This yields $58 EPS by 2028 against $24 today.",
      "At $1,000 entry, we are paying 17x 2028 earnings for a structurally protected monopoly with mid-teens revenue growth and expanding margins. That is the kind of asymmetry that compounds.",
    ],
    numerics: [
      { label: "Position weight", value: "12%" },
      { label: "Conviction", value: "0.89" },
      { label: "Bear / Base / Bull 2028 px", value: "$650 / $1,400 / $2,100" },
      { label: "Backlog coverage", value: "2.4 yrs" },
      { label: "TAM 2030E", value: "$140B" },
    ],
    whatWouldMakeMeWrong: [
      "Functional alternative to EUV for sub-2nm emerges (none in literature today).",
      "TSMC + Intel + Samsung combined wafer capex falls > 25% YoY for two years.",
      "Export controls expand to block all High-NA shipments, not just China.",
    ],
  },
  {
    id: "cathie-2026-04-30-coin",
    personaId: "cathie",
    date: "2026-04-30",
    title: "Coinbase: stablecoin distribution is the actual business",
    tickers: ["COIN"],
    type: "update",
    summary:
      "Trading revenue gets the headlines. USDC distribution and Base L2 are quietly becoming the moat.",
    body: [
      "If you are still modeling Coinbase as a function of crypto trading volume, you are modeling 2021. The interesting line items now are USDC interest revenue and Base sequencer fees. Together they ran at a $1.4B annualized rate last quarter — recurring, high-margin, and largely uncorrelated to BTC price.",
      "Base is becoming the default consumer-facing L2 of the Ethereum ecosystem. Daily active addresses crossed 4M, and the sequencer captures roughly 90% of the value generated on-chain. This is closer to a payment-rail business than to a brokerage.",
      "We are not adjusting position size today. We are flagging that the bear case (crypto winter, trading volume halves) is now significantly less destructive than it would have been in 2022. Floor revenue from USDC and Base is approximately 60% of estimated 2026 revenue.",
    ],
    numerics: [
      { label: "USDC + Base revenue", value: "~$1.4B run-rate" },
      { label: "Position weight", value: "8%" },
      { label: "Base DAA", value: "4.1M" },
      { label: "Revenue 'floor' coverage", value: "~60%" },
    ],
  },

  // ──────────────── RAY ────────────────
  {
    id: "ray-2026-05-14-regime",
    personaId: "ray",
    date: "2026-05-14",
    title: "Regime map: rising growth, easing inflation — but watch real yields",
    tickers: ["IEF", "TLT", "TIP", "GLD"],
    type: "macro",
    summary:
      "Quadrant probability shifted toward Goldilocks. Tilting equities up; trimming long-duration; holding gold.",
    body: [
      "We update regime probabilities every Sunday. This week's shift is meaningful but not extreme. The model now assigns 46% probability to 'rising growth + falling inflation' (Goldilocks), up from 31% a month ago. Probability of 'falling growth + rising inflation' (stagflation) dropped from 22% to 14%.",
      "Drivers: PMI new orders crossed back above 52, wage growth decelerated to 3.4% YoY, and energy futures suggest oil-driven inflation passes through over the next two quarters. None of these are decisive on their own; together they shift the posterior.",
      "Allocation response is modest. Equity tilt moves from 38% to 42% (within bands). Long-duration Treasuries trim from 12% to 10%. We are keeping gold at 8% — central bank buying remains structurally elevated and the asset is doing exactly what we hire it to do.",
      "We do not predict the next CPI print. We position for the distribution of outcomes weighted by their probability, and we rebalance when probabilities move enough to matter. They did this week.",
    ],
    numerics: [
      { label: "Goldilocks probability", value: "46% (+15pp)" },
      { label: "Stagflation probability", value: "14% (-8pp)" },
      { label: "Equity tilt", value: "38% → 42%" },
      { label: "TLT trim", value: "12% → 10%" },
    ],
  },
  {
    id: "ray-2026-04-22-corr",
    personaId: "ray",
    date: "2026-04-22",
    title: "Correlation regime change — bonds finally diversifying again",
    tickers: ["TLT", "IEF"],
    type: "macro",
    summary:
      "30-day equity-Treasury correlation flipped from +0.4 to -0.2 over the past six weeks. This matters more than the level of yields.",
    body: [
      "Through 2022–2023 the diversification properties of long-duration Treasuries collapsed. Stocks and bonds fell together, the foundational assumption of any balanced portfolio broke, and our drawdowns reflected it.",
      "We are now seeing the structural relationship reassert. Six-week rolling equity-Treasury correlation is back at -0.2, comparable to the 2014–2019 regime. Mechanism: inflation surprises are no longer the dominant macro signal — growth surprises are — and bonds rally on growth shocks in either direction.",
      "This is not a forecast. It is an observation that the hedge is working again. We are sizing duration to its historical role rather than the past two years' broken behavior. Expect MDD to compress over the next 12 months if this holds.",
    ],
    numerics: [
      { label: "Eq–Treasury 6w corr", value: "-0.21" },
      { label: "Trailing 24m corr", value: "+0.18" },
      { label: "Duration exposure", value: "28% (was 22%)" },
    ],
  },

  // ──────────────── PETER ────────────────
  {
    id: "peter-2026-05-10-anet",
    personaId: "peter",
    date: "2026-05-10",
    title: "Arista: networks for AI factories",
    tickers: ["ANET"],
    type: "thesis",
    summary:
      "EPS growing 18% at 21x. Picks-and-shovels exposure to AI capex without paying NVIDIA multiples.",
    body: [
      "Here is the simple version. Every AI training cluster needs back-end networking. Historically that meant InfiniBand from NVIDIA. Increasingly it means Ethernet — and Arista owns the high-end Ethernet switching market for hyperscalers.",
      "I like businesses I can explain to my mother. Arista sells the boxes that move data between GPUs. They sell to Microsoft, Meta, Oracle Cloud. They are best-in-class on software (EOS) and have been for fifteen years. Now their TAM just tripled because AI back-end networking is a brand-new buyer category.",
      "EPS growth: 18% three-year CAGR. PEG: 1.1. Net cash balance sheet. Insider ownership above 7%. Operating margin 41% and expanding. This is what GARP looks like when it shows up — you do not need a complicated model.",
      "What I am watching: gross margin compression from custom silicon, and Cisco re-entering with credible product. Both risks are real but not imminent. Position size 11% with room to add on a pullback toward $280.",
    ],
    numerics: [
      { label: "Forward P/E", value: "21x" },
      { label: "EPS CAGR (3y)", value: "+18%" },
      { label: "PEG", value: "1.1" },
      { label: "Op margin", value: "41%" },
      { label: "Net cash / mkt cap", value: "8%" },
      { label: "Position", value: "11%" },
    ],
    whatWouldMakeMeWrong: [
      "Hyperscaler capex growth turns negative for two quarters (we re-underwrite at that point).",
      "Cisco's Silicon One platform takes more than 15% share at any top-4 hyperscaler.",
      "Gross margin slips below 60% on customer mix shift.",
    ],
  },
  {
    id: "peter-2026-04-18-deck",
    personaId: "peter",
    date: "2026-04-18",
    title: "Deckers: HOKA is not a fad, it's a category",
    tickers: ["DECK"],
    type: "thesis",
    summary:
      "International HOKA penetration is where US was three years ago. Same playbook, same outcome.",
    body: [
      "Walk through any major city — Tokyo, London, Seoul — and count the HOKA pairs on commuter feet. Three years ago you would have seen one in a hundred. Today closer to one in twenty. International is roughly 35% of HOKA revenue and growing 40%+ while US growth has decelerated to a still-healthy 22%.",
      "This is the classic Lynch setup: a brand whose category penetration story is observable on the street, with EPS growing 15–18% trading at 22x forward. Inventory days normalized last quarter after the late-2024 build-up that spooked the market.",
      "The bear thesis — HOKA is a sneaker fashion cycle that fades — is reasonable on its face but contradicted by the data. Cohort repurchase rates remain above 60% three years post-purchase. Athletes do not abandon a shoe that works. Fashion buyers do, but they are not the majority of the buyer mix.",
      "Position 8%. I will add on any pullback driven by quarterly comp noise that does not change the international penetration thesis.",
    ],
    numerics: [
      { label: "Forward P/E", value: "22x" },
      { label: "EPS CAGR (3y)", value: "+16%" },
      { label: "HOKA intl growth", value: "+41% YoY" },
      { label: "Net cash", value: "$2.1B" },
      { label: "Repurchase rate (3y)", value: "62%" },
      { label: "Position", value: "8%" },
    ],
  },
];

export const REPORTS_BY_PERSONA: Record<string, Report[]> = REPORTS.reduce(
  (acc, r) => {
    (acc[r.personaId] ||= []).push(r);
    return acc;
  },
  {} as Record<string, Report[]>
);
