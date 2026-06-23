// build-convt-phase-d-deck.js — Convt Phase D update, general-audience, 5 slides.
// Run from repo root:  node build-convt-phase-d-deck.js  → decks/convt-phase-d.pptx
// Design tokens inlined (Tessera/Convt visual language) so it runs standalone.

const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
pres.author = "Convt";
pres.title = "Convt — Phase D update";

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

function base(title) {
  const s = pres.addSlide();
  s.background = { color: C.cream100 };
  return s;
}
function mosaic(s) {
  [
    [11.55, 0.5, C.coral500], [12.1, 0.5, C.cream200],
    [11.55, 1.05, C.ink900], [12.1, 1.05, C.sage500],
  ].forEach(([x, y, c]) => s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.5, h: 0.5, fill: { color: c }, line: { color: c } }));
}
function eyebrow(s, t) {
  s.addText(t, { x: 0.6, y: 0.55, w: 10.5, h: 0.3, fontFace: FONT.sans, fontSize: 10, color: C.coral600, bold: true, charSpacing: 4, margin: 0 });
}
function headline(s, parts, fs = 34) {
  s.addText(parts, { x: 0.6, y: 1.0, w: 11.6, h: 1.0, fontFace: FONT.serif, fontSize: fs, charSpacing: -1, margin: 0 });
}
function subtitle(s, t, y = 1.95, w = 11.6) {
  s.addText(t, { x: 0.6, y, w, h: 0.8, fontFace: FONT.sans, fontSize: 13, color: C.ink600, italic: true, margin: 0, lineSpacingMultiple: 1.1 });
}
function foot(s, n, ctx) {
  s.addText(`Convt · ${ctx}`, { x: 0.6, y: 7.1, w: 7, h: 0.25, fontFace: FONT.serif, italic: true, fontSize: 10, color: C.ink500, margin: 0 });
  s.addText(`${String(n).padStart(2, "0")} / ${String(TOTAL).padStart(2, "0")}`, { x: 12.4, y: 7.1, w: 0.7, h: 0.25, fontFace: FONT.mono, fontSize: 9, color: C.ink400, align: "right", margin: 0 });
}
// Card with a small accent square + title + body.
function card(s, x, y, w, h, accent, title, body) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: C.cream50 }, line: { color: C.ink900, width: 0.5, transparency: 92 }, shadow: shadow() });
  s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.12, h, fill: { color: accent }, line: { color: accent } });
  s.addShape(pres.shapes.RECTANGLE, { x: x + 0.32, y: y + 0.3, w: 0.22, h: 0.22, fill: { color: accent }, line: { color: accent } });
  s.addText(title, { x: x + 0.66, y: y + 0.22, w: w - 0.9, h: 0.4, fontFace: FONT.serif, fontSize: 16, color: C.ink900, margin: 0 });
  s.addText(body, { x: x + 0.32, y: y + 0.72, w: w - 0.6, h: h - 0.9, fontFace: FONT.sans, fontSize: 11.5, color: C.ink600, margin: 0, lineSpacingMultiple: 1.08 });
}

// ───────────────────────── Slide 1 — Title / hero ─────────────────────────
{
  const s = base();
  mosaic(s);
  eyebrow(s, "PHASE D · 2026년 6월 업데이트");
  headline(s, [
    { text: "AI 애널리스트 4명, ", options: { color: C.ink900 } },
    { text: "당신의 포트폴리오", options: { color: C.coral600, italic: true } },
    { text: ".", options: { color: C.ink900 } },
  ], 40);
  subtitle(s, "매주 4명의 AI 애널리스트가 각자의 철학으로 투자 의견을 씁니다. 사용자는 한 명을 골라, $100K 가상 계좌로 그 사람을 그대로 따라 투자합니다. 실제 돈은 쓰지 않는 페이퍼 트레이딩입니다.", 2.05, 11.8);

  const stats = [
    ["4", "AI 애널리스트", C.coral500],
    ["$100K", "가상 계좌 · 1인당", C.sage500],
    ["convt.xyz", "서비스 오픈", C.plum500],
    ["$0", "실제 돈 · 페이퍼 전용", C.ink900],
  ];
  const sw = 2.85, gap = 0.3, startX = 0.6, y = 4.0;
  stats.forEach(([num, label, c], i) => {
    const x = startX + i * (sw + gap);
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: sw, h: 1.9, fill: { color: C.cream50 }, line: { color: C.ink900, width: 0.5, transparency: 92 }, shadow: shadow() });
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: sw, h: 0.1, fill: { color: c }, line: { color: c } });
    s.addText(num, { x: x + 0.2, y: y + 0.45, w: sw - 0.4, h: 0.8, fontFace: FONT.mono, fontSize: 30, color: C.ink900, margin: 0 });
    s.addText(label, { x: x + 0.2, y: y + 1.32, w: sw - 0.4, h: 0.4, fontFace: FONT.sans, fontSize: 11, color: C.ink500, margin: 0 });
  });
  foot(s, 1, "한눈에 보기");
}

// ───────────────────────── Slide 2 — How it works ─────────────────────────
{
  const s = base();
  eyebrow(s, "어떻게 작동하나");
  headline(s, [
    { text: "로그인 → 팔로우 → ", options: { color: C.ink900 } },
    { text: "미러링 → 경쟁", options: { color: C.coral600, italic: true } },
    { text: ".", options: { color: C.ink900 } },
  ]);
  subtitle(s, "복잡한 설정 없이 네 단계면 끝입니다. 따라가고 싶은 애널리스트만 고르면 나머지는 자동입니다.");

  const steps = [
    ["1 · 로그인", "구글 계정으로 가입", C.ink900],
    ["2 · 팔로우", "4명 중 한 명 선택", C.coral500],
    ["3 · 미러링", "내 $100K가 그 애널리스트의 포트폴리오를 그대로 추종", C.sage500],
    ["4 · 경쟁 + 알림", "리더보드에서 수익률 비교, 리밸런스 때 이메일", C.plum500],
  ];
  const bw = 2.85, bh = 2.5, gap = 0.27, startX = 0.6, y = 3.2;
  steps.forEach(([t, b, c], i) => {
    const x = startX + i * (bw + gap);
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: bw, h: bh, fill: { color: C.cream50 }, line: { color: c, width: 2 }, shadow: shadow() });
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: bw, h: 0.12, fill: { color: c }, line: { color: c } });
    s.addText(t, { x: x + 0.25, y: y + 0.35, w: bw - 0.45, h: 0.5, fontFace: FONT.serif, fontSize: 17, color: C.ink900, margin: 0 });
    s.addText(b, { x: x + 0.25, y: y + 0.95, w: bw - 0.45, h: 1.4, fontFace: FONT.sans, fontSize: 12, color: C.ink600, margin: 0, lineSpacingMultiple: 1.1 });
    if (i < steps.length - 1) {
      s.addShape(pres.shapes.RIGHT_ARROW, { x: x + bw + 0.02, y: y + bh / 2 - 0.13, w: gap - 0.04, h: 0.26, fill: { color: C.ink400 }, line: { color: C.ink400 } });
    }
  });
  s.addText("실제 돈은 들어가지 않습니다 — 전 과정이 가상($100K) 페이퍼 트랙입니다.", { x: 0.6, y: 6.05, w: 11.8, h: 0.4, fontFace: FONT.sans, fontSize: 11, italic: true, color: C.ink500, margin: 0 });
  foot(s, 2, "제품 흐름");
}

// ───────────────────────── Slide 3 — What shipped ─────────────────────────
{
  const s = base();
  eyebrow(s, "PHASE D — 무엇을 출시했나");
  headline(s, [
    { text: "데모가 아니라, ", options: { color: C.ink900 } },
    { text: "실제로 쓰는 제품", options: { color: C.coral600, italic: true } },
    { text: ".", options: { color: C.ink900 } },
  ]);
  subtitle(s, "로그인부터 수익률 경쟁까지 — 사용자가 직접 쓸 수 있는 끝-에서-끝 흐름이 모두 라이브가 됐습니다.");

  const x1 = 0.6, x2 = 6.85, y1 = 2.85, y2 = 4.75, cw = 5.85, ch = 1.75;
  card(s, x1, y1, cw, ch, C.coral500, "계정 & 팔로우", "구글 로그인 후, 4명 중 한 명을 팔로우. 한 번에 한 명만 — 갈아타면 그 시점부터 새 애널리스트를 추종합니다.");
  card(s, x2, y1, cw, ch, C.sage500, "내 포트폴리오", "첫 팔로우부터의 누적 수익률을 보여줍니다. 애널리스트를 바꿔도 손익이 끊기지 않고 하나의 계좌로 이어집니다.");
  card(s, x1, y2, cw, ch, C.plum500, "공개 리더보드 + 프로필", "닉네임으로 다른 투자자들과 수익률을 비교. 이메일·실명은 절대 공개되지 않습니다.");
  card(s, x2, y2, cw, ch, C.ink900, "이메일 알림", "팔로우한 애널리스트가 리밸런스하면 메일로 알림. 가입 확인 메일 + 한 번 클릭으로 수신 해제.");
  s.addText("+ 브랜드를 Tessera → Convt 로 리브랜딩하고 convt.xyz 도메인·이메일을 연결했습니다.", { x: 0.6, y: 6.65, w: 11.8, h: 0.35, fontFace: FONT.sans, fontSize: 11, italic: true, color: C.ink500, margin: 0 });
  foot(s, 3, "출시 내역");
}

// ───────────────────────── Slide 4 — Lessons / case studies ────────────────
{
  const s = base();
  eyebrow(s, "케이스 스터디 — 우리가 배운 것");
  headline(s, [
    { text: "버그가 제품을 ", options: { color: C.ink900 } },
    { text: "더 단단하게", options: { color: C.coral600, italic: true } },
    { text: " 만들었습니다.", options: { color: C.ink900 } },
  ]);
  subtitle(s, "기술적 디테일보다 패턴이 중요합니다 — 같은 종류의 실수가 반복되지 않도록 시스템으로 막았습니다.");

  const x1 = 0.6, x2 = 6.85, y1 = 2.85, y2 = 4.75, cw = 5.85, ch = 1.75;
  card(s, x1, y1, cw, ch, C.coral500, "조용한 실패가 1등 적", "에러 없이 '빈 결과'가 나오면 성공처럼 보입니다. 모든 침묵을 경보로 바꿔서, 문제를 며칠 뒤가 아니라 즉시 잡습니다.");
  card(s, x2, y1, cw, ch, C.sage500, "표는 Cathie, 차트는 Warren", "같은 데이터인데 두 화면이 달랐습니다. 화면마다 따로 계산하지 말고, 기록(이벤트 로그) 한 곳에서 다시 계산하도록 통일.");
  card(s, x1, y2, cw, ch, C.plum500, "로컬은 멀쩡, 운영만 깨짐", "환경마다 데이터 형식이 미묘하게 달랐습니다(날짜). '내 PC에선 됐는데'를 막으려면 경계에서 형식을 고정해야 합니다.");
  card(s, x2, y2, cw, ch, C.ink900, "AI가 규칙을 계속 어김", "말로 시킨 한도를 AI가 무시하곤 했습니다. 부탁이 아니라 시스템 단의 '게이트'로 강제해야 안전이 보장됩니다.");
  foot(s, 4, "케이스 스터디");
}

// ───────────────────────── Slide 5 — Where we are / next ────────────────────
{
  const s = base();
  mosaic(s);
  eyebrow(s, "현재 위치 · 다음");
  headline(s, [
    { text: "페이퍼로 ", options: { color: C.ink900 } },
    { text: "라이브", options: { color: C.coral600, italic: true } },
    { text: ". 다음은 사람을 모읍니다.", options: { color: C.ink900 } },
  ]);
  subtitle(s, "Phase D 완료 + convt.xyz 오픈. 제품은 살아 있고, 실제 돈은 아직 쓰지 않습니다(법률 검토가 게이트).");

  const items = [
    ["지금", "친구·가족 실사용자 온보딩 시작 — 각자 다른 애널리스트를 팔로우", C.coral500],
    ["쌓는 중", "몇 주간 실제 페이퍼 트랙레코드 관찰 — \"AI 애널리스트가 정말 통하는가\"의 증거", C.sage500],
    ["다음", "트랙레코드가 쌓이면 확대. 실거래는 항상 법률 검토 뒤 — 함부로 켜지 않습니다", C.plum500],
  ];
  let y = 3.45;
  items.forEach(([t, b, c]) => {
    s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y, w: 0.22, h: 0.22, fill: { color: c }, line: { color: c } });
    s.addText(t, { x: 1.0, y: y - 0.07, w: 2.4, h: 0.4, fontFace: FONT.serif, fontSize: 17, color: C.ink900, margin: 0 });
    s.addText(b, { x: 3.3, y: y - 0.07, w: 9.0, h: 0.7, fontFace: FONT.sans, fontSize: 12.5, color: C.ink600, margin: 0, lineSpacingMultiple: 1.08 });
    y += 1.05;
  });
  foot(s, 5, "로드맵");
}

pres.writeFile({ fileName: "decks/convt-phase-d.pptx" }).then((n) => console.log("Wrote:", n));
