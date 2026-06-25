// Greeting + starter prompts per persona.
//
// Display-only — never sent to the LLM, never claims to be real analyst
// output. Lives outside `lib/mock/` so it survives the eventual mock
// purge: even with the real chat backend, fresh sessions still need a
// friendly opener + a few suggested questions to scaffold the
// conversation.

export type ChatMessage = {
  id: string;
  role: "user" | "analyst";
  content: string;
  ts: number;
};

export const STARTERS: Record<
  string,
  { greeting: string; suggestions: string[] }
> = {
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
  michael: {
    greeting:
      "Michael here — I'm the bear at the table. I sit in cash and gold and only press a hedge when the bubble signal actually fires: a fast run-up paired with a collapsing free-cash-flow yield. No shorts, no leverage — just inverse ETFs, sized small and held briefly. Ask me what's overpriced, where the leverage is hiding, or why I'm not more bearish.",
    suggestions: [
      "What's flashing a bubble signal right now?",
      "Why inverse ETFs instead of shorting outright?",
      "How much cash are you holding, and why?",
      "What would make you cover the hedges?",
    ],
  },
};
