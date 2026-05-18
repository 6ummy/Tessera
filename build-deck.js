// Tessera — technical presentation for AI study team
// Run: node build-deck.js
const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 × 7.5 inch
pres.author = "Tessera";
pres.title = "Tessera — a multi-agent LLM research desk (technical)";

// ─────────── Claude design palette ───────────
const C = {
  cream100: "F5F4EE",
  cream50: "FAF9F5",
  cream200: "EDEBE0",
  ink900: "1F1E1B",
  ink800: "2A2925",
  ink700: "3D3B36",
  ink600: "5A5751",
  ink500: "7C7870",
  ink400: "A8A39A",
  ink300: "C9C5BC",
  coral500: "D97757",
  coral600: "C2613F",
  coral50: "FBF1ED",
  sage500: "6B8E6B",
  plum500: "8B6B8E",
  codeBg: "1A1815",
  codeKey: "E89B7E",
  codeStr: "8CA68C",
  codeVal: "EDEBE0",
};

const FONT = {
  serif: "Georgia",
  sans: "Calibri",
  mono: "Consolas",
};

const W = 13.3, H = 7.5;
const TOTAL = 17;

const personaPhoto = (id) => path.join(__dirname, "apps", "web", "public", "personas", `${id}.jpg`);

const eyebrow = (slide, text, x = 0.6, y = 0.6) =>
  slide.addText(text, {
    x, y, w: 8, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600,
    bold: true, charSpacing: 4, margin: 0,
  });

const slideTitle = (slide, parts) =>
  slide.addText(parts, {
    x: 0.6, y: 1.0, w: 12.2, h: 1.0,
    fontFace: FONT.serif, fontSize: 32, charSpacing: -1, margin: 0,
  });

const pageNum = (slide, n) =>
  slide.addText(`${String(n).padStart(2, "0")} / ${String(TOTAL).padStart(2, "0")}`, {
    x: 12.4, y: 7.1, w: 0.7, h: 0.25,
    fontFace: FONT.mono, fontSize: 9, color: C.ink400, align: "right", margin: 0,
  });

const footerBrand = (slide, dark = false) =>
  slide.addText("Tessera · technical deck", {
    x: 0.6, y: 7.1, w: 4, h: 0.25,
    fontFace: FONT.serif, italic: true, fontSize: 10,
    color: dark ? C.ink400 : C.ink500, margin: 0,
  });

const cardShadow = () => ({
  type: "outer", color: "1F1E1B", blur: 18, offset: 4, angle: 90, opacity: 0.06,
});

const card = (slide, x, y, w, h, opts = {}) => {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: opts.fill || C.cream50 },
    line: { color: C.ink900, width: 0.5, transparency: 92 },
    shadow: cardShadow(),
  });
};

const codeBlock = (slide, x, y, w, h, lines) => {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: C.codeBg }, line: { color: C.codeBg },
  });
  slide.addText(lines, {
    x: x + 0.25, y: y + 0.2, w: w - 0.5, h: h - 0.3,
    fontFace: FONT.mono, fontSize: 11, color: C.cream100,
    valign: "top", margin: 0,
  });
};

// ═══════════════════════════════════════════════════════
// SLIDE 1 — TITLE
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };

  // Mosaic motif
  const tiles = [
    [11.2, 0.6, C.coral500], [11.85, 0.6, C.cream200], [12.5, 0.6, C.cream200],
    [11.2, 1.25, C.cream200], [11.85, 1.25, C.ink900], [12.5, 1.25, C.cream200],
    [11.2, 1.9, C.cream200], [11.85, 1.9, C.cream200], [12.5, 1.9, C.sage500],
  ];
  tiles.forEach(([x, y, c]) =>
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.55, h: 0.55, fill: { color: c }, line: { color: c } })
  );

  s.addText("Tessera", {
    x: 0.6, y: 0.7, w: 6, h: 0.5,
    fontFace: FONT.serif, fontSize: 22, italic: true, color: C.ink900, margin: 0,
  });

  s.addText("TECHNICAL DECK · AI STUDY GROUP · 2026", {
    x: 0.6, y: 2.5, w: 12, h: 0.4,
    fontFace: FONT.sans, fontSize: 12, color: C.coral600,
    bold: true, charSpacing: 4, margin: 0,
  });

  s.addText([
    { text: "A multi-agent LLM\n", options: { color: C.ink900 } },
    { text: "research desk ", options: { color: C.coral600, italic: true } },
    { text: "for long-term\ninvesting.", options: { color: C.ink900 } },
  ], {
    x: 0.6, y: 3.0, w: 12, h: 3.0,
    fontFace: FONT.serif, fontSize: 60, charSpacing: -2, margin: 0,
  });

  s.addText("How we built it: data ingestion · feature computation · " +
    "persona spec design · LLM pipeline · risk gateway · " +
    "brokerage integration · compliance.", {
    x: 0.6, y: 6.2, w: 11, h: 0.6,
    fontFace: FONT.sans, fontSize: 14, color: C.ink600, margin: 0,
  });

  s.addText("github.com/6ummy/Tessera", {
    x: 0.6, y: 7.1, w: 6, h: 0.3,
    fontFace: FONT.mono, fontSize: 10, color: C.ink400, margin: 0,
  });
}

// ═══════════════════════════════════════════════════════
// SLIDE 2 — AGENDA
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "AGENDA");
  slideTitle(s, [{ text: "Eight things ", options: { color: C.ink900 } }, { text: "to walk through.", options: { color: C.ink700, italic: true } }]);

  const items = [
    { n: "01", t: "System architecture", d: "Three planes: data, agents, decision/execution. Why this split." },
    { n: "02", t: "Stack", d: "Vercel · Firebase · Cloud Run · Neon · Anthropic · Alpaca. Why each." },
    { n: "03", t: "Data ingestion", d: "EOD prices, fundamentals, macro, news. APIs, frequency, storage shape." },
    { n: "04", t: "Hallucination defense", d: "The single most important design choice: LLMs never compute numbers." },
    { n: "05", t: "Persona spec design", d: "Anatomy of a system prompt. What goes in, what's forbidden." },
    { n: "06", t: "Same data, four readings", d: "How four personas interpret one earnings release differently." },
    { n: "07", t: "LLM call pipeline", d: "Haiku screen → Sonnet thesis → Pydantic validate → citation check." },
    { n: "08", t: "Execution + compliance", d: "Alpaca OAuth, paper/live flag, kill switch, US regulatory posture." },
  ];
  // 4 cols × 2 rows fits comfortably above the footer
  const colW = 2.95, colH = 2.05, gap = 0.2;
  items.forEach((it, i) => {
    const col = i % 4, row = Math.floor(i / 4);
    const x = 0.6 + col * (colW + gap);
    const y = 2.5 + row * (colH + 0.25);
    card(s, x, y, colW, colH);
    s.addText(it.n, {
      x: x + 0.3, y: y + 0.25, w: 1.0, h: 0.4,
      fontFace: FONT.mono, fontSize: 14, color: C.coral500, margin: 0,
    });
    s.addText(it.t, {
      x: x + 0.3, y: y + 0.65, w: colW - 0.6, h: 0.5,
      fontFace: FONT.serif, fontSize: 16, color: C.ink900, margin: 0,
    });
    s.addText(it.d, {
      x: x + 0.3, y: y + 1.15, w: colW - 0.6, h: 0.85,
      fontFace: FONT.sans, fontSize: 10, color: C.ink600, margin: 0,
    });
  });
  footerBrand(s); pageNum(s, 2);
}

// ═══════════════════════════════════════════════════════
// SLIDE 3 — SYSTEM ARCHITECTURE
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "01 · SYSTEM ARCHITECTURE");
  slideTitle(s, [{ text: "Three planes. ", options: { color: C.ink900 } }, { text: "Strict one-way flow.", options: { color: C.ink700, italic: true } }]);

  // Plane stack
  const planes = [
    {
      name: "DATA PLANE", color: C.sage500,
      what: "Ingest · normalize · store · embed",
      items: ["Alpaca WS / Coinbase WS (EOD)", "FMP, SEC EDGAR (fundamentals, filings)", "FRED (macro)", "NewsAPI, Reddit, X (text)"],
    },
    {
      name: "AGENT PLANE", color: C.coral500,
      what: "Read features · write theses · in parallel",
      items: ["Warren · Cathie · Ray · Peter (Anthropic Claude)", "Haiku 4.5 first pass → Sonnet 4.6 thesis", "Pydantic schema validation", "pgvector recall of prior theses"],
    },
    {
      name: "DECISION + EXECUTION PLANE", color: C.plum500,
      what: "Validate · enforce risk · execute",
      items: ["Quant validator (ticker exists, schema valid)", "Risk gateway (deterministic Python, caps + VaR)", "Paper engine (default) / Alpaca live (flagged)", "Ledger writes + Firestore fan-out to UI"],
    },
  ];

  const py = 2.4, ph = 1.45, pgap = 0.18;
  planes.forEach((p, i) => {
    const y = py + i * (ph + pgap);
    card(s, 0.6, y, 12.1, ph);
    // accent bar on left
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y, w: 0.08, h: ph,
      fill: { color: p.color }, line: { color: p.color },
    });
    s.addText(p.name, {
      x: 0.9, y: y + 0.2, w: 5, h: 0.3,
      fontFace: FONT.sans, fontSize: 10, color: p.color, bold: true, charSpacing: 3, margin: 0,
    });
    s.addText(p.what, {
      x: 0.9, y: y + 0.5, w: 4.5, h: 0.4,
      fontFace: FONT.serif, italic: true, fontSize: 14, color: C.ink800, margin: 0,
    });
    // 4 items as 2x2 chips on the right
    p.items.forEach((it, j) => {
      const col = j % 2, row = Math.floor(j / 2);
      s.addText(`· ${it}`, {
        x: 5.6 + col * 3.6, y: y + 0.25 + row * 0.5, w: 3.5, h: 0.4,
        fontFace: FONT.mono, fontSize: 10, color: C.ink700, margin: 0,
      });
    });
  });

  // Bottom note
  s.addText("Data only flows downward. Each plane reads the one above, writes to its own store. " +
    "No backward calls — keeps failures isolated and pipeline replayable.", {
    x: 0.6, y: 7.05, w: 12, h: 0.4,
    fontFace: FONT.sans, italic: true, fontSize: 11, color: C.ink500, margin: 0,
  });
  pageNum(s, 3);
}

// ═══════════════════════════════════════════════════════
// SLIDE 4 — STACK
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "02 · STACK");
  slideTitle(s, [{ text: "Boring choices ", options: { color: C.ink900 } }, { text: "on purpose.", options: { color: C.ink700, italic: true } }]);

  const groups = [
    { g: "Frontend", items: [
      ["Next.js 14 App Router", "RSC + server actions + streaming"],
      ["Vercel", "Zero-config deploy, US region, free tier"],
      ["Tailwind + Radix", "Claude-design palette, primitives only"],
      ["Recharts", "Deterministic charts, React-native"],
    ]},
    { g: "Auth + realtime", items: [
      ["Firebase Auth", "Google/Apple SSO, no custom auth code"],
      ["Firestore", "Client subscriptions for fan-out to UI"],
      ["FCM", "Push alerts on rebalance / new portfolio"],
    ]},
    { g: "Agents + batch", items: [
      ["Google Cloud Run Jobs", "Scale-to-zero, 60-min jobs, same GCP as Firebase"],
      ["LangGraph (LangChain)", "Agent state machine + retries"],
      ["Anthropic Claude API", "Haiku 4.5 · Sonnet 4.6 · Opus 4.7"],
    ]},
    { g: "Data + state", items: [
      ["Neon Postgres", "Serverless, Vercel-friendly branching"],
      ["TimescaleDB extension", "OHLCV hypertables, continuous aggregates"],
      ["pgvector", "Persona memory recall (embedding similarity)"],
    ]},
    { g: "Brokerage", items: [
      ["Alpaca", "US stocks + crypto, single API, paper/live flag"],
      ["OAuth flow only", "We never touch user broker credentials"],
    ]},
    { g: "Ops", items: [
      ["Sentry", "Errors + LLM call traces"],
      ["Grafana Cloud free", "LLM cost dashboard, ingestor health"],
    ]},
  ];

  const colW = 4.05, colH = 2.25, gap = 0.2;
  groups.forEach((g, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = 0.6 + col * (colW + gap);
    const y = 2.4 + row * (colH + gap);
    card(s, x, y, colW, colH);
    s.addText(g.g.toUpperCase(), {
      x: x + 0.3, y: y + 0.2, w: colW - 0.6, h: 0.3,
      fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
    });
    g.items.forEach((it, j) => {
      const iy = y + 0.55 + j * 0.4;
      s.addText(it[0], {
        x: x + 0.3, y: iy, w: colW - 0.6, h: 0.22,
        fontFace: FONT.mono, fontSize: 10, color: C.ink900, margin: 0,
      });
      s.addText(it[1], {
        x: x + 0.3, y: iy + 0.2, w: colW - 0.6, h: 0.2,
        fontFace: FONT.sans, fontSize: 9, color: C.ink500, italic: true, margin: 0,
      });
    });
  });

  footerBrand(s); pageNum(s, 4);
}

// ═══════════════════════════════════════════════════════
// SLIDE 5 — DATA INGESTION
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "03 · DATA INGESTION");
  slideTitle(s, [{ text: "Long-term means ", options: { color: C.ink900 } }, { text: "fundamentals dominate.", options: { color: C.ink700, italic: true } }]);

  // Source table
  const rows = [
    ["SOURCE", "API", "WHAT WE PULL", "FREQ", "STORE"],
    ["Alpaca", "alpaca.markets/v2/stocks/bars", "EOD OHLCV, US equities + ETFs", "daily", "ohlcv_1d"],
    ["Coinbase", "api.exchange.coinbase.com", "EOD candles, BTC/ETH/major alts", "daily", "ohlcv_1d"],
    ["Financial Modeling Prep", "fmp.api/financials", "Income / balance / cash flow, 5 yrs", "quarterly", "fundamentals"],
    ["SEC EDGAR", "data.sec.gov/submissions", "10-K, 10-Q, 8-K full text", "as filed", "filings + GCS"],
    ["FRED", "stlouisfed.org/api", "Yields, CPI, employment, ~20 series", "as released", "macro_series"],
    ["NewsAPI", "newsapi.org/v2", "Ticker-tagged headlines + bodies", "hourly batch", "news + embedding"],
    ["Reddit (PRAW)", "reddit.com/r/{stocks,wallstreetbets}", "Top posts per ticker for sentiment", "hourly batch", "social + embedding"],
  ];

  const tx = 0.6, ty = 2.4, tw = 12.1;
  const colW = [1.6, 3.3, 4.0, 1.2, 1.7];
  rows.forEach((row, i) => {
    const y = ty + i * 0.5;
    const isHeader = i === 0;
    if (isHeader) {
      s.addShape(pres.shapes.RECTANGLE, {
        x: tx, y, w: tw, h: 0.5,
        fill: { color: C.ink900 }, line: { color: C.ink900 },
      });
    } else if (i % 2 === 0) {
      s.addShape(pres.shapes.RECTANGLE, {
        x: tx, y, w: tw, h: 0.5,
        fill: { color: C.cream50 }, line: { color: C.cream50 },
      });
    }
    let cx = tx + 0.2;
    row.forEach((cell, j) => {
      s.addText(cell, {
        x: cx, y, w: colW[j] - 0.2, h: 0.5,
        fontFace: j >= 1 && !isHeader ? FONT.mono : FONT.sans,
        fontSize: isHeader ? 10 : 11,
        color: isHeader ? C.coral500 : C.ink800,
        bold: isHeader,
        charSpacing: isHeader ? 2 : 0,
        valign: "middle", margin: 0,
      });
      cx += colW[j];
    });
  });

  s.addText("All raw rows preserved. Pre-computed features (returns, RSI, FCF yield, PEG, regime probabilities) " +
    "live in a separate ticker_features table that the LLM reads instead.", {
    x: 0.6, y: 6.4, w: 12, h: 0.6,
    fontFace: FONT.sans, italic: true, fontSize: 11, color: C.ink500, margin: 0,
  });

  footerBrand(s); pageNum(s, 5);
}

// ═══════════════════════════════════════════════════════
// SLIDE 6 — HALLUCINATION DEFENSE (the core design)
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "04 · HALLUCINATION DEFENSE");
  slideTitle(s, [{ text: "LLMs write theses. ", options: { color: C.ink900 } }, { text: "Code computes numbers.", options: { color: C.coral600, italic: true } }]);

  // Left: bad pattern, Right: our pattern
  const colY = 2.4, colW = 5.95, colH = 4.5;

  // BAD
  card(s, 0.6, colY, colW, colH);
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: colY, w: colW, h: 0.5,
    fill: { color: C.coral500 }, line: { color: C.coral500 },
  });
  s.addText("✗  NAIVE PATTERN", {
    x: 0.85, y: colY + 0.1, w: colW - 0.5, h: 0.3,
    fontFace: FONT.sans, fontSize: 11, color: C.cream100, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText("LLM reads raw data, computes signals, decides weights.", {
    x: 0.85, y: colY + 0.65, w: colW - 0.5, h: 0.5,
    fontFace: FONT.serif, italic: true, fontSize: 14, color: C.ink800, margin: 0,
  });
  codeBlock(s, 0.85, colY + 1.3, colW - 0.5, 1.6, [
    { text: 'prompt = f"Here is AAPL\'s last 30 days:\\n{ohlcv_csv}\\n\\n', options: { color: C.codeVal, breakLine: true } },
    { text: 'What is its momentum? Allocate 0–20% if bullish."', options: { color: C.codeVal, breakLine: true } },
    { text: '', options: { breakLine: true } },
    { text: '→ model invents ret_30d = +12% (actual: −3%)', options: { color: C.codeKey, breakLine: true } },
    { text: '→ recommends 18% AAPL on hallucinated signal', options: { color: C.codeKey } },
  ]);
  s.addText("Risks: invented numbers, wrong tickers, fabricated citations, " +
    "weights that violate risk policy — all reach production.", {
    x: 0.85, y: colY + 3.05, w: colW - 0.5, h: 1.2,
    fontFace: FONT.sans, fontSize: 11, color: C.ink600, margin: 0,
  });

  // GOOD
  card(s, 6.85, colY, colW, colH);
  s.addShape(pres.shapes.RECTANGLE, {
    x: 6.85, y: colY, w: colW, h: 0.5,
    fill: { color: C.sage500 }, line: { color: C.sage500 },
  });
  s.addText("✓  TESSERA PATTERN", {
    x: 7.1, y: colY + 0.1, w: colW - 0.5, h: 0.3,
    fontFace: FONT.sans, fontSize: 11, color: C.cream100, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText("Python computes the numbers. LLM only interprets.", {
    x: 7.1, y: colY + 0.65, w: colW - 0.5, h: 0.5,
    fontFace: FONT.serif, italic: true, fontSize: 14, color: C.ink800, margin: 0,
  });
  codeBlock(s, 7.1, colY + 1.3, colW - 0.5, 1.6, [
    { text: 'features = compute_features("AAPL")  # pandas', options: { color: C.codeVal, breakLine: true } },
    { text: '# {ret_30d: -0.031, rsi: 42, fcf_yield: 0.041,', options: { color: C.codeStr, breakLine: true } },
    { text: '#  peg: 1.8, pe_fwd: 28.2, ...}', options: { color: C.codeStr, breakLine: true } },
    { text: '', options: { breakLine: true } },
    { text: 'prompt = f"{persona_spec}\\nFeatures: {features}\\n', options: { color: C.codeVal, breakLine: true } },
    { text: 'Write thesis. Output JSON per schema."', options: { color: C.codeVal } },
  ]);
  s.addText("LLM gets pre-validated numbers. Its only freedom is the *narrative*. " +
    "Wrong tickers and fake citations are rejected downstream.", {
    x: 7.1, y: colY + 3.05, w: colW - 0.5, h: 1.2,
    fontFace: FONT.sans, fontSize: 11, color: C.ink600, margin: 0,
  });

  footerBrand(s); pageNum(s, 6);
}

// ═══════════════════════════════════════════════════════
// SLIDE 7 — PERSONA SPEC ANATOMY
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "05 · PERSONA SPEC DESIGN");
  slideTitle(s, [{ text: "Each persona = ", options: { color: C.ink900 } }, { text: "a tightly-specified prompt.", options: { color: C.ink700, italic: true } }]);

  // Left: anatomy diagram, Right: code excerpt
  const colY = 2.4;

  // Left labels
  const labels = [
    { t: "IDENTITY", d: "Name, archetype, background, lens" },
    { t: "MENTAL MODEL", d: "The deterministic framework the persona applies (e.g. Warren's 4-question filter)" },
    { t: "INPUTS", d: "Schema of pre-computed features the persona will receive" },
    { t: "VOICE RULES", d: "Required style, banned words, formatting constraints" },
    { t: "HARD RULES", d: "Behaviors that can never be violated (e.g. 'never propose without `what_would_make_me_wrong`')" },
    { t: "OUTPUT SCHEMA", d: "Pydantic-validated JSON shape, every field typed" },
  ];
  labels.forEach((l, i) => {
    const y = colY + i * 0.72;
    s.addShape(pres.shapes.OVAL, {
      x: 0.6, y: y + 0.08, w: 0.18, h: 0.18,
      fill: { color: C.coral500 }, line: { color: C.coral500 },
    });
    s.addText(l.t, {
      x: 0.95, y, w: 5.4, h: 0.3,
      fontFace: FONT.sans, fontSize: 11, color: C.ink900, bold: true, charSpacing: 2, margin: 0,
    });
    s.addText(l.d, {
      x: 0.95, y: y + 0.3, w: 5.4, h: 0.4,
      fontFace: FONT.sans, fontSize: 10, color: C.ink600, italic: true, margin: 0,
    });
  });

  // Right: code excerpt of Warren's hard rules
  codeBlock(s, 6.85, colY, 5.85, 4.5, [
    { text: '# warren.system.md (excerpt)', options: { color: C.codeStr, breakLine: true } },
    { text: '', options: { breakLine: true } },
    { text: 'VOICE:', options: { color: C.codeKey, breakLine: true } },
    { text: '- Plainspoken Midwestern. Period-heavy.', options: { breakLine: true } },
    { text: '- Banned: "asymmetric", "disruptive", "TAM",', options: { breakLine: true } },
    { text: '  "compelling", "narrative", emojis.', options: { breakLine: true } },
    { text: '', options: { breakLine: true } },
    { text: 'HARD RULES:', options: { color: C.codeKey, breakLine: true } },
    { text: '- Every proposal MUST include', options: { breakLine: true } },
    { text: '  `what_would_make_me_wrong`.', options: { breakLine: true } },
    { text: '- No 5-year hold case → no position.', options: { breakLine: true } },
    { text: '- single_name_weight <= 0.18', options: { breakLine: true } },
    { text: '', options: { breakLine: true } },
    { text: 'OUTPUT (Pydantic):', options: { color: C.codeKey, breakLine: true } },
    { text: 'class Proposal(BaseModel):', options: { breakLine: true } },
    { text: '    ticker: str   # must exist in universe', options: { breakLine: true } },
    { text: '    target_weight: float = Field(ge=0, le=0.18)', options: { breakLine: true } },
    { text: '    horizon_days: int = Field(ge=1825)', options: { breakLine: true } },
    { text: '    cited_news_ids: list[UUID]', options: { breakLine: true } },
    { text: '    what_would_make_me_wrong: list[str]', options: {} },
  ]);

  s.addText("Full specs (~600 lines each) live in personalities.md and are versioned with the codebase.", {
    x: 0.6, y: 7.05, w: 12, h: 0.4,
    fontFace: FONT.sans, italic: true, fontSize: 11, color: C.ink500, margin: 0,
  });
  pageNum(s, 7);
}

// ═══════════════════════════════════════════════════════
// SLIDE 8 — FOUR PERSONAS COMPARISON
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "06 · THE FOUR LENSES");
  slideTitle(s, [{ text: "Same market data. ", options: { color: C.ink900 } }, { text: "Four different filters.", options: { color: C.ink700, italic: true } }]);

  const personas = ["warren", "cathie", "ray", "peter"];
  const personaNames = ["Warren", "Cathie", "Ray", "Peter"];
  const accents = [C.ink900, C.coral500, C.plum500, C.sage500];

  // Top row: persona headers with mini photos
  const phY = 2.3, cellW = 2.5;
  const headerOffset = 2.5;
  personas.forEach((p, i) => {
    const x = headerOffset + 0.3 + i * cellW;
    s.addImage({
      path: personaPhoto(p),
      x, y: phY, w: 0.7, h: 0.7,
      rounding: true, sizing: { type: "cover", w: 0.7, h: 0.7 },
    });
    s.addShape(pres.shapes.OVAL, {
      x: x + 0.8, y: phY + 0.25, w: 0.12, h: 0.12,
      fill: { color: accents[i] }, line: { color: accents[i] },
    });
    s.addText(personaNames[i], {
      x: x + 0.95, y: phY + 0.05, w: cellW - 1.0, h: 0.4,
      fontFace: FONT.serif, fontSize: 18, color: C.ink900, margin: 0,
    });
    s.addText(["Value · 67", "Disruptive · 32", "Macro · 58", "GARP · 44"][i], {
      x: x + 0.95, y: phY + 0.4, w: cellW - 1.0, h: 0.3,
      fontFace: FONT.sans, fontSize: 9, color: C.ink500, charSpacing: 2, margin: 0,
    });
  });

  // Comparison rows
  const rows = [
    ["KEY METRIC",      "FCF yield > 6%",       "Bear/base/bull on 2030 P&L",  "Regime probabilities",        "PEG < 1.2 + EPS CAGR 15–25%"],
    ["HOLDING",         "7–12 names, < 15% TO", "15–25 names, 60–90% TO",      "8–14 ETFs, 25–40% TO",        "12–20 names, 25–40% TO"],
    ["HORIZON",         "5+ years",             "3–5 years",                   "Continuous rebalance",        "2–4 years"],
    ["TIME-FRAME LLM SEES", "5y financials",   "5y growth + scenarios",       "Real yields + macro factors", "3y EPS + observability"],
    ["IGNORES",         "Macro, momentum, IPOs", "Trailing P/E, gross margin", "Single stocks, sentiment",    "Turnarounds, story stocks"],
    ["MAX SINGLE NAME", "18%",                  "16%",                         "35% (broad equity)",          "13%"],
  ];

  const ty = 3.3, rowH = 0.6;
  rows.forEach((row, i) => {
    const y = ty + i * rowH;
    if (i % 2 === 1) {
      s.addShape(pres.shapes.RECTANGLE, {
        x: 0.6, y, w: 12.1, h: rowH,
        fill: { color: C.cream50 }, line: { color: C.cream50 },
      });
    }
    // label col
    s.addText(row[0], {
      x: 0.7, y, w: headerOffset - 0.2, h: rowH,
      fontFace: FONT.sans, fontSize: 9, color: C.ink500, bold: true, charSpacing: 2, valign: "middle", margin: 0,
    });
    // 4 persona cols
    for (let j = 1; j <= 4; j++) {
      s.addText(row[j], {
        x: headerOffset + 0.3 + (j - 1) * cellW, y, w: cellW - 0.2, h: rowH,
        fontFace: FONT.mono, fontSize: 10, color: C.ink800, valign: "middle", margin: 0,
      });
    }
  });

  footerBrand(s); pageNum(s, 8);
}

// ═══════════════════════════════════════════════════════
// SLIDE 9 — SAME DATA, FOUR READINGS (example)
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "06b · CONCRETE EXAMPLE");
  slideTitle(s, [{ text: "NVDA Q3 2026 release: ", options: { color: C.ink900 } }, { text: "the desk reads it.", options: { color: C.ink700, italic: true } }]);

  // Top: the input
  codeBlock(s, 0.6, 2.4, 12.1, 1.5, [
    { text: '# Feature snapshot sent to all four personas (identical):', options: { color: C.codeStr, breakLine: true } },
    { text: '{ ticker: "NVDA", price: 1240, ret_30d: +0.082, ret_1y: +0.34, fcf_yield: 0.018,', options: { breakLine: true } },
    { text: '  pe_fwd: 38, eps_cagr_3y: +0.42, gross_margin_yoy: -0.03, dc_revenue_yoy: +0.41,', options: { breakLine: true } },
    { text: '  inference_share_yoy: +0.55, capex_intensity: 0.21, peg: 0.9, news_sentiment_7d: +0.41 }', options: {} },
  ]);

  // 4 verdicts
  const verdicts = [
    { p: "warren", n: "Warren", a: C.ink900, v: "HOLD · 0%",
      r: "FCF yield 1.8% is half my bar. I can't underwrite a 5-year hold at this multiple. Watching only. Re-enter at FCF yield ≥ 5% or a 35%+ drawdown."  },
    { p: "cathie", n: "Cathie", a: C.coral500, v: "ADD · 14%",
      r: "Inference share +55% YoY validates the bull. Bear (sovereign capex pause) loses 30%; base earns 2.5x; bull 4x. Sizing to the asymmetry — adding 200bps."  },
    { p: "ray", n: "Ray", a: C.plum500, v: "N/A",
      r: "Single names aren't my desk. I'll note that AI capex strength keeps growth-quadrant probability elevated (+3pp this week), supporting equity tilt."  },
    { p: "peter", n: "Peter", a: C.sage500, v: "HOLD · 7%",
      r: "PEG of 0.9 looks GARP-ish but the gross margin yoy is decelerating. Add trigger: stable margin + EPS revision up next quarter. Trim trigger: two qtrs of margin contraction."  },
  ];

  const vY = 4.2, vW = 2.95, vH = 2.7, vGap = 0.18;
  verdicts.forEach((v, i) => {
    const x = 0.6 + i * (vW + vGap);
    card(s, x, vY, vW, vH);
    // Top row: photo + verdict
    s.addImage({
      path: personaPhoto(v.p),
      x: x + 0.3, y: vY + 0.3, w: 0.65, h: 0.65,
      rounding: true, sizing: { type: "cover", w: 0.65, h: 0.65 },
    });
    s.addText(v.n, {
      x: x + 1.05, y: vY + 0.3, w: vW - 1.2, h: 0.35,
      fontFace: FONT.serif, fontSize: 18, color: C.ink900, margin: 0,
    });
    s.addText(v.v, {
      x: x + 1.05, y: vY + 0.62, w: vW - 1.2, h: 0.3,
      fontFace: FONT.mono, fontSize: 12, color: v.a, bold: true, margin: 0,
    });
    s.addText(v.r, {
      x: x + 0.3, y: vY + 1.15, w: vW - 0.5, h: 1.5,
      fontFace: FONT.sans, fontSize: 11, color: C.ink700, margin: 0,
    });
  });

  footerBrand(s); pageNum(s, 9);
}

// ═══════════════════════════════════════════════════════
// SLIDE 10 — LLM CALL PIPELINE
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "07 · LLM CALL PIPELINE");
  slideTitle(s, [{ text: "Per persona, ", options: { color: C.ink900 } }, { text: "one batch per session.", options: { color: C.ink700, italic: true } }]);

  // Horizontal pipeline of 5 stages
  const stages = [
    { t: "1. Universe screen",   m: "Haiku 4.5",   d: "~500 tickers → top ~30 per persona", c: "$0.005" },
    { t: "2. Thesis writeup",    m: "Sonnet 4.6",  d: "Deep analysis on shortlist",          c: "$0.045" },
    { t: "3. Schema validate",   m: "Pydantic",    d: "Type + range checks, 1 retry",        c: "free" },
    { t: "4. Citation check",    m: "Python",      d: "Each cited news_id must resolve",     c: "free" },
    { t: "5. Risk gateway",      m: "Python",      d: "Weight caps, sector, VaR budget",     c: "free" },
  ];

  const py = 2.4, pH = 2.4, sW = (12.1 - 4 * 0.15) / 5;
  stages.forEach((st, i) => {
    const x = 0.6 + i * (sW + 0.15);
    card(s, x, py, sW, pH);
    s.addText(st.t, {
      x: x + 0.2, y: py + 0.25, w: sW - 0.4, h: 0.4,
      fontFace: FONT.serif, fontSize: 14, color: C.ink900, margin: 0,
    });
    // Tool chip
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: x + 0.2, y: py + 0.85, w: sW - 0.4, h: 0.4,
      fill: { color: C.ink900 }, line: { color: C.ink900 }, rectRadius: 0.05,
    });
    s.addText(st.m, {
      x: x + 0.2, y: py + 0.85, w: sW - 0.4, h: 0.4,
      fontFace: FONT.mono, fontSize: 10, color: C.cream100, align: "center", valign: "middle", margin: 0,
    });
    s.addText(st.d, {
      x: x + 0.2, y: py + 1.4, w: sW - 0.4, h: 0.6,
      fontFace: FONT.sans, fontSize: 10, color: C.ink600, margin: 0,
    });
    s.addText(`cost/call: ${st.c}`, {
      x: x + 0.2, y: py + 2.0, w: sW - 0.4, h: 0.3,
      fontFace: FONT.mono, fontSize: 9, color: C.coral600, margin: 0,
    });
  });

  // Aggregate math
  card(s, 0.6, 5.1, 12.1, 1.8);
  s.addText("DAILY MATH", {
    x: 0.85, y: 5.25, w: 4, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText("4 personas × 1 batch/day × (1 Haiku screen + ~20 Sonnet calls) ≈ 80 LLM calls/day", {
    x: 0.85, y: 5.55, w: 12, h: 0.4,
    fontFace: FONT.mono, fontSize: 12, color: C.ink800, margin: 0,
  });
  s.addText("• ~$1.20/day per persona thesis batch  ·  ~$1.50/day all-in including chat baseline", {
    x: 0.85, y: 5.95, w: 12, h: 0.4,
    fontFace: FONT.sans, fontSize: 12, color: C.ink700, margin: 0,
  });
  s.addText("• Prompt caching: persona spec (~3K tokens) cached at 0.1× cost across all calls within 5-min window", {
    x: 0.85, y: 6.3, w: 12, h: 0.4,
    fontFace: FONT.sans, fontSize: 12, color: C.ink700, margin: 0,
  });

  footerBrand(s); pageNum(s, 10);
}

// ═══════════════════════════════════════════════════════
// SLIDE 11 — RECOMMENDATION SURFACING
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "08 · SURFACING TO USER");
  slideTitle(s, [{ text: "Validated outputs ", options: { color: C.ink900 } }, { text: "stream to UI.", options: { color: C.ink700, italic: true } }]);

  // Horizontal flow diagram with 5 boxes
  const flow = [
    { t: "Cloud Run\nbatch job", c: C.ink900 },
    { t: "INSERT INTO\nanalyst_reports\n(Neon Postgres)", c: C.sage500 },
    { t: "Trigger fn\npushes to\nFirestore", c: C.plum500 },
    { t: "Firestore\nrealtime\nclient sub", c: C.coral500 },
    { t: "Browser re-renders\nportfolio cards\n(no refresh)", c: C.ink900 },
  ];

  // 5 boxes + 4 arrow gaps must fit in 12.1" of usable width
  const fy = 2.5, fH = 1.9, bW = 2.0, arrowW = 0.35;
  const fTotal = flow.length * bW + (flow.length - 1) * arrowW;  // 10 + 1.4 = 11.4
  const fStart = (W - fTotal) / 2;  // ≈ 0.95
  flow.forEach((f, i) => {
    const x = fStart + i * (bW + arrowW);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y: fy, w: bW, h: fH,
      fill: { color: C.cream50 },
      line: { color: f.c, width: 1.5 },
      rectRadius: 0.1,
    });
    s.addText(f.t, {
      x, y: fy, w: bW, h: fH,
      fontFace: FONT.sans, fontSize: 11, color: C.ink800, align: "center", valign: "middle", margin: 0.1,
    });
    // arrow to next
    if (i < flow.length - 1) {
      const ax = x + bW + 0.02;
      s.addShape(pres.shapes.LINE, {
        x: ax, y: fy + fH / 2, w: arrowW - 0.04, h: 0,
        line: { color: C.ink700, width: 1, endArrowType: "triangle" },
      });
    }
  });

  // What user sees
  card(s, 0.6, 5.0, 5.95, 1.8);
  s.addText("WHAT USER SEES IMMEDIATELY", {
    x: 0.85, y: 5.15, w: 5.5, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText("• 4 portfolios side-by-side on /proposals\n" +
    "• Hover any position → which analyst, what conviction\n" +
    "• Push notification on rebalance via FCM", {
    x: 0.85, y: 5.45, w: 5.5, h: 1.3,
    fontFace: FONT.sans, fontSize: 12, color: C.ink700, margin: 0, paraSpaceAfter: 4,
  });

  // What user can do
  card(s, 6.75, 5.0, 5.95, 1.8);
  s.addText("WHAT USER CAN DO", {
    x: 7.0, y: 5.15, w: 5.5, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText("• Follow a portfolio on paper (no money committed)\n" +
    "• Open chat with any analyst — discuss reasoning\n" +
    "• Phase F: opt-in live trading via Alpaca OAuth", {
    x: 7.0, y: 5.45, w: 5.5, h: 1.3,
    fontFace: FONT.sans, fontSize: 12, color: C.ink700, margin: 0, paraSpaceAfter: 4,
  });

  footerBrand(s); pageNum(s, 11);
}

// ═══════════════════════════════════════════════════════
// SLIDE 12 — CHAT FLOW
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "07b · CHAT WITH ANALYST");
  slideTitle(s, [{ text: "System prompt assembled ", options: { color: C.ink900 } }, { text: "per turn.", options: { color: C.ink700, italic: true } }]);

  // Left: assembly diagram
  const parts = [
    { l: "PERSONA SPEC", d: "Loaded from personalities.md (cached)", h: "~3K tok" },
    { l: "CURRENT BOOK", d: "JSON of persona's holdings (today)",     h: "~600 tok" },
    { l: "RECENT REPORTS", d: "Last 3 thesis snippets, summarized",   h: "~1K tok" },
    { l: "RELEVANT FEATURES", d: "Pre-computed numbers for any ticker mentioned", h: "~400 tok" },
    { l: "CONVERSATION HISTORY", d: "Last N turns",                   h: "~1.5K tok" },
    { l: "USER MESSAGE", d: "Current turn",                            h: "~50 tok" },
  ];

  s.addText("SYSTEM PROMPT ASSEMBLY", {
    x: 0.6, y: 2.4, w: 6, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });

  parts.forEach((p, i) => {
    const y = 2.85 + i * 0.62;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y, w: 6, h: 0.55,
      fill: { color: C.cream50 }, line: { color: C.ink900, width: 0.5, transparency: 92 },
    });
    s.addText(p.l, {
      x: 0.8, y: y + 0.04, w: 3.4, h: 0.25,
      fontFace: FONT.sans, fontSize: 10, color: C.ink900, bold: true, charSpacing: 2, margin: 0,
    });
    s.addText(p.d, {
      x: 0.8, y: y + 0.27, w: 4.5, h: 0.25,
      fontFace: FONT.sans, fontSize: 9, color: C.ink500, italic: true, margin: 0,
    });
    s.addText(p.h, {
      x: 5.0, y: y + 0.13, w: 1.5, h: 0.3,
      fontFace: FONT.mono, fontSize: 10, color: C.coral600, align: "right", margin: 0,
    });
  });

  // Right: code + cost
  codeBlock(s, 7.0, 2.4, 5.7, 3.1, [
    { text: 'reply = anthropic.messages.create(', options: { color: C.codeVal, breakLine: true } },
    { text: '  model="claude-sonnet-4-6",', options: { breakLine: true } },
    { text: '  system=[', options: { breakLine: true } },
    { text: '    {"type":"text","text":persona_spec,', options: { breakLine: true } },
    { text: '     "cache_control":{"type":"ephemeral"}},', options: { color: C.codeStr, breakLine: true } },
    { text: '    {"type":"text","text":book_+_reports},', options: { breakLine: true } },
    { text: '  ],', options: { breakLine: true } },
    { text: '  messages=conversation_history + [', options: { breakLine: true } },
    { text: '    {"role":"user","content":user_msg}', options: { breakLine: true } },
    { text: '  ],', options: { breakLine: true } },
    { text: '  max_tokens=600,', options: { breakLine: true } },
    { text: ')', options: {} },
  ]);

  card(s, 7.0, 5.7, 5.7, 1.25);
  s.addText("PER MESSAGE", {
    x: 7.25, y: 5.85, w: 5, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText("~$0.012 with caching (persona spec at 0.1× rate). " +
    "Heavy chat user (50 msgs/day) ≈ $0.60/day.", {
    x: 7.25, y: 6.15, w: 5.2, h: 0.8,
    fontFace: FONT.sans, fontSize: 12, color: C.ink700, margin: 0,
  });

  footerBrand(s); pageNum(s, 12);
}

// ═══════════════════════════════════════════════════════
// SLIDE 13 — TRADING EXECUTION
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "08 · TRADING EXECUTION");
  slideTitle(s, [{ text: "Adapter pattern. ", options: { color: C.ink900 } }, { text: "Paper today, live by flag.", options: { color: C.ink700, italic: true } }]);

  // Code excerpt
  codeBlock(s, 0.6, 2.4, 7.0, 3.0, [
    { text: '# tessera/execution/adapter.py', options: { color: C.codeStr, breakLine: true } },
    { text: 'class ExecutionAdapter(Protocol):', options: { color: C.codeKey, breakLine: true } },
    { text: '    def place(self, user_id, order: Order) -> Fill:', options: { breakLine: true } },
    { text: '        ...', options: { breakLine: true } },
    { text: '', options: { breakLine: true } },
    { text: 'class PaperEngine(ExecutionAdapter):  # default', options: { breakLine: true } },
    { text: '    """Marks-to-market in Neon ledger table."""', options: { color: C.codeStr, breakLine: true } },
    { text: '', options: { breakLine: true } },
    { text: 'class AlpacaLiveAdapter(ExecutionAdapter):  # flagged', options: { breakLine: true } },
    { text: '    """Routes via user\'s Alpaca OAuth token."""', options: { color: C.codeStr, breakLine: true } },
    { text: '', options: { breakLine: true } },
    { text: 'adapter = (AlpacaLiveAdapter() if flag(user_id, "live")', options: { breakLine: true } },
    { text: '           else PaperEngine())', options: {} },
  ]);

  // OAuth flow diagram (right side, compact)
  s.addText("OAUTH FLOW (USER → ALPACA)", {
    x: 8.0, y: 2.4, w: 5, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });

  const oauthSteps = [
    "1. User clicks 'Connect Alpaca'",
    "2. Redirect → Alpaca authorize URL",
    "3. User logs in on Alpaca's domain",
    "4. Callback returns short-lived code",
    "5. Backend exchanges code → access_token",
    "6. Token stored encrypted in Firestore",
    "7. Every order: user confirms in UI first",
  ];
  oauthSteps.forEach((step, i) => {
    s.addText(step, {
      x: 8.0, y: 2.85 + i * 0.35, w: 5, h: 0.3,
      fontFace: FONT.mono, fontSize: 11, color: C.ink800, margin: 0,
    });
  });

  // Hard rules / kill switch
  card(s, 0.6, 5.7, 12.1, 1.4);
  s.addText("INVARIANTS", {
    x: 0.85, y: 5.85, w: 6, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText([
    { text: "✓ No custody — we never receive funds. ", options: { bold: true } },
    { text: "✓ Every order: explicit user confirm in UI. ", options: { bold: true, breakLine: true } },
    { text: "✓ Kill switch: 1 click → queue close-all positions (paper or live) via Temporal workflow. ", options: { bold: true, breakLine: true } },
    { text: "✓ Same code path for paper/live — only the adapter changes.", options: { bold: true } },
  ], {
    x: 0.85, y: 6.15, w: 12, h: 1.0,
    fontFace: FONT.sans, fontSize: 12, color: C.ink800, margin: 0, paraSpaceAfter: 4,
  });

  footerBrand(s); pageNum(s, 13);
}

// ═══════════════════════════════════════════════════════
// SLIDE 14 — RISK GATEWAY + COMPLIANCE
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "09 · RISK + COMPLIANCE");
  slideTitle(s, [{ text: "Two backstops: ", options: { color: C.ink900 } }, { text: "code, then law.", options: { color: C.ink700, italic: true } }]);

  // Left: risk gateway code
  codeBlock(s, 0.6, 2.4, 6.0, 3.0, [
    { text: '# tessera/risk/gateway.py', options: { color: C.codeStr, breakLine: true } },
    { text: 'def validate(portfolio, persona) -> Result:', options: { color: C.codeKey, breakLine: true } },
    { text: '    fail = []', options: { breakLine: true } },
    { text: '    for pos in portfolio.positions:', options: { breakLine: true } },
    { text: '        if pos.ticker not in UNIVERSE:', options: { breakLine: true } },
    { text: '            fail += ["hallucinated_ticker"]', options: { color: C.codeKey, breakLine: true } },
    { text: '        if pos.weight > persona.MAX_NAME:', options: { breakLine: true } },
    { text: '            fail += ["single_name_cap_exceeded"]', options: { color: C.codeKey, breakLine: true } },
    { text: '    for sec, w in sector_weights(portfolio):', options: { breakLine: true } },
    { text: '        if w > persona.MAX_SECTOR: fail += [...]', options: { breakLine: true } },
    { text: '    if portfolio_var(portfolio) > VAR_BUDGET:', options: { breakLine: true } },
    { text: '        fail += ["var_budget_exceeded"]', options: { color: C.codeKey, breakLine: true } },
    { text: '    return Result(ok=not fail, reasons=fail)', options: {} },
  ]);

  // Right: compliance posture
  card(s, 6.8, 2.4, 5.9, 3.0);
  s.addText("US REGULATORY POSTURE", {
    x: 7.05, y: 2.55, w: 5.5, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });

  const reg = [
    ["Paper only, all users", "OK", C.sage500, "Research/educational — no SEC filing"],
    ["Self trading own capital", "OK", C.sage500, "No advisor relationship triggered"],
    ["Friends/family live", "REVIEW", C.coral500, "Securities lawyer consult first (~$300)"],
    ["Public users live", "BLOCKED", C.ink900, "Requires SEC RIA + state Blue Sky filings"],
  ];
  reg.forEach((r, i) => {
    const y = 2.95 + i * 0.6;
    s.addShape(pres.shapes.OVAL, {
      x: 7.05, y: y + 0.12, w: 0.14, h: 0.14,
      fill: { color: r[2] }, line: { color: r[2] },
    });
    s.addText(r[0], {
      x: 7.3, y, w: 3.0, h: 0.3,
      fontFace: FONT.sans, fontSize: 12, color: C.ink900, bold: true, margin: 0,
    });
    s.addText(r[1], {
      x: 10.3, y, w: 2.0, h: 0.3,
      fontFace: FONT.mono, fontSize: 11, color: r[2], bold: true, margin: 0,
    });
    s.addText(r[3], {
      x: 7.3, y: y + 0.28, w: 5.2, h: 0.3,
      fontFace: FONT.sans, fontSize: 10, color: C.ink600, italic: true, margin: 0,
    });
  });

  // Bottom: enforced invariants
  card(s, 0.6, 5.7, 12.1, 1.4);
  s.addText("INVARIANTS WE NEVER BREAK", {
    x: 0.85, y: 5.85, w: 6, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText("No custody  ·  No personalized advice  ·  No hallucinated tickers " +
    "·  No skipping paper-trading phase  ·  No live orders without explicit user confirmation", {
    x: 0.85, y: 6.2, w: 12, h: 0.8,
    fontFace: FONT.sans, fontSize: 13, color: C.ink800, margin: 0,
  });

  footerBrand(s); pageNum(s, 14);
}

// ═══════════════════════════════════════════════════════
// SLIDE 15 — COST + KNOBS
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "OPERATIONAL ECONOMICS");
  slideTitle(s, [{ text: "$60–325/mo at pilot. ", options: { color: C.ink900 } }, { text: "Knobs we can turn.", options: { color: C.ink700, italic: true } }]);

  // Left: cost breakdown
  s.addText("WHERE THE MONEY GOES", {
    x: 0.6, y: 2.4, w: 6, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });
  const cost = [
    ["LLM — Haiku screens",     "$15–40"],
    ["LLM — Sonnet thesis",     "$30–180"],
    ["LLM — Chat (user-driven)", "$10–50"],
    ["LLM — Opus weekly review", "$5–20"],
    ["Cloud Run + Neon + Firebase free tier", "$0–5"],
    ["Market data (Alpaca + FMP optional)",   "$0–30"],
  ];
  cost.forEach((r, i) => {
    const y = 2.8 + i * 0.5;
    if (i > 0) {
      s.addShape(pres.shapes.LINE, {
        x: 0.6, y, w: 6, h: 0,
        line: { color: C.ink300, width: 0.5 },
      });
    }
    s.addText(r[0], {
      x: 0.6, y: y + 0.1, w: 4.5, h: 0.4,
      fontFace: FONT.sans, fontSize: 12, color: C.ink800, margin: 0,
    });
    s.addText(r[1], {
      x: 5.0, y: y + 0.1, w: 1.6, h: 0.4,
      fontFace: FONT.mono, fontSize: 12, color: C.ink900, align: "right", margin: 0,
    });
  });
  // total
  s.addShape(pres.shapes.LINE, {
    x: 0.6, y: 5.85, w: 6, h: 0, line: { color: C.ink900, width: 1.5 },
  });
  s.addText("TOTAL", {
    x: 0.6, y: 5.95, w: 4.5, h: 0.4,
    fontFace: FONT.sans, fontSize: 12, color: C.ink900, bold: true, margin: 0,
  });
  s.addText("$60–325", {
    x: 5.0, y: 5.95, w: 1.6, h: 0.4,
    fontFace: FONT.mono, fontSize: 14, color: C.coral600, bold: true, align: "right", margin: 0,
  });

  // Right: knobs we can turn
  card(s, 7.0, 2.4, 5.7, 4.4);
  s.addText("LEVERS TO REDUCE COST", {
    x: 7.25, y: 2.55, w: 5.2, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });
  const knobs = [
    ["Daily → weekly batch", "−60% LLM", "Long-term holdings don't need daily updates"],
    ["4 personas → 2 personas", "−50% LLM", "MVP can run with Warren + Cathie only"],
    ["Sonnet → Haiku for thesis", "−70% LLM", "Voice quality drops, valid trade-off"],
    ["Prompt caching always-on", "−40% LLM", "Cached persona spec (5-min TTL)"],
    ["Skip the Opus weekly review", "−$15", "Replace with simple performance table"],
  ];
  knobs.forEach((k, i) => {
    const y = 3.0 + i * 0.72;
    s.addText(k[0], {
      x: 7.25, y, w: 3.5, h: 0.3,
      fontFace: FONT.sans, fontSize: 11, color: C.ink900, bold: true, margin: 0,
    });
    s.addText(k[1], {
      x: 10.8, y, w: 1.7, h: 0.3,
      fontFace: FONT.mono, fontSize: 11, color: C.sage500, bold: true, align: "right", margin: 0,
    });
    s.addText(k[2], {
      x: 7.25, y: y + 0.28, w: 5.2, h: 0.35,
      fontFace: FONT.sans, fontSize: 10, color: C.ink600, italic: true, margin: 0,
    });
  });

  s.addText("Cost is independent of user count. Persona analysis is shared across all subscribers.", {
    x: 0.6, y: 7.0, w: 12, h: 0.4,
    fontFace: FONT.sans, italic: true, fontSize: 11, color: C.ink500, margin: 0,
  });
  pageNum(s, 15);
}

// ═══════════════════════════════════════════════════════
// SLIDE 16 — STATUS + PLAN SUMMARY
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  eyebrow(s, "STATUS · PLAN");
  slideTitle(s, [{ text: "Where we are. ", options: { color: C.ink900 } }, { text: "Where we're going.", options: { color: C.ink700, italic: true } }]);

  // ── LEFT: Where we are today ──
  const lx = 0.6, lw = 5.95, ly = 2.4;
  card(s, lx, ly, lw, 4.5);
  s.addText("BUILT TODAY", {
    x: lx + 0.3, y: ly + 0.25, w: lw - 0.6, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText("Frontend MVP, demo-ready", {
    x: lx + 0.3, y: ly + 0.55, w: lw - 0.6, h: 0.4,
    fontFace: FONT.serif, italic: true, fontSize: 16, color: C.ink800, margin: 0,
  });

  const built = [
    "Next.js 14 + Tailwind + Recharts, Vercel-ready",
    "4 personas with photos, bios, system prompts",
    "Marketplace + proposals + dashboard + how-it-works",
    "Slide-over detail with Thesis ↔ Chat toggle",
    "Chat UI with streaming (mock backend)",
    "personalities.md (~600 lines/persona) ready for LLM",
  ];
  built.forEach((b, i) => {
    const y = ly + 1.15 + i * 0.34;
    s.addShape(pres.shapes.OVAL, {
      x: lx + 0.35, y: y + 0.1, w: 0.12, h: 0.12,
      fill: { color: C.sage500 }, line: { color: C.sage500 },
    });
    s.addText(b, {
      x: lx + 0.6, y, w: lw - 0.9, h: 0.32,
      fontFace: FONT.sans, fontSize: 11, color: C.ink700, margin: 0,
    });
  });

  // Pending list
  s.addText("PENDING", {
    x: lx + 0.3, y: ly + 3.3, w: lw - 0.6, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.ink500, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText("Backend · real LLM · data ingestion · paper engine · auth · broker", {
    x: lx + 0.3, y: ly + 3.6, w: lw - 0.6, h: 0.7,
    fontFace: FONT.sans, fontSize: 11, color: C.ink600, italic: true, margin: 0,
  });

  // ── RIGHT: Path to production ──
  const rx = 6.85, rw = 5.85, ry = 2.4;
  card(s, rx, ry, rw, 4.5);
  s.addText("PATH TO PRODUCTION", {
    x: rx + 0.3, y: ry + 0.25, w: rw - 0.6, h: 0.3,
    fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 3, margin: 0,
  });
  s.addText("6-week pilot, paper-first", {
    x: rx + 0.3, y: ry + 0.55, w: rw - 0.6, h: 0.4,
    fontFace: FONT.serif, italic: true, fontSize: 16, color: C.ink800, margin: 0,
  });

  const phases = [
    { p: "A", t: "Data backbone",        w: "wk 1",         d: "Ingestors, feature builder, Neon schema" },
    { p: "B", t: "Real LLM theses",      w: "wks 2–3",      d: "Haiku screen + Sonnet thesis, Pydantic validate" },
    { p: "C", t: "Paper execution",      w: "wks 4–5",      d: "Risk gateway, paper engine, real P&L attribution" },
    { p: "D", t: "User auth + follow",   w: "wk 6",         d: "Firebase Auth, 3 F&F users on paper" },
    { p: "E", t: "Compliance review",    w: "wk 6 (parallel)", d: "Securities lawyer consult, written advice" },
    { p: "F", t: "Live trading (opt)",   w: "wk 7+",        d: "Alpaca OAuth, self first, F&F only if E clears" },
  ];
  phases.forEach((ph, i) => {
    const y = ry + 1.15 + i * 0.55;
    // Phase letter badge
    s.addShape(pres.shapes.OVAL, {
      x: rx + 0.3, y: y + 0.05, w: 0.4, h: 0.4,
      fill: { color: i === 0 ? C.coral500 : C.ink900 },
      line: { color: i === 0 ? C.coral500 : C.ink900 },
    });
    s.addText(ph.p, {
      x: rx + 0.3, y: y + 0.05, w: 0.4, h: 0.4,
      fontFace: FONT.serif, italic: true, fontSize: 12, color: C.cream100,
      align: "center", valign: "middle", margin: 0,
    });
    // Title
    s.addText(ph.t, {
      x: rx + 0.85, y: y, w: 3.0, h: 0.3,
      fontFace: FONT.sans, fontSize: 12, color: C.ink900, bold: true, margin: 0,
    });
    // Weeks (right-aligned)
    s.addText(ph.w, {
      x: rx + rw - 1.5, y: y, w: 1.3, h: 0.3,
      fontFace: FONT.mono, fontSize: 10, color: C.coral600, align: "right", margin: 0,
    });
    // Description
    s.addText(ph.d, {
      x: rx + 0.85, y: y + 0.28, w: rw - 1.1, h: 0.3,
      fontFace: FONT.sans, fontSize: 10, color: C.ink600, italic: true, margin: 0,
    });
  });

  // Bottom DoD strip
  s.addText("MVP done when: 4 personas writing real theses daily · 30+ days paper P&L · 3 F&F users active · lawyer advice on file · cost stable < $200/mo", {
    x: 0.6, y: 7.1, w: 12, h: 0.4,
    fontFace: FONT.sans, italic: true, fontSize: 10, color: C.ink500, margin: 0,
  });
  pageNum(s, 16);
}

// ═══════════════════════════════════════════════════════
// SLIDE 17 — CLOSING / Q&A
// ═══════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.ink900 };

  // Mosaic motif bottom-right (pulled in slightly so no tile rides the slide edge)
  const tiles = [
    [11.6, 5.55, C.cream100], [12.25, 5.55, C.cream100],
    [11.6, 6.2, C.coral500],  [12.25, 6.2, C.cream100],
    [11.6, 6.85, C.cream100], [12.25, 6.85, C.sage500],
  ];
  tiles.forEach(([x, y, c]) =>
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.55, h: 0.55, fill: { color: c }, line: { color: c } })
  );

  eyebrow(s, "TESSERA · TECHNICAL DECK");

  s.addText([
    { text: "Questions.\n", options: { color: C.cream100 } },
    { text: "Comments. ", options: { color: C.coral500, italic: true } },
    { text: "Forks.", options: { color: C.cream100 } },
  ], {
    x: 0.6, y: 1.8, w: 12, h: 3.6,
    fontFace: FONT.serif, fontSize: 88, charSpacing: -3, margin: 0,
  });

  // Three sub-points (kept narrow so they don't collide with the mosaic on the right)
  const links = [
    ["Repo", "github.com/6ummy/Tessera"],
    ["Architecture", "architecture.md"],
    ["Persona specs", "personalities.md"],
  ];
  links.forEach((l, i) => {
    const x = 0.6 + i * 3.4;
    s.addText(l[0], {
      x, y: 6.0, w: 3.2, h: 0.3,
      fontFace: FONT.sans, fontSize: 10, color: C.coral500, bold: true, charSpacing: 3, margin: 0,
    });
    s.addText(l[1], {
      x, y: 6.3, w: 3.2, h: 0.4,
      fontFace: FONT.mono, fontSize: 13, color: C.cream100, margin: 0,
    });
  });

  s.addText("Thanks.", {
    x: 0.6, y: 7.05, w: 6, h: 0.35,
    fontFace: FONT.serif, italic: true, fontSize: 14, color: C.ink400, margin: 0,
  });
}

// ─────────────────────────────────────────────────────────
pres.writeFile({ fileName: "tessera-deck.pptx" }).then(name => {
  console.log("Wrote:", name);
});
