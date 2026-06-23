// build-convt-numbers-deck.js — single "By the numbers" stat board.
// Run from repo root:  node build-convt-numbers-deck.js  → decks/convt-by-the-numbers.pptx

const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Convt";
pres.title = "Convt — by the numbers";

const C = {
  cream100: "F5F4EE", cream50: "FAF9F5", cream200: "EDEBE0",
  ink900: "1F1E1B", ink700: "3D3B36", ink600: "5A5751", ink500: "7C7870", ink400: "A8A39A",
  coral500: "D97757", coral600: "C2613F", sage500: "6B8E6B", plum500: "8B6B8E",
};
const FONT = { serif: "Georgia", sans: "Calibri", mono: "Consolas" };
const shadow = () => ({ type: "outer", color: "1F1E1B", blur: 18, offset: 4, angle: 90, opacity: 0.06 });

const s = pres.addSlide();
s.background = { color: C.cream100 };

// Mosaic top-right
[[11.55, 0.5, C.coral500], [12.1, 0.5, C.cream200], [11.55, 1.05, C.ink900], [12.1, 1.05, C.sage500]]
  .forEach(([x, y, c]) => s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.5, h: 0.5, fill: { color: c }, line: { color: c } }));

s.addText("CONVT · PHASE C + D · BY THE NUMBERS", { x: 0.6, y: 0.55, w: 10.6, h: 0.3, fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 4, margin: 0 });
s.addText([
  { text: "By the ", options: { color: C.ink900 } },
  { text: "numbers", options: { color: C.coral600, italic: true } },
  { text: ".", options: { color: C.ink900 } },
], { x: 0.6, y: 1.0, w: 11.7, h: 0.95, fontFace: FONT.serif, fontSize: 38, charSpacing: -1, margin: 0 });
s.addText("What it took to get Convt from an empty repo to a live paper-trading product — measured from git and the production database.", { x: 0.6, y: 1.95, w: 11.9, h: 0.5, fontFace: FONT.sans, fontSize: 12.5, italic: true, color: C.ink600, margin: 0 });

const stats = [
  ["55.5K", "lines of code written", "~29.7K live today · 205 commits", C.coral500],
  ["~200", "pull requests", "merged, almost all squash", C.sage500],
  ["19", "case studies documented", "deep bug write-ups · 50+ total fixes", C.plum500],
  ["59", "tickers analysed", "41 stocks · 8 crypto · 10 ETFs", C.ink900],
  ["20 yrs", "of price history backfilled", "212K daily bars across the universe", C.coral500],
  ["~400", "AI theses written", "237 memories · 1,094 LLM calls", C.sage500],
];

const cw = 3.85, ch = 1.95, gx = 0.32, gy = 0.3, x0 = 0.6, y0 = 2.75;
stats.forEach((st, i) => {
  const col = i % 3, row = Math.floor(i / 3);
  const x = x0 + col * (cw + gx);
  const y = y0 + row * (ch + gy);
  const [num, label, sub, c] = st;
  s.addShape(pres.shapes.RECTANGLE, { x, y, w: cw, h: ch, fill: { color: C.cream50 }, line: { color: C.ink900, width: 0.5, transparency: 92 }, shadow: shadow() });
  s.addShape(pres.shapes.RECTANGLE, { x, y, w: cw, h: 0.1, fill: { color: c }, line: { color: c } });
  s.addText(num, { x: x + 0.28, y: y + 0.3, w: cw - 0.5, h: 0.78, fontFace: FONT.mono, fontSize: 36, color: C.ink900, margin: 0 });
  s.addText(label, { x: x + 0.3, y: y + 1.12, w: cw - 0.55, h: 0.4, fontFace: FONT.serif, fontSize: 15, color: C.ink900, margin: 0 });
  s.addText(sub, { x: x + 0.3, y: y + 1.5, w: cw - 0.55, h: 0.35, fontFace: FONT.sans, fontSize: 10, color: C.ink500, margin: 0 });
});

s.addText("Paper trading only — no fine-tuning. The four analysts are prompted (Sonnet 4.6) and recall their own past theses from memory.", { x: 0.6, y: 7.12, w: 11, h: 0.25, fontFace: FONT.serif, italic: true, fontSize: 10, color: C.ink500, margin: 0 });
s.addText("01 / 01", { x: 12.4, y: 7.12, w: 0.7, h: 0.25, fontFace: FONT.mono, fontSize: 9, color: C.ink400, align: "right", margin: 0 });

pres.writeFile({ fileName: "decks/convt-by-the-numbers.pptx" }).then((n) => console.log("Wrote:", n));
