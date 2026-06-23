// build-convt-cd-deck.js — Convt Phase C + D build review, 5 slides (English).
// Run from repo root:  node build-convt-cd-deck.js  → decks/convt-phase-c-d.pptx
// Sources: case-studies.md, CLAUDE.md, Plan.md, architecture.md.
// Design tokens inlined (Tessera/Convt visual language) — runs standalone.

const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
pres.author = "Convt";
pres.title = "Convt — Phase C + D build review";

const C = {
  cream100: "F5F4EE", cream50: "FAF9F5", cream200: "EDEBE0",
  ink900: "1F1E1B", ink700: "3D3B36", ink600: "5A5751",
  ink500: "7C7870", ink400: "A8A39A", ink300: "C9C5BC",
  coral500: "D97757", coral600: "C2613F", coral50: "FBF1ED",
  sage500: "6B8E6B", plum500: "8B6B8E",
};
const FONT = { serif: "Georgia", sans: "Calibri", mono: "Consolas" };
const TOTAL = 5;
const shadow = () => ({ type: "outer", color: "1F1E1B", blur: 18, offset: 4, angle: 90, opacity: 0.06 });

function base() { const s = pres.addSlide(); s.background = { color: C.cream100 }; return s; }
function mosaic(s) {
  [[11.55, 0.5, C.coral500], [12.1, 0.5, C.cream200], [11.55, 1.05, C.ink900], [12.1, 1.05, C.sage500]]
    .forEach(([x, y, c]) => s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.5, h: 0.5, fill: { color: c }, line: { color: c } }));
}
function eyebrow(s, t) { s.addText(t, { x: 0.6, y: 0.55, w: 10.6, h: 0.3, fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 4, margin: 0 }); }
function headline(s, parts, fs = 33) { s.addText(parts, { x: 0.6, y: 0.98, w: 11.7, h: 0.95, fontFace: FONT.serif, fontSize: fs, charSpacing: -1, margin: 0 }); }
function subtitle(s, t, y = 1.92, w = 11.8) { s.addText(t, { x: 0.6, y, w, h: 0.7, fontFace: FONT.sans, fontSize: 12.5, color: C.ink600, italic: true, margin: 0, lineSpacingMultiple: 1.08 }); }
function foot(s, n, ctx) {
  s.addText(`Convt · ${ctx}`, { x: 0.6, y: 7.12, w: 8, h: 0.25, fontFace: FONT.serif, italic: true, fontSize: 10, color: C.ink500, margin: 0 });
  s.addText(`${String(n).padStart(2, "0")} / ${String(TOTAL).padStart(2, "0")}`, { x: 12.4, y: 7.12, w: 0.7, h: 0.25, fontFace: FONT.mono, fontSize: 9, color: C.ink400, align: "right", margin: 0 });
}
function card(s, x, y, w, h, accent, title, body) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: C.cream50 }, line: { color: C.ink900, width: 0.5, transparency: 92 }, shadow: shadow() });
  s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.12, h, fill: { color: accent }, line: { color: accent } });
  s.addShape(pres.shapes.RECTANGLE, { x: x + 0.32, y: y + 0.28, w: 0.2, h: 0.2, fill: { color: accent }, line: { color: accent } });
  s.addText(title, { x: x + 0.64, y: y + 0.2, w: w - 0.85, h: 0.36, fontFace: FONT.serif, fontSize: 15.5, color: C.ink900, margin: 0 });
  s.addText(body, { x: x + 0.32, y: y + 0.66, w: w - 0.6, h: h - 0.82, fontFace: FONT.sans, fontSize: 11, color: C.ink600, margin: 0, lineSpacingMultiple: 1.06 });
}

// ───────────── Slide 1 — overview ─────────────
{
  const s = base(); mosaic(s);
  eyebrow(s, "PHASE C + D · BUILD REVIEW · 2026");
  headline(s, [
    { text: "Four AI analysts, ", options: { color: C.ink900 } },
    { text: "one disciplined machine", options: { color: C.coral600, italic: true } },
    { text: ".", options: { color: C.ink900 } },
  ], 38);
  subtitle(s, "Warren (value), Cathie (disruptive growth), Ray (macro), and Peter (GARP) each write a weekly investment thesis. A deterministic engine runs every book against a $100K paper account; users follow the analyst that thinks like them. Paper trading only — no real money.", 2.0, 11.9);

  const stats = [
    ["4", "analyst personas", C.coral500],
    ["weekly", "theses + rebalance", C.sage500],
    ["$100K", "paper book · each", C.plum500],
    ["convt.xyz", "live in the browser", C.ink900],
  ];
  const sw = 2.85, gap = 0.3, x0 = 0.6, y = 4.1;
  stats.forEach(([num, label, c], i) => {
    const x = x0 + i * (sw + gap);
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: sw, h: 1.85, fill: { color: C.cream50 }, line: { color: C.ink900, width: 0.5, transparency: 92 }, shadow: shadow() });
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: sw, h: 0.1, fill: { color: c }, line: { color: c } });
    s.addText(num, { x: x + 0.22, y: y + 0.42, w: sw - 0.44, h: 0.78, fontFace: FONT.mono, fontSize: 27, color: C.ink900, margin: 0 });
    s.addText(label, { x: x + 0.22, y: y + 1.28, w: sw - 0.44, h: 0.4, fontFace: FONT.sans, fontSize: 11, color: C.ink500, margin: 0 });
  });
  s.addText("Two phases: C built the engine (research → risk → paper P&L); D turned it into a product people use.", { x: 0.6, y: 6.25, w: 11.9, h: 0.4, fontFace: FONT.sans, fontSize: 11.5, italic: true, color: C.ink500, margin: 0 });
  foot(s, 1, "overview");
}

// ───────────── Slide 2 — Phase C: the engine ─────────────
{
  const s = base();
  eyebrow(s, "PHASE C — THE ENGINE");
  headline(s, [
    { text: "Numbers in code, ", options: { color: C.ink900 } },
    { text: "narrative in the LLM", options: { color: C.coral600, italic: true } },
    { text: ".", options: { color: C.ink900 } },
  ]);
  subtitle(s, "The pipeline turns market data into a tradeable book — and never lets the model invent a price, a weight, or a P&L.");

  const x1 = 0.6, x2 = 6.85, y1 = 2.7, y2 = 4.78, cw = 5.85, ch = 1.95;
  card(s, x1, y1, cw, ch, C.coral500, "Weekly thesis batch", "A research call per shortlisted ticker, then ONE construction call per persona. Sizing intent is normalized deterministically so weights always sum to 1.0 — the LLM argues, code does the arithmetic.");
  card(s, x2, y1, cw, ch, C.sage500, "Deterministic risk gateway", "Every book clears the same gate before anyone sees it: parametric VaR99, a drawdown floor, single-name + sector caps, and an active-position count. Rejections feed back into a retry.");
  card(s, x1, y2, cw, ch, C.plum500, "Paper engine", "Fills at the next bar's OPEN, marks to market at the close, conserves NAV exactly (no fees v1). Idempotent by report id — re-running a day can't double-trade.");
  card(s, x2, y2, cw, ch, C.ink900, "90-day backtest baseline", "Point-in-time replay, Sharpe by archetype — Warren 1.28 · Cathie 3.21 · Peter 2.81 · Ray 1.96. All positive, ordered exactly by mandate (growth > GARP > macro > value).");
  foot(s, 2, "Phase C");
}

// ───────────── Slide 3 — Phase D: the product ─────────────
{
  const s = base();
  eyebrow(s, "PHASE D — THE PRODUCT");
  headline(s, [
    { text: "From a research desk to ", options: { color: C.ink900 } },
    { text: "a thing people use", options: { color: C.coral600, italic: true } },
    { text: ".", options: { color: C.ink900 } },
  ]);
  subtitle(s, "Sign-in to leaderboard, end to end and real — the only mock left (the social feed) was retired.");

  const x1 = 0.6, x2 = 6.85, y1 = 2.7, y2 = 4.78, cw = 5.85, ch = 1.95;
  card(s, x1, y1, cw, ch, C.coral500, "Sign in & follow", "Google SSO; the user record is upserted from a verified token (no service-account secret). Single-follow — one analyst at a time; switching is logged so the account curve shows the change.");
  card(s, x2, y1, cw, ch, C.sage500, "Your portfolio", "A personal $100K paper book mirrors the analyst by weight. Return is compounded since your FIRST follow and carries across switches — reconstructed from the event log, not a row that resets to $100K.");
  card(s, x1, y2, cw, ch, C.plum500, "Public leaderboard + profiles", "Pick a nickname, go public, and rank against other real investors by since-inception return. Emails and real names are never exposed — nickname only.");
  card(s, x2, y2, cw, ch, C.ink900, "Email alerts", "A rebalance email when your analyst moves, plus a confirmation email — each carrying a one-click, signed unsubscribe link. Email is the single notify channel (web push was dropped).");
  s.addText("+ Rebranded Tessera → Convt and wired the convt.xyz domain + sending email.", { x: 0.6, y: 6.85, w: 11.9, h: 0.35, fontFace: FONT.sans, fontSize: 11, italic: true, color: C.ink500, margin: 0 });
  foot(s, 3, "Phase D");
}

// ───────────── Slide 4 — case studies ─────────────
{
  const s = base();
  eyebrow(s, "CASE STUDIES — SILENT FAILURES");
  headline(s, [
    { text: "The worst bugs ", options: { color: C.ink900 } },
    { text: "threw no error", options: { color: C.coral600, italic: true } },
    { text: ".", options: { color: C.ink900 } },
  ]);
  subtitle(s, "Our #1 bug class: empty or wrong results that look like success. Four that taught us the most.");

  const x1 = 0.6, x2 = 6.85, y1 = 2.7, y2 = 4.78, cw = 5.85, ch = 1.95;
  card(s, x1, y1, cw, ch, C.coral500, "The duplicated trading day", "Two data sources stored the same day twice (Alpaca 04:00Z vs Yahoo 00:00Z). Every row-window feature silently used HALF its intended horizon — for ~6 years. No error; a daily SPY canary now trips on it.");
  card(s, x2, y1, cw, ch, C.sage500, "COIN's 2.7-year-old margin", "A brokerage changed an XBRL tag; the loader quietly walked back to a 2021 crypto-bull value ($4.16B) that was 'reasonable but stale.' Sanity bounds catch unit errors — not staleness. Now: a freshness guard.");
  card(s, x1, y2, cw, ch, C.plum500, "Worked locally, 500 in prod", "The database driver returns dates as objects on the server but strings on the client. The exact same code ran fine in the browser and crashed only in production. Fix: pin the type at the SQL boundary.");
  card(s, x2, y2, cw, ch, C.ink900, "A green job marked “Failed”", "Every step of the nightly run succeeded — but an idle DB connection got reaped, and the cleanup that tried to use it threw, flipping the exit code to 1. Teardown errors must never rewrite the result.");
  foot(s, 4, "case studies");
}

// ───────────── Slide 5 — the Cathie problem ─────────────
{
  const s = base(); mosaic(s);
  eyebrow(s, "WHEN THE AI WON'T FOLLOW THE RULES");
  headline(s, [
    { text: "Cathie kept breaking the cap. ", options: { color: C.ink900 } },
    { text: "We were both right", options: { color: C.coral600, italic: true } },
    { text: ".", options: { color: C.ink900 } },
  ], 31);
  subtitle(s, "The most interesting bug wasn't a bug — it was the model staying in character harder than our rules.");

  // Story box
  s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 2.55, w: 12.1, h: 1.35, fill: { color: C.coral50 }, line: { color: C.coral500, width: 1 }, shadow: shadow() });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 2.55, w: 0.12, h: 1.35, fill: { color: C.coral500 }, line: { color: C.coral500 } });
  s.addText([
    { text: "The story.  ", options: { fontFace: FONT.serif, fontSize: 14, color: C.coral600, italic: true } },
    { text: "Cathie's first book put 67% in Technology — rejected by the 50% sector cap. We fed back the exact number: “Technology 0.5600 > sector cap 0.50.” Her retry trimmed it only to 56% — still over. The persona's conviction in disruptive tech outran our math. No crash, just a model that wouldn't break character.",
      options: { fontFace: FONT.sans, fontSize: 12, color: C.ink700 } },
  ], { x: 0.95, y: 2.68, w: 11.5, h: 1.1, margin: 0, lineSpacingMultiple: 1.06 });

  // Two takeaways
  const cw = 5.85, ch = 1.7, y = 4.15;
  card(s, 0.6, y, cw, ch, C.ink900, "Takeaway 1 — Enforce, don't ask", "Critical limits live in a system-level gate (the risk gateway), never in a polite instruction the model can roleplay around. The cap that matters is the one code rejects, not the one the prompt requests.");
  card(s, 6.85, y, cw, ch, C.sage500, "Takeaway 2 — …but we removed her cap", "Tech / S-curve concentration IS Cathie's mandate — a sector cap was the wrong tool for her. We dropped it, and bound her risk instead by single-name 16% + VaR99 8.5% + a 35% drawdown floor.");

  s.addText([
    { text: "The rule about the rule:  ", options: { fontFace: FONT.serif, italic: true, color: C.coral600 } },
    { text: "drop a cap because it's the wrong control — never because the model keeps busting it. One neuters the gate; the other fixes what you're controlling.", options: { color: C.ink600 } },
  ], { x: 0.6, y: 6.1, w: 12.1, h: 0.7, fontFace: FONT.sans, fontSize: 11.5, margin: 0, lineSpacingMultiple: 1.05 });
  foot(s, 5, "AI behaviour");
}

pres.writeFile({ fileName: "decks/convt-phase-c-d.pptx" }).then((n) => console.log("Wrote:", n));
