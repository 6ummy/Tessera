// Mock persona chat engine.
// Picks a response based on keyword detection in the user's message, falling
// back to an in-character generic answer. Designed so the demo *feels* like
// chatting with each analyst without a real LLM call.
//
// Wire to Claude later by replacing `respond()` with an API call that sends
// the message + `personalities.md` system prompt + recent portfolio/reports.

import { PROPOSAL_BY_PERSONA } from "./proposals";
import { REPORTS_BY_PERSONA } from "./reports";

export type ChatMessage = {
  id: string;
  role: "user" | "analyst";
  content: string;
  ts: number;
};

// Greeting and starter suggestions per persona.
export const STARTERS: Record<string, { greeting: string; suggestions: string[] }> = {
  warren: {
    greeting:
      "Glad you stopped by. I'm Warren — I run a value book. Ask me about a business, a balance sheet, or why I'm holding so much cash. I'll be honest about what I don't know.",
    suggestions: [
      "Why is Costco still in your book at 48x?",
      "What would make you sell Berkshire?",
      "How much cash is too much cash?",
      "Are you worried about a recession?",
    ],
  },
  cathie: {
    greeting:
      "Hey — Cathie here. I cover AI compute, robotics, and crypto infrastructure. I think in 2030 P&Ls, not next quarter. Ask me what I think the world looks like in five years, or where I might be wrong.",
    suggestions: [
      "Walk me through your ASML thesis.",
      "Is Bitcoin a real asset class?",
      "How do you think about NVIDIA at this price?",
      "What's your bear case on AI?",
    ],
  },
  ray: {
    greeting:
      "Welcome. I'm Ray — I allocate across asset classes based on regime probabilities, not single-stock catalysts. Ask me about growth-inflation quadrants, real yields, or why I'm not getting excited about any particular forecast.",
    suggestions: [
      "What regime are we in right now?",
      "Why do you hold gold?",
      "Bonds-equity correlation — is it broken?",
      "How do you think about geopolitical risk?",
    ],
  },
  peter: {
    greeting:
      "Hey, Peter here. I run GARP — growth at a reasonable price. I find names by walking aisles and reading 10-Ks. Ask me about a stock, a sector, or the burrito shop you noticed had a line around the block.",
    suggestions: [
      "What's your add trigger on META?",
      "Are you avoiding turnarounds on purpose?",
      "Talk me through a recent thesis.",
      "What sectors are you tilting toward?",
    ],
  },
};

// Keyword → response bank per persona. First match wins.
type RuleSet = { match: RegExp; reply: (ctx: Ctx) => string }[];
type Ctx = { ticker?: string; personaId: string };

const VALUE_BANK: RuleSet = [
  {
    match: /cash|too much|sit\s*on/i,
    reply: () =>
      "Cash is a position. When nothing on the watchlist clears my bar, holding 4.8% yield is a perfectly reasonable parking spot. I won't redeploy until valuations come to me. Patience is a position too.",
  },
  {
    match: /recession|bear|crash|drawdown|correction/i,
    reply: () =>
      "I don't forecast macro. I underwrite businesses I'd be happy to own if the market closed for ten years. If a recession lets me buy Mastercard at 15x, that's a gift — not a problem to be solved.",
  },
  {
    match: /sell|exit|trim|reduce/i,
    reply: () =>
      "Three reasons I sell. One: the moat I thought I saw isn't there. Two: management started managing the stock instead of the business. Three: price became silly. I don't sell on quarterly noise.",
  },
  {
    match: /berkshire|brk/i,
    reply: () =>
      "Berkshire is in the book since 1986 and I've never sold a share. Diversified compounder with $180B in cash optionality and float at near-zero cost. The day they stop being disciplined about acquisitions is the day I rethink — and that's not today.",
  },
  {
    match: /costco|cost/i,
    reply: () =>
      "Costco at 48x looks rich until you decompose it. You're not buying a grocer. You're buying a 93% renewal-rate membership annuity attached to a working-capital-negative distribution engine. The merchandise runs at breakeven by design. Strip out memberships and the multiple stops looking crazy.",
  },
  {
    match: /ai\b|crypto|btc|bitcoin/i,
    reply: () =>
      "Not my circle of competence. I leave AI to Cathie and I leave crypto to people who can value it. I prefer businesses that have been earning money for thirty years over assets that need a story to justify their price.",
  },
  {
    match: /valuation|expensive|cheap|p\/e|pe ratio/i,
    reply: () =>
      "Price is what you pay; value is what you get. My bar is 6% free cash flow yield on conservative forward estimates. I'll size smaller when valuation is rich but business quality is exceptional, and I'll wait years for the chance to add.",
  },
  {
    match: /tech|technology/i,
    reply: () =>
      "I own Google. I understand search and YouTube and Cloud is now $50B run-rate. That counts as a business I can hold for ten years. The rest of tech I leave to people who can model 2030 P&Ls. I can barely model next year's.",
  },
];

const GROWTH_BANK: RuleSet = [
  {
    match: /asml/i,
    reply: () =>
      "Every chip below 3nm in the next decade gets patterned by an ASML machine — not most, all. High-NA EUV is the entire roadmap. Bookings are lumpy because the tools are $300M+ each; what matters is multi-year visibility, which extends to 2028. Base case: 22% revenue CAGR, margins expand to 36%, $58 EPS by 2028. At 17x that, you're paying for a structurally protected monopoly.",
  },
  {
    match: /nvda|nvidia/i,
    reply: () =>
      "Inference workload is roughly 10x the training market. CUDA moat survives the next two competitive cycles. I size at 16% because the asymmetry is still attractive — the bear case (China cuts orders) loses 30%, the bull (sovereign AI capex keeps compounding) doubles. That distribution is what I'm long.",
  },
  {
    match: /bitcoin|btc|crypto|coin\b/i,
    reply: () =>
      "Bitcoin is base-layer macro savings. I hold it personally and don't talk about it on podcasts. Coinbase is where it gets interesting on the equity side — USDC interest and Base sequencer fees are now ~$1.4B annualized, recurring and high-margin. If you're still modeling COIN as a function of trading volume, you're modeling 2021.",
  },
  {
    match: /tesla|tsla/i,
    reply: () =>
      "I own it for autonomy and energy storage, not for cars. The car business funds the optionality. If FSD generalizes the way the data suggests, the equity is worth several times today's price. If it doesn't, you still get a profitable EV maker. Asymmetric.",
  },
  {
    match: /bear|wrong|risk/i,
    reply: () =>
      "Every position has a written bear case before I size it. The asymmetry is in the bull, but discipline is in the bear. If my bear loses more than 90%, the position is too big — full stop.",
  },
  {
    match: /volatility|vol\b|drawdown|down/i,
    reply: () =>
      "Drawdowns under 25% are the price of compounding above market. I don't apologize for them. I re-underwrite the thesis quarterly; if it's intact, the drawdown doesn't matter. If it's broken, I cut fast.",
  },
  {
    match: /ai\b|artificial intelligence|llm/i,
    reply: () =>
      "AI is two civilization-scale platforms compounding simultaneously — training compute and inference distribution. I want to own the picks (NVDA, ASML, ANET), the rails (CRWD, PLTR), and the multimodal data businesses (TEM). I'm not trying to pick the winning model.",
  },
  {
    match: /pe ratio|p\/e|valuation/i,
    reply: () =>
      "Trailing P/E penalizes R&D investment, which is exactly what I want a company to be doing in the early innings. I think in 2027–2030 P&Ls. If you can't model that, the position isn't for you.",
  },
];

const MACRO_BANK: RuleSet = [
  {
    match: /regime|quadrant|goldilocks|stagflation/i,
    reply: () =>
      "This week the model assigns 46% to Goldilocks (growth ↑, inflation ↓), up 15pp from a month ago. Stagflation dropped to 14%. Drivers: PMI new orders crossed 52, wage growth decelerated to 3.4%. Allocation response is modest — equity tilt 38% → 42%. I don't predict the next CPI print; I position for the distribution.",
  },
  {
    match: /gold|gld/i,
    reply: () =>
      "Gold at 8% because central-bank buying is structurally elevated and negative correlation to real yields is restored. I hire gold to do exactly what it's doing right now. I'll trim if real yields rip above 3% and stay there for two quarters.",
  },
  {
    match: /bond|treasury|yield|duration|tlt|ief/i,
    reply: () =>
      "Six-week equity-Treasury correlation flipped from +0.4 to -0.2. That's the bigger news than the level of yields. The hedge is working again. I'm sizing duration to its historical role rather than the broken 2022-2023 behavior. Expect MDD to compress over the next 12 months if this holds.",
  },
  {
    match: /recession|growth/i,
    reply: () =>
      "Growth is currently above-trend and moderating. My deflation quadrant probability is 14%. I don't bet on recessions; I make sure I'm not destroyed if one shows up. That's a different discipline.",
  },
  {
    match: /inflation|cpi|prices/i,
    reply: () =>
      "Inflation is the dominant macro variable when it's surprising. Right now it isn't — breakevens are below long-run trend. TIPS at 10% gives me cheap insurance against an energy or wage reacceleration. I'd rather pay the carry and not need it than be naked if it returns.",
  },
  {
    match: /china|geopolitic|war|risk/i,
    reply: () =>
      "Geopolitical shocks are not in any model I've built. They are the reason I keep 8% in gold, 18% in intermediate Treasuries, and refuse to run leverage. I'd rather give up 100 bps of expected return than be on the wrong side of an event nobody could have priced.",
  },
  {
    match: /stock|equity|ticker/i,
    reply: () =>
      "I don't pick individual stocks. That's Warren's, Cathie's, and Peter's job. I allocate across asset classes. If you want a name, ask one of them; if you want regime exposure, that's my desk.",
  },
];

const GARP_BANK: RuleSet = [
  {
    match: /add trigger|add\b/i,
    reply: () =>
      "Every position has a pre-committed add trigger and a trim trigger. On META, I add on a pullback toward $410 absent a thesis break. On ANET, I add toward $280. Without those numbers written down before the trade, you'll second-guess yourself when it matters.",
  },
  {
    match: /meta|facebook/i,
    reply: () =>
      "EPS growing 20%+ at sub-20x. Reels monetization is closing the gap to feed and AI capex is starting to pay back in ad targeting. Classic GARP setup — I'm not paying for hope, I'm paying for a multiple roughly flat to the index against double-digit EPS growth.",
  },
  {
    match: /arista|anet/i,
    reply: () =>
      "Best-in-class Ethernet switching for hyperscalers, and AI back-end networking is a brand-new buyer category that just tripled their TAM. PEG of 1.1, op margin 41% and expanding, net cash. Position 11% — would size higher on any pullback driven by capex noise that doesn't change the thesis.",
  },
  {
    match: /turnaround|cheap stock|distressed/i,
    reply: () =>
      "I avoid turnarounds on purpose. Catching falling knives is somebody else's job. I want businesses already compounding, not businesses where I'm betting on management changing the trajectory. Costs me upside occasionally; saves me a lot of stop-losses.",
  },
  {
    match: /peg|pe ratio|valuation/i,
    reply: () =>
      "PEG below 1.2 on credible forward EPS estimates. If a name is at 1.5 I want acceleration to justify it, and I write down what acceleration looks like and when I'll re-underwrite. PEG > 2 with no acceleration signal is a trim, no exceptions.",
  },
  {
    match: /sector|consumer|tech|industrial/i,
    reply: () =>
      "Sector tilt right now: consumer (HOKA international, Booking direct mix) + industrial (URI mega-projects, LRCX memory recovery) + a tech sleeve (META, ANET, TSM). Sector cap stays at 35% — I'll cut before I let any single sector dominate.",
  },
  {
    match: /sale|trim|sell/i,
    reply: () =>
      "Trim trigger is deceleration — two quarters of decelerating EPS growth without a clear one-off explanation. Or PEG drifting above 1.8. I'd rather give up the last 20% of a winner than ride a former winner all the way down.",
  },
  {
    match: /walk|store|aisle/i,
    reply: () =>
      "Every weekend I'm in three stores I haven't been to. Last month: a Korean grocery in Allston, a new climbing gym in Somerville, a Costco. You learn more about consumer businesses by standing in the aisle than by reading the 10-K. Both matter — but the 10-K confirms; the aisle initiates.",
  },
];

const BANKS: Record<string, RuleSet> = {
  warren: VALUE_BANK,
  cathie: GROWTH_BANK,
  ray: MACRO_BANK,
  peter: GARP_BANK,
};

// Generic fallbacks per persona — used when no keyword matches.
const FALLBACK: Record<string, string[]> = {
  warren: [
    "Tell me which business you're thinking about and I'll tell you whether I understand it. If I don't, I pass — and you should probably ask Cathie or Peter.",
    "Specifics help. A ticker, a balance sheet item, a question about management. I'm not great at generalities — I'm a one-business-at-a-time investor.",
  ],
  cathie: [
    "What time horizon are you thinking about? I write 2027–2030 P&Ls; if you need a six-month call, you want Peter, not me.",
    "Throw a specific name or theme at me — AI compute, on-chain infra, robotics, genomics — and I'll tell you what I'd want to be paid to underwrite the bull case.",
  ],
  ray: [
    "Be more specific about the regime question — growth, inflation, real yields, correlation, gold? I don't have an opinion on single names; that's not my book.",
    "If you want a stock pick, ask Warren, Cathie, or Peter. If you want to know what asset class I'd be tilted toward this quarter, I can answer.",
  ],
  peter: [
    "What's the name? I can walk you through the GARP screen and tell you what would have me adding or trimming. Generic market chat isn't really my thing.",
    "If you've seen a line out the door at a place this week and want to know if there's a ticker behind it — that's exactly the right question to ask me.",
  ],
};

export function respond(personaId: string, userMessage: string): string {
  const bank = BANKS[personaId] || [];
  const msg = userMessage.trim();
  for (const rule of bank) {
    if (rule.match.test(msg)) {
      return rule.reply({ personaId });
    }
  }
  // Light context: occasionally drop a portfolio name to feel grounded
  const proposal = PROPOSAL_BY_PERSONA[personaId];
  const reports = REPORTS_BY_PERSONA[personaId] ?? [];
  const generic = FALLBACK[personaId] ?? ["Tell me more."];
  const pick = generic[Math.floor(Math.random() * generic.length)];
  if (proposal?.positions[0] && msg.length < 40) {
    return `${pick} For reference, the biggest active position in the book right now is ${proposal.positions[0].ticker} at ${(proposal.positions[0].weight * 100).toFixed(0)}%${reports[0] ? `; I wrote about it on ${reports[0].date}.` : "."}`;
  }
  return pick;
}
