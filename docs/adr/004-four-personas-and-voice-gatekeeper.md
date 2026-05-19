# ADR-004: Four personas (Warren / Cathie / Ray / Peter) + single voice gatekeeper

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-18 |
| **Authors** | @6ummy |
| **Tracks affected** | Persona Voice (primary), LLM Pipeline, Frontend |
| **Supersedes** | — |
| **Related** | `personalities.md`, `.github/CODEOWNERS` (`personalities.md @6ummy`), `architecture.md` §5 |

---

## Context

Tessera의 **핵심 product premise**는 "여러 명의 AI analyst가 서로 다른 투자
철학으로 같은 시장을 다르게 해석한다"입니다. 이 premise가 작동하려면 두 가지
질문에 답해야 합니다:

1. **몇 명의 페르소나를 둘 것인가?** (1 vs 4 vs 8 vs 20)
2. **누가 페르소나 voice를 결정/유지하는가?** (single owner vs 분산 vs 사용자 정의)

너무 적으면 "왜 multi-persona 컨셉인가?"가 약함. 너무 많으면 voice drift / 비용 / 변별력 문제. 분산 ownership은 일관성 깨짐. 모두 결정의 trade-off.

## Decision

### 페르소나 수: **4명**

| Persona | Archetype | 핵심 lens |
|---|---|---|
| **Warren** (67) | Value | FCF yield > 6%, 5+ year hold, 명료한 비즈니스 |
| **Cathie** (32) | Disruptive Growth | AI/robotics/crypto infra, 2030 P&L 기준, 시나리오 가중 |
| **Ray** (58) | Macro Hedger | regime probability (2×2 grid), asset-class allocation만 |
| **Peter** (44) | GARP | PEG < 1.2, EPS CAGR 15–25%, "walk the aisle" |

각 페르소나는:
- `personalities.md`에 600줄 짜리 spec (Identity / Mental model / Voice rules / Hard rules / Output schema / Chat fine-tuning specs)
- 고유 photo, 나이, 배경, 직업 history, 가족, hobby — 일관된 character
- 의도적으로 disagree하도록 설계 — 같은 NVDA earnings에 Warren(Hold), Cathie(Add), Ray(N/A), Peter(Hold-with-trigger)

### Voice ownership: **정우(@6ummy) 단독 gatekeeper**

`personalities.md`는 CODEOWNERS에서 `@6ummy` 단독 owner.
- 다른 사람이 PR 보낼 수는 있음 (voice 개선 제안)
- 머지는 **정우만** approve 가능
- "Voice consistency requires a single decision-maker; everyone else proposes via PR but only 정우 can approve."

## Alternatives Considered

### Alt 1: 2명 페르소나만 (Warren + Cathie)
가장 미니멀. Value vs Growth라는 핵심 dichotomy.
- **거절 이유**:
  - "Multi-persona"의 가치가 약함 — 2명은 그냥 양극이지 "데스크"가 아님
  - Ray의 macro lens가 빠지면 portfolio가 단일 자산군에 너무 노출
  - Peter의 GARP가 빠지면 중간지대 (compounders) 커버리지 0
  - 비용 절감은 미미 — Phase A 데이터로 보면 4명도 월 $60–280 충분히 감당

### Alt 2: 8+ 명 페르소나 (international, sector specialists, quant, etc.)
풍부함 + 다양성.
- **거절 이유**:
  - **Voice drift 위험 8배 증가** — 8명의 voice를 한 명의 gatekeeper가 일관되게 유지 어려움
  - LLM 비용 2배 (daily batch)
  - User cognitive overhead — "어느 분석가 follow할지" 결정이 어려워짐 → choice paralysis
  - UI 부담 — 4명도 marketplace grid에 적당, 8명 되면 sub-categorization 필요

### Alt 3: 사용자 정의 페르소나 (user-generated)
"내가 직접 페르소나를 만든다."
- **거절 이유**:
  - Voice 품질 통제 불가 — 사용자가 만든 페르소나가 떨어지면 platform 전체 신뢰도 손상
  - Compliance 위험 — 사용자가 만든 페르소나로 personalized advice 정황 발생 (RIA 등록 trigger)
  - 파일럿 phase엔 시기상조 — 4 base persona로 product-market fit 검증부터
  - 미래 가능성 — fork/customize 기능은 Phase 4+ 옵션

### Alt 4: 분산 voice ownership (4명 owner가 각자 자기 페르소나 관리)
- 각 owner가 도메인 전문성을 살릴 수 있음
- bottleneck 제거
- **거절 이유**:
  - **voice cross-pollination 위험** — 한 사람이 Warren spec 손대면 Warren 색이 흐려지는데, 그 사람이 동시에 Cathie도 손대면 두 voice 사이 경계가 모호해짐
  - 페르소나 spec은 **product design decision** — UI 색깔 결정처럼 한 명의 일관된 시각이 필요
  - Backstory + voice + hard rules가 서로 얽혀 있어 일부만 바뀌면 모순 (예: Warren에게 "be more aggressive" 추가했다가 5+ year hold 규칙과 충돌)

## Consequences

### Positive
- **명확한 책임** — voice 관련 모든 결정의 single source of truth (정우)
- **변별력** — 4명 voice가 명확히 다르고, 측정 가능 (chat eval, thesis sample)
- **확장 가능** — 향후 페르소나 추가 시 같은 패턴 (정우가 voice approve)
- **유저에게 인지적으로 manageable** — 4명 사진 + 짧은 태그라인 한 화면에 들어옴
- **CODEOWNERS로 자동 강제** — 다른 사람이 personalities.md 머지 못 함

### Negative
- **Gatekeeper bottleneck** — 정우 못 들어오면 voice 변경 다 정지. 미티게이션: 큰 voice 변경은 드물고, 작은 typo는 docs PR로 처리.
- **정우의 voice 편향이 4명 전체에 반영** — voice는 결국 한 사람의 design 감각. 4명이 의도된 만큼 다르지 않을 수도. 미티게이션: voice eval set으로 chat 응답 random sample 검토, 다양성 score 측정.
- **자기 personalities.md PR 머지 못 함** (정우가 author면 self-approve 불가) — 매번 admin bypass 또는 owner 추가 필요.

### Neutral / 관찰할 것
- 페르소나 추가 (5번째? 6번째?) — 사용자 follow 분포 보고 결정. Phase D 데이터 활용.
- Voice drift 모니터링 — 분기별로 random sample 10개 thesis 본인이 직접 읽고 "Warren 같음? Cathie 같음?" 라벨링. confusion matrix가 단순 베이스라인 이상이면 OK.
- 외부 사용자가 fork 요청하면 — 그건 별도 ADR로 결정 (현재 backlog).

## Verification

- ✅ `personalities.md`에 4 페르소나 각 600줄 spec 작성 완료
- ✅ CODEOWNERS에 `personalities.md @6ummy` 명시
- ✅ Branch protection으로 다른 사람 머지 차단 확인 (Phase A 직접 테스트)
- 미래 (Phase B): voice eval set 작성 — 페르소나별 known-good thesis 10개. PR이 spec 건드릴 때마다 regression 자동 측정.
- 미래 (Phase D): 사용자 follow 분포 측정 — 한 페르소나가 80%+ 차지면 다른 페르소나 voice 재고.

## Notes / Open Questions

- **5번째 페르소나 후보**: "Mara" (Senior Manager) — 4명 thesis를 큐레이션해 Cons/Bal/Aggr 3개 portfolio 제안. 원래 architecture에 있었으나 현재 product에선 빠짐. 사용자 수 > 20 시점에 재검토 (`Plan.md` Open Decisions).
- **Cathie crypto 노출**: 현재 equity proxy (COIN, MSTR)만. spot BTC/ETH는 Coinbase OAuth + 추가 disclosure 필요 — ADR-XXX에서 결정.
- 정우 외 voice "deputy" 추가 옵션 — 한솔 또는 한 명을 backup voice reviewer로 — 정우 부재 시 emergency PR 처리. 현재 운영 약속만으로 (정우 항상 reachable 가정).
