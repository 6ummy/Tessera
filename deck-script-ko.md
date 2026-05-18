# Tessera 기술 발표 스크립트

> AI 스터디 그룹 발표용. 17 슬라이드, 약 32–37분.
> 영어 기술 용어는 원문 유지. 친근한 발표 톤.

---

## Slide 01 — Title

안녕하세요. 오늘 발표할 프로젝트는 **Tessera**라고 하는, multi-agent LLM 기반 research desk입니다.

한 문장으로 설명하면 — 서로 다른 투자 철학을 가진 네 명의 AI analyst persona가 매일 시장을 읽고, 각자의 thesis를 작성해서, 사용자가 그걸 비교해서 따라가는 long-term 투자 플랫폼입니다.

오늘은 마케팅적인 얘기보다는 **어떻게 만들었는가**에 집중하려고 합니다. 데이터를 어떻게 가져오는지, persona를 어떻게 정의하는지, LLM call이 어떻게 흘러가는지, brokerage API를 어떻게 연동하는지, 그리고 미국에서 이런 서비스를 할 때 compliance적으로 뭘 조심해야 하는지까지.

레포는 `github.com/6ummy/Tessera`에 올라가 있습니다. 발표 끝나고 보셔도 됩니다.

---

## Slide 02 — Agenda

오늘 다룰 8가지 토픽입니다.

1. **System architecture** — 왜 세 개의 plane으로 나눴는지
2. **Stack** — 각 도구를 왜 선택했는지
3. **Data ingestion** — 어떤 API에서 뭘 가져오는지
4. **Hallucination defense** — 이 시스템의 가장 중요한 design choice
5. **Persona spec design** — system prompt를 어떻게 구조화했는지
6. **Same data, four readings** — 같은 데이터를 네 명이 어떻게 다르게 해석하는지
7. **LLM call pipeline** — Haiku → Sonnet → Pydantic → citation check까지
8. **Execution + compliance** — Alpaca OAuth, paper/live flag, kill switch, 그리고 미국 규제

발표 중간에 질문 있으시면 끊어 주세요.

---

## Slide 03 — System Architecture

전체 시스템은 세 개의 plane으로 구성됩니다. **strict하게 한 방향으로만 데이터가 흐릅니다.** 위 plane이 아래 plane으로만 데이터를 보내고, backward call은 없습니다. 덕분에 failure가 isolate되고, pipeline을 언제든지 replay할 수 있습니다.

- **Data Plane** — Alpaca, Coinbase, FMP, SEC EDGAR, FRED, NewsAPI, Reddit 같은 소스에서 raw data를 가져와서 Neon Postgres에 저장합니다. Embedding까지 미리 만들어 둡니다.

- **Agent Plane** — 4명의 persona가 병렬로 돌면서 thesis를 씁니다. Haiku 4.5로 universe를 일차 screening하고, 통과한 종목만 Sonnet 4.6으로 deep analysis합니다. 출력은 Pydantic schema로 validate합니다. pgvector로 과거 thesis를 recall해서 일관성을 유지합니다.

- **Decision + Execution Plane** — LLM이 만든 결과를 결정론적인 Python 코드가 검증합니다. ticker가 실재하는지, weight cap을 안 넘는지, VaR 예산 안인지. 통과한 것만 paper engine, 또는 Alpaca live adapter로 흘러갑니다.

핵심은 **LLM은 plan을 짜고, Python이 dispose한다**는 점입니다.

---

## Slide 04 — Stack

스택 선택은 한 마디로 "**boring choices on purpose**"입니다. 새로운 거 쓰고 싶은 욕심을 참았습니다.

- **Frontend** — Next.js 14 App Router + Vercel + Tailwind + Recharts. Vercel은 zero-config로 deploy되고 미국 리전이 default라 latency도 괜찮습니다.

- **Auth + realtime** — Firebase Auth + Firestore + FCM. 직접 auth 짤 일을 0으로 만들어 줍니다. Firestore의 client-side subscription으로 portfolio가 바뀌면 브라우저가 알아서 re-render됩니다.

- **Agents + batch** — Cloud Run Jobs로 LLM batch를 돌립니다. Scale-to-zero라 평소엔 돈이 안 듭니다. Firebase랑 같은 GCP project 안이라서 IAM도 한 군데서 관리됩니다. Orchestration은 LangGraph, model은 Anthropic Claude (Haiku, Sonnet, Opus).

- **Data + state** — Neon Postgres에 TimescaleDB extension으로 OHLCV hypertable을, pgvector로 persona memory를 둡니다. DB 하나로 시계열·벡터·ledger 다 처리합니다.

- **Brokerage** — Alpaca. 미국 stock과 crypto를 같은 API로 처리할 수 있습니다. OAuth만 쓰고, user의 broker credential은 절대 우리가 안 만집니다.

- **Ops** — Sentry + Grafana Cloud free. 파일럿 단계라 이 정도면 충분합니다.

---

## Slide 05 — Data Ingestion

장기 투자라서 **fundamental 데이터가 dominant**합니다. 분봉 tick data 같은 건 안 가져옵니다.

테이블을 보시면 — Alpaca랑 Coinbase는 EOD candle만 daily로. FMP는 분기 재무제표 5년치. SEC EDGAR에서 10-K, 10-Q, 8-K 본문을 그대로 받아서 Postgres에 저장하고 원본 HTML은 GCS에 백업합니다. FRED에서 yield, CPI, 고용지표 등 약 20개 macro series를 가져옵니다. 뉴스는 NewsAPI랑 Reddit에서 hourly batch로 ticker별로 묶어서 embedding까지 만들어 둡니다.

여기서 한 가지 중요한 design choice — **raw row는 다 보존**하지만, LLM은 raw row를 절대 보지 않습니다. Returns, RSI, FCF yield, PEG, regime probability 같은 **pre-computed feature**가 따로 `ticker_features` 테이블에 들어가고, LLM은 그것만 읽습니다. 이게 다음 슬라이드의 hallucination defense로 이어집니다.

---

## Slide 06 — Hallucination Defense

이 슬라이드가 오늘 발표의 가장 중요한 부분입니다.

**Naive pattern** — LLM한테 raw OHLCV를 던지고 "momentum 계산해서 0–20% 사이로 allocate해" 라고 시키는 방식. 문제는, model이 ret_30d를 +12%라고 invent하는 순간 끝납니다. 실제는 −3%였는데. 환각된 signal로 18% 포지션이 production까지 가버립니다.

**Tessera pattern** — `compute_features("AAPL")`라는 Python 함수가 pandas로 먼저 계산합니다. `{ret_30d: -0.031, rsi: 42, fcf_yield: 0.041, peg: 1.8, pe_fwd: 28.2}` 이런 dict가 나옵니다. 그 dict를 prompt에 박아서 LLM한테 줍니다. "이 숫자들을 보고 thesis를 작성해, 이 schema대로 JSON을 출력해."

결론은 — **LLM은 narrative만 자유롭게 쓰고, 숫자는 절대 건드리지 않는다.** Wrong ticker나 fake citation도 downstream에서 reject됩니다. 이건 다음에 자세히 보겠습니다.

---

## Slide 07 — Persona Spec Design

각 persona는 결국 **tightly-specified system prompt**입니다. 600줄 정도 됩니다. 6개 섹션으로 구성돼요.

1. **Identity** — 이름, archetype, 배경, 보는 관점
2. **Mental model** — persona가 적용하는 deterministic framework. 예를 들어 Warren은 "내가 이해할 수 있는가, moat가 있는가, management가 정직한가, 가격이 맞는가" 4-question filter를 씁니다.
3. **Inputs** — persona가 받게 될 pre-computed feature의 schema
4. **Voice rules** — 톤, 사용 금지어, 포맷 제약. Warren은 "asymmetric", "disruptive", "TAM" 같은 단어를 절대 못 씁니다.
5. **Hard rules** — 절대 어기면 안 되는 행동. Warren은 `what_would_make_me_wrong` 필드가 없으면 proposal 자체를 못 만듭니다.
6. **Output schema** — Pydantic으로 validate하는 JSON 모양. ticker, target_weight, horizon_days, cited_news_ids, what_would_make_me_wrong 등 모든 field가 typed입니다.

오른쪽이 Warren spec의 일부 발췌입니다. `target_weight: float = Field(ge=0, le=0.18)` — 0–18% 사이를 강제로 enforce합니다. 18%를 넘으면 Pydantic이 reject합니다.

전체 spec은 repo의 `personalities.md`에 있습니다. 코드와 함께 version 관리됩니다.

---

## Slide 08 — The Four Lenses

이게 핵심 비교 표입니다. 네 명이 **같은 시장 데이터**를 보지만, 적용하는 filter가 다 다릅니다.

- **Warren** (Value, 67세) — FCF yield 6% 넘는 것만. 7–12 종목 집중. turnover 15% 미만. 매크로, 모멘텀, IPO 다 무시. 단일 종목 18% cap.

- **Cathie** (Disruptive, 32세) — 2030년 P&L 기준 bear/base/bull scenario. 15–25 종목, turnover 60–90%로 회전 빠름. trailing P/E랑 gross margin compression 무시. 단일 종목 16% cap.

- **Ray** (Macro, 58세) — 단일 종목 picking 안 함. asset class 단위로 regime probability에 따라 allocate. 8–14 ETF만. 단일 instrument 35%까지.

- **Peter** (GARP, 44세) — PEG 1.2 미만 + EPS CAGR 15–25%. 12–20 종목. turnaround랑 story stock 무시. 단일 종목 13% cap.

**같은 NVDA earnings release를 받아도** 이 네 명은 다른 결론에 도달합니다. 그게 다음 슬라이드에서 보여드릴 핵심 가치입니다.

---

## Slide 09 — Same Data, Four Readings

NVDA Q3 2026 가상 release를 예시로 들어 보겠습니다. 네 명 모두 위의 동일한 feature snapshot을 받습니다. ret_30d +8.2%, fcf_yield 1.8%, pe_fwd 38, eps_cagr_3y +42%, inference_share_yoy +55%, peg 0.9, news_sentiment +0.41. 똑같습니다.

각자 어떻게 반응할까요?

- **Warren — HOLD · 0%** — "FCF yield 1.8%는 내 bar의 절반이다. 5-year hold를 underwrite할 수 없다. Watch만 하고, FCF yield가 5% 넘거나 35% drawdown이 오면 재진입."

- **Cathie — ADD · 14%** — "inference share YoY +55%가 bull thesis를 validate한다. Bear(sovereign capex pause)는 −30%, base는 2.5배, bull은 4배. asymmetry에 맞춰 sizing — 200bps 추가."

- **Ray — N/A** — "단일 종목은 내 desk가 아니다. 다만 AI capex strength가 growth quadrant probability를 3pp 끌어올렸고, 그게 equity tilt를 지지한다는 거 정도만 노트한다."

- **Peter — HOLD · 7%** — "PEG 0.9는 GARP스럽지만 gross margin yoy가 decelerating이다. Add trigger는 margin이 stable해지면서 EPS revision이 올라갈 때. Trim trigger는 두 분기 연속 margin contraction."

이게 Tessera의 핵심 가치입니다. 같은 데이터에 대한 4개의 **independent reasoned reading**. 평균을 내거나 합치는 게 아니라, 사용자가 자기랑 맞는 lens 하나를 골라서 따라가는 구조입니다.

---

## Slide 10 — LLM Call Pipeline

LLM call은 persona 한 명당 daily batch 한 번씩 돌립니다. 5 stage로 구성됩니다.

1. **Universe screen** — Haiku 4.5. 약 500개 universe에서 persona별로 top 30개 정도만 추립니다. 호출당 약 $0.005.
2. **Thesis writeup** — Sonnet 4.6. 추려진 종목에 대해 deep analysis. 호출당 약 $0.045.
3. **Schema validate** — Pydantic. type check, range check. 실패하면 1회 retry, 그래도 실패하면 drop. 비용 0.
4. **Citation check** — Python. 인용한 news_id가 실제 news 테이블에 존재하는지 확인. fake citation은 silent하게 제거. 비용 0.
5. **Risk gateway** — Python. weight cap, sector concentration, VaR budget. 비용 0.

**Daily 합계** — 4 persona × (1 Haiku + 약 20 Sonnet) ≈ 80 LLM call. 약 $1.20/일이 thesis batch 비용입니다. Chat baseline 포함해서 $1.50/일 정도.

**Prompt caching이 큰 lever입니다.** persona spec이 3K token 정도 되는데, 이걸 5분 TTL ephemeral cache로 처리하면 cache read는 0.1배 가격이 됩니다. caching 안 켜면 LLM 비용이 5–10배 차이 납니다.

---

## Slide 11 — Surfacing to User

LLM 결과가 어떻게 사용자한테 도달하는지 — 5 단계 flow입니다.

`Cloud Run batch job → INSERT INTO analyst_reports (Neon Postgres) → Trigger function이 Firestore로 push → Firestore realtime client subscription → Browser가 portfolio card를 re-render` (refresh 없이).

핵심은 **새로고침이 필요 없다**는 점입니다. 사용자가 dashboard를 띄워 놓고 있으면, batch job이 끝나는 순간 화면이 자동으로 update됩니다. Push notification도 FCM으로 같이 갑니다.

**사용자가 보는 것** — `/proposals`에 4개 portfolio가 side-by-side로 뜹니다. 어떤 종목이든 hover하면 "어느 analyst가 왜 이 weight로 넣었는지" thesis가 보입니다.

**사용자가 할 수 있는 것** — paper로 portfolio 하나를 follow하거나, 특정 analyst와 chat을 열어서 reasoning을 더 파고들 수 있습니다. Phase F에서 live trading이 열리면 Alpaca OAuth로 opt-in.

---

## Slide 12 — Chat with Analyst

Chat은 turn마다 system prompt를 새로 assemble합니다. 6 part로 구성됩니다.

1. **Persona spec** — `personalities.md`에서 로드. caching됨. ~3K token.
2. **Current book** — 그 persona의 오늘 holdings JSON. ~600 token.
3. **Recent reports** — 최근 thesis 3개 요약. ~1K token.
4. **Relevant features** — 사용자가 언급한 ticker의 pre-computed feature. ~400 token.
5. **Conversation history** — 직전 N turn. ~1.5K token.
6. **User message** — 현재 turn. ~50 token.

오른쪽 코드는 Anthropic SDK 호출 예시입니다. `system`에 두 개의 block을 줍니다 — persona spec은 `cache_control: ephemeral`을 붙여서 caching하고, book+reports는 매번 새로 보냅니다.

비용은 메시지당 약 **$0.012** (caching 적용 기준). 사용자가 하루 50개 메시지 쳐도 $0.60/일 수준이라 부담 없습니다.

지금 demo에서는 LLM call이 아니라 keyword-matched mock response로 시뮬레이션하고 있고, 실제 production에서는 이 SDK call 한 줄로 swap만 하면 됩니다.

---

## Slide 13 — Trading Execution

실행 부분은 **adapter pattern**으로 설계했습니다. 왼쪽 코드 보시면 — `ExecutionAdapter`라는 Protocol을 정의하고, `PaperEngine`이랑 `AlpacaLiveAdapter`가 둘 다 구현합니다. feature flag로 `flag(user_id, "live")` 체크해서 둘 중 하나가 활성화됩니다.

핵심은 — **paper랑 live가 같은 code path**를 씁니다. adapter 한 줄만 바뀝니다. 그래서 paper에서 검증된 strategy가 그대로 live로 넘어갈 수 있습니다.

**OAuth flow** — 사용자가 Alpaca를 연결하는 과정입니다.

1. 사용자가 "Connect Alpaca" 클릭
2. Alpaca authorize URL로 redirect
3. 사용자가 **Alpaca 도메인에서** 로그인 (우리가 password 처리 안 함)
4. callback으로 short-lived code 돌아옴
5. 백엔드가 code를 access_token으로 교환
6. token을 Firestore에 encrypted 저장
7. 매 order마다 사용자가 UI에서 confirm해야 실제 전송

**Invariants** — 우리는 어떤 경우에도 (1) custody 안 함, (2) 모든 order에 explicit confirm 받음, (3) kill switch 한 번에 모든 포지션 close 큐잉 (Temporal workflow로), (4) paper/live 같은 code path 유지.

---

## Slide 14 — Risk + Compliance

**Risk gateway** — 왼쪽 코드. validate() 함수가 portfolio를 받아서 4가지 체크합니다.

1. 모든 ticker가 universe 안에 실재하는지 (hallucination 방어)
2. single name cap 안 넘는지 (persona별로 다름)
3. sector concentration 안 넘는지
4. portfolio-level VaR이 budget 안인지

하나라도 실패하면 `Result(ok=False, reasons=...)`를 반환. fail한 portfolio는 사용자한테 절대 노출 안 됨. persona의 trust score만 차감됩니다.

**US regulatory posture** — 오른쪽 표.

- **Paper only, 모든 사용자** — OK. 교육/리서치라 SEC filing 불필요.
- **본인이 자기 자본으로 trade** — OK. advisor 관계 trigger 안 됨.
- **친구·가족이 live trade** — 회색지대. Securities lawyer 30분 상담 필수 (~$300).
- **불특정 다수 public 사용자 live** — 막혀 있음. SEC RIA registration + 주별 Blue Sky filing 필요. 파일럿 scope 밖.

밑에 우리가 절대 안 깨는 invariants — no custody, no personalized advice, no hallucinated ticker, no skipping paper phase, no live order without explicit user confirmation.

---

## Slide 15 — Operational Economics

월 비용 breakdown.

- **LLM Haiku screens** — $15–40
- **LLM Sonnet thesis** — $30–180
- **LLM Chat** (user-driven) — $10–50
- **LLM Opus weekly review** — $5–20
- **Cloud Run + Neon + Firebase** free tier — $0–5
- **Market data** — $0–30

**합계 $60–325/월**. **LLM이 dominant**합니다. 인프라는 사실상 공짜.

가장 중요한 점 — **비용이 사용자 수에 비례하지 않습니다.** Persona 분석은 모든 subscriber가 공유하는 batch라서, 3명이든 300명이든 LLM bill은 같습니다. 사용자가 늘면 늘어나는 건 chat과 push 정도라 marginal cost가 거의 0에 가깝습니다.

비용 줄이는 lever들:
- **Daily → weekly batch** : −60% LLM. 장기 holdings는 매일 update 필요 없음.
- **4 persona → 2 persona** : −50% LLM. MVP는 Warren + Cathie만으로도 충분.
- **Sonnet → Haiku for thesis** : −70%. voice 품질 떨어지지만 trade-off로 OK.
- **Prompt caching always-on** : −40%. 거의 무조건 켜야 함.
- **Opus weekly review skip** : −$15. 간단한 performance 표로 대체.

축소하면 월 $30~80까지 내려갈 수 있습니다.

---

## Slide 16 — Status + Plan

여기까지 시스템 디자인이었고, 이제 **현재 상태와 앞으로 어떻게 갈 건지** 정리하고 마무리하겠습니다.

**왼쪽 — BUILT TODAY.** Frontend MVP는 demo-ready 상태입니다. Next.js 14 + Tailwind + Recharts로 Vercel에 그대로 deploy 가능합니다. 4명의 persona가 photo, bio, system prompt까지 갖춰져 있고, marketplace, proposals, dashboard, how-it-works까지 4개 route 다 있어요. Slide-over detail sheet에서 Thesis와 Chat 사이 toggle도 되고, chat UI는 streaming까지 구현돼 있습니다 — 다만 백엔드는 mock입니다. `personalities.md`는 persona당 600줄 정도로 LLM에 그대로 system prompt로 넣을 수 있는 상태고요.

**PENDING이 무엇이냐 —** 솔직하게 말씀드리면 backend 자체, 실제 LLM call, data ingestion, paper engine, auth, broker connection 다 아직입니다. 화면만 있고 그 뒤가 전부 mock인 상태.

**오른쪽 — PATH TO PRODUCTION. 6주짜리 pilot 계획입니다, paper-first로.**

- **Phase A · wk 1 — Data backbone.** Neon Postgres 셋업, 6개 ingestor (Alpaca, Coinbase, FMP, EDGAR, FRED, NewsAPI), feature builder까지.
- **Phase B · wks 2–3 — Real LLM theses.** Anthropic SDK 연결, Haiku로 universe screen, Sonnet으로 thesis, Pydantic validation. Chat도 mock에서 실제 LLM call로 swap.
- **Phase C · wks 4–5 — Paper execution.** Risk gateway 코드, PaperEngine, daily mark-to-market, 실제 P&L attribution. 이 시점부터 leaderboard에 진짜 Sharpe/MDD가 뜹니다.
- **Phase D · wk 6 — User auth + follow.** Firebase Auth 연결, 3명 friends-and-family onboarding.
- **Phase E · wk 6 (parallel) — Compliance review.** 미국 securities lawyer 30분 상담, 서면 advice 받아서 file.
- **Phase F · wk 7+ — Live trading (optional).** Alpaca OAuth, 본인 먼저 1주 검증. F&F live는 Phase E가 clear해야만 진행.

밑에 보시면 — **MVP done when**: 4명 persona가 매일 real thesis 작성 / 30일 이상 paper P&L track / 3명 F&F active / lawyer advice on file / 월 비용 $200 미만 안정화.

원래는 12주 계획이었는데 절반으로 압축한 버전입니다. **scope를 줄이지 dates를 늦추지 않는 게** 원칙이에요 — 각 phase의 "compression note"에 뭘 cut했는지 명시돼 있습니다 (예: social feed deferred, voice tuning은 post-launch).

---

## Slide 17 — Closing

여기까지가 Tessera 기술 발표입니다.

- 코드는 `github.com/6ummy/Tessera`
- 시스템 디자인 문서는 `architecture.md`
- 빌드 계획은 `Plan.md` — 6주 phase별 task breakdown까지
- Persona spec은 `personalities.md` — 각 600줄 정도. system prompt 그대로 가져다 쓸 수 있는 형태입니다.

질문 받겠습니다. 코드 fork해서 자기 persona 만들어 보고 싶으시면 환영입니다. 감사합니다.

---

# 발표 팁

- **총 시간 32–37분** 가정 (17 슬라이드). Q&A 별도 10–15분.
- **각 슬라이드 평균 2분.** Slide 6 (hallucination defense), Slide 9 (NVDA example), Slide 13 (trading) 세 곳은 3분씩, Slide 16 (status + plan) 도 3분 정도 쓰는 게 좋음.
- **질문 유도 지점:**
  - Slide 6 끝나고 — "혹시 다른 hallucination 방어 패턴 본 적 있으세요?"
  - Slide 9 끝나고 — "이렇게 4명 의견이 갈리는 게 사용자한테 useful할까요, 아니면 confusing할까요?"
  - Slide 14 끝나고 — "compliance 쪽에서 놓친 게 있으면 알려주세요."
  - Slide 16 끝나고 — "6주 안에 끝낼 수 있을까요? 어디서 막힐 것 같으세요?"
- **시간 부족할 때 skip 가능한 순서:** Slide 15 (cost) → Slide 4 (stack) → Slide 11 (surfacing). 6, 7, 8, 9, 16은 절대 빼지 말 것.
- **Demo 가능하면:** Slide 5 (data 보여줄 때) repo의 `personas` 페이지 띄워서 4명 카드 보여주기. Slide 9 (NVDA) 끝나고 `/proposals` 페이지로 가서 실제 4-portfolio side-by-side 보여주면 강력.
