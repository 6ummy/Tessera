# ADR-005: Hallucination defense — LLM writes narrative, Python computes numbers

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-18 |
| **Authors** | @6ummy |
| **Tracks affected** | LLM Pipeline, Quant, Persona Voice |
| **Supersedes** | — |
| **Related** | `architecture.md` §2 principles, `Plan.md` §11 Risk Register #11, `apps/worker/tessera_worker/features/compute.py`, `packages/shared/tessera_shared/schemas.py` |

---

## Context

LLM은 숫자 산수에서 hallucinate합니다 — "AAPL 30일 수익률은 +12%였다"라고
확신에 차서 답하지만 실제는 −3%일 수 있습니다. 금융 product에서 이런 일이
발생하면:

- 사용자에게 잘못된 thesis가 풀이됨
- Risk gateway가 invented 가격으로 paper trade 체결
- 페르소나의 신뢰도 영구 손상

전통적 대응법:
- **LLM 출력 post-validate** — LLM이 가격 말한 후 우리가 DB랑 비교 (느림, 일부 케이스 놓침)
- **LLM에게 raw data 다 주고 "정확히 계산해"** — 더 hallucinate
- **LLM 안 쓰고 quant model만** — voice 못 만들고 narrative 손실

우리는 다른 길을 택했습니다.

## Decision

**역할을 split.** LLM은 *narrative*, Python은 *numbers*.

### LLM이 받는 것 (input)
- **사전 계산된 numerical features**: `ret_1d`, `ret_30d`, `fcf_yield`, `peg`, `rsi_14`, `vol_30d` 등이 이미 Python에서 계산된 dict
- **raw text**: 뉴스 본문, earnings call transcript, 10-K 본문 발췌 — 그대로 흘러감 (LLM의 행간 읽기 능력 보존)
- **persona memory recall**: pgvector로 surfaced된 과거 thesis 텍스트

### LLM이 안 받는 것
- Raw OHLCV CSV
- 가격 계산이 필요한 어떤 형태든

### LLM이 출력하는 것
- **structured JSON** — Pydantic schema 강제 (`AnalystReport`, `Proposal`, `RegimeProbabilities`)
- `target_weight`, `conviction`, `horizon_days` 같은 숫자 필드 — **하지만 모두 type + range constraint**
- `cited_news_ids` — UUID 리스트, 모두 DB의 실제 row를 가리켜야 함

### 검증 단계 (LLM 출력 → main DB 사이)
1. **Pydantic schema validation** — 실패 시 1회 retry, 재실패 시 drop + 알림
2. **Universe check** — `ticker`가 universe.py에 존재하는지
3. **Citation check** — `cited_news_ids`가 `news` 테이블에 실재하는지 (가짜 ID 0%)
4. **Risk gateway** (pure Python) — weight cap, sector cap, VaR budget. **LLM이 우회 불가**.

### Feature builder (numbers의 single source of truth)

`apps/worker/tessera_worker/features/compute.py` — 결정론적 pandas/numpy.
- `ret_*`, `vol_30d`, `rsi_14`, `sma_*`, `volume_z` 등 계산
- Property-based tests 13개 (hypothesis) — RSI ∈ [0,100], vol ≥ 0, SMA가 rolling min/max 사이 등
- Canary asserts — SPY 1y return이 Yahoo와 100 bps 이내 (실측 0.49 bps)
- 모든 숫자는 여기에서 옴 → LLM은 받기만

## Alternatives Considered

### Alt 1: LLM에게 raw OHLCV CSV 주고 "정확히 계산해" prompt
- 가장 간단한 접근
- **거절 이유**: LLM은 산수에서 hallucinate. 검증된 fact. 우리 use case 1번 시도하면 1번 실패.

### Alt 2: LLM 출력 후 우리가 cross-check
- LLM이 가격 답하면 → 우리가 같은 시점 DB 가격이랑 비교 → 다르면 거부
- **거절 이유**:
  - LLM 출력 ↔ DB 검증이 fuzzy (소수점, timezone, adjustment 등) — false positive 많음
  - 검증 통과한다고 정확한 게 아님 — 약간 다른 수치는 "비슷하니까 OK?" 모호함
  - Pre-compute 방식이 더 깨끗 (LLM이 잘못 알 기회 자체 없음)

### Alt 3: LLM도 numbers 만지게 하되, 출력에서만 Pydantic 강제
- Pydantic이 type + range는 잡지만 *내용*은 못 잡음. "AAPL ret_30d = +12%" 같은 거짓도 type 통과.
- **거절 이유**: 우리가 막고 싶은 건 type 오류가 아니라 잘못된 사실 출력. Pydantic만으론 부족.

### Alt 4: 완전 quant (LLM 안 씀)
- factor model + ML로 신호, 사람이 narrative 작성
- **거절 이유**: Tessera의 핵심 가치 = AI persona가 thesis를 쓴다. LLM 빼면 product 자체가 사라짐.

### Alt 5: OpenAI / Anthropic의 "tool use" 강제 (LLM이 우리 함수 호출해서 숫자 얻음)
- LLM이 `get_ret_30d(AAPL)` 같은 함수 호출, 우리가 답 줌
- **거절 이유**:
  - 우리 패턴과 거의 동등하나 latency가 늘어남 (LLM 호출 안에 추가 round-trip)
  - 호출 횟수 unbounded → 비용 예측 불가
  - 사전 계산은 그냥 prompt에 박는 게 더 단순 + 빠름 + 저렴

## Consequences

### Positive
- **Hallucinated ticker 0건 보장** — Risk gateway가 universe.py 외 ticker reject
- **Invented 가격 불가능** — LLM이 가격 받을 일 자체가 없음
- **재현 가능** — 같은 feature snapshot → 같은 thesis (modulo LLM nondeterminism, 작음)
- **Audit trail** — `analyst_reports`에 `inputs_hash` 저장. 잘못된 thesis 발생 시 input 그대로 replay 가능
- **Feature builder가 single source of truth** — 1곳만 검증 (property test + canary) → 전체 시스템 신뢰

### Negative
- **Pre-computation 비용** — Phase A에서 13,983 feature row 계산 ~8초. 미래 universe 500개 + 5년 데이터로 늘면 더 비싸짐.
- **새 feature 추가 friction** — LLM이 "PEG 보고싶다" → Quant 트랙이 PEG 계산 추가 → schema migration → property test → 그 다음에야 LLM이 사용. 빠른 실험엔 부담.
- **Feature schema가 모든 페르소나 prompt와 강결합** — feature 이름 바꾸면 4 페르소나 spec 다 업데이트 필요

### Neutral / 관찰할 것
- **Mode collapse** — Pydantic이 `target_weight: float = Field(ge=0, le=0.20)` 으로 강제하면 LLM이 cap 근처(17–18%)에 anchoring할 위험 (Risk Register #13). Phase C에서 weight distribution 모니터링 → 발생 시 conviction-only schema로 refactor (ADR-XXX 예정).
- **Feature가 너무 적으면 LLM이 narrative만으로 weak conclusion** — 추가 feature 필요 시점 모니터링.

## Verification

- ✅ Phase A SPY canary: ret_1y = +26.6254% vs Yahoo +26.6205% → **0.49 bps**. Threshold 100 bps. 통과.
- ✅ 13 property tests pass (hypothesis): RSI bounded, vol non-negative, SMA within window min/max 등
- ✅ feature builder idempotent: 13,983 rows 재계산 시 동일
- 미래 (Phase B): 30일 backtest 동안 hallucinated_ticker count = 0. schema validation failure rate < 2%.

## Notes / Open Questions

- **conviction-only schema 전환** (Risk #13 mitigation): Phase C에서 weight bimodality KL test 결과 보고 결정. 별도 ADR-008로 기록 예정.
- **Tool use가 미래에 의미 있어지는 시점** — LLM이 "이 ticker의 5년 dividend history 보고싶다" 같은 ad-hoc query 필요 시. 현재는 사전 계산 feature로 충분.
- **Embedding fact-check** — Phase B 추가 가능: LLM의 thesis text를 다시 LLM에 넣어 "이 thesis가 cited 데이터와 일치하는가?" semantic check. 비용 vs 효과 미정.
