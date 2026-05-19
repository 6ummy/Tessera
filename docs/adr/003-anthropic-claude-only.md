# ADR-003: Anthropic Claude only (no OpenAI / Gemini / multi-provider)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-18 |
| **Authors** | @6ummy |
| **Tracks affected** | LLM Pipeline, Quant (indirect — cost) |
| **Supersedes** | — |
| **Related** | `architecture.md` §3, `personalities.md` Chat fine-tuning specs |

---

## Context

Tessera는 LLM을 두 곳에서 씁니다:

1. **Thesis batch** (daily) — 페르소나별로 시장 분석 글 작성. Haiku로 universe screening, Sonnet으로 deep thesis, Opus로 weekly meta-review.
2. **Chat with analyst** (on-demand) — 사용자가 페르소나에게 질문하면 streaming 응답.

LLM 공급자 선택은 비용·voice 일관성·기능 측면에서 큰 결정입니다. 옵션은 OpenAI (GPT-4o / 4.1), Google Gemini, Anthropic Claude, 그리고 multi-provider 추상화 (LiteLLM, LangChain) 등이 있었습니다.

## Decision

**Anthropic Claude 단일 공급자.** 모델 계층:

- **Haiku 4.5** — universe screening (저비용 1차 필터)
- **Sonnet 4.6** — 페르소나 thesis 생성, chat 응답
- **Opus 4.7** — 주간 메타리뷰 (페르소나 성과 평가 등)

Anthropic SDK (`anthropic` Python package) 직접 사용. Multi-provider 추상화 도입 안 함.

## Alternatives Considered

### Alt 1: OpenAI GPT-4o / 4.1 단일 공급자
- 가격 비슷, 인지도 높음
- structured output (JSON mode) 기능 있음
- **거절 이유**:
  - Sonnet 4.6의 **prompt caching**이 결정적 — 페르소나 spec 3K 토큰을 5분 TTL ephemeral cache로 처리하면 cache read는 0.1× 가격. 우리 같이 동일 system prompt 여러 번 쓰는 워크로드에선 비용 5–10배 차이. (OpenAI도 caching 있지만 자동, 제어 약함)
  - Voice 일관성 — Claude는 reasoning + narrative 품질이 페르소나 voice 표현에 더 잘 맞음 (주관적 평가, 다만 우리 personalities.md 형식은 anthropic prompt style에 맞춰 설계함)
  - constitutional AI 접근 — 금융 advice 영역에서 OpenAI보다 보수적 응답이 우리 disclaimer 정책과 정렬

### Alt 2: Google Gemini (Pro / Flash)
- 가장 저렴
- 1M+ context window
- **거절 이유**:
  - 우리 prompt는 ~10K 토큰 — long context 이점 없음
  - structured output + tool use가 Claude/OpenAI보다 덜 성숙
  - GCP에 다 묶기 좋은 점이 있지만 — Cloud Run + Vertex AI 통합이 우리 단순한 워크로드엔 over-engineering

### Alt 3: Multi-provider abstraction (LiteLLM / LangChain ChatModel)
- 공급자 lock-in 회피
- A/B 테스트 가능
- **거절 이유**:
  - 추상화 비용 — 새 dependency, 새 학습 곡선
  - Provider-specific 기능 못 씀 (특히 Anthropic prompt caching, OpenAI structured output) — 추상화 layer가 lowest common denominator로 떨어짐
  - 솔직히 자주 swap 안 함. 1년에 한 번 정도 모델 평가하면 충분.
  - 향후 정말 다 공급자 필요해지면 그때 도입 (Anthropic + 다른 1개) — premature.

### Alt 4: Self-hosted (Llama 3.x / DeepSeek)
- 비용 0 (compute 제외)
- 완전한 privacy
- **거절 이유**:
  - GPU 인프라 셋업 + 운영 부담 (vLLM, ray, autoscaling)
  - 작은 팀이 운영하기 비현실적
  - Quality gap — 70B+ open model이 Sonnet 4.6에 근접하지만 prompt engineering이 훨씬 어렵고 voice 일관성 더 떨어짐
  - Tessera는 paper trading pilot — privacy 요구사항이 self-host를 강제할 만큼 강하지 않음

## Consequences

### Positive
- **비용**: 4 페르소나 × daily Sonnet thesis + Haiku screening + chat baseline = ~$60–280/월 (caching on 기준). 매우 합리적.
- **voice 일관성**: 같은 모델 family라 4 페르소나의 voice 변동성이 모델 변경으로 인해 흔들리지 않음. Voice 차이는 system prompt(personalities.md)에서만 옴.
- **prompt caching이 비용 핵심 lever** — `personalities.md` 페르소나 spec을 ephemeral cache 처리로 1/10 비용
- **단순한 SDK** — `anthropic.messages.create(...)` 한 줄. 추상화 layer 없음 → 디버깅 쉬움.
- **Pydantic validation으로 structured output 처리** — 모델이 자유 형식으로 응답하고 우리가 validate. 모든 공급자에서 동작.

### Negative
- **단일 공급자 lock-in** — Anthropic이 가격 인상하거나 모델 deprecate하면 즉시 영향. 다만 Anthropic은 1년 deprecation notice 정책 보장.
- **Anthropic API 장애 시** chat과 daily batch 동시 영향. 미티게이션: batch는 retry로 처리, chat은 friendly "잠시 후 다시 시도" 메시지.
- **모델 비교 실험** — A/B 테스트하려면 별도 코드 작성 필요 (현재 안 함).

### Neutral / 관찰할 것
- 월 LLM 비용 dashboard — $20/일 alert. $50/일 hard limit.
- 모델 deprecation 알림 모니터링 (Anthropic email + changelog).
- 미래 Anthropic 가격 인상 30%+ 시 OpenAI 비교 ADR-XXX 작성하여 재평가.

## Verification

- ✅ Phase A check_connections.py: Haiku reply 'ok', tokens_in=12 tokens_out=4 → ~$0.00007. 작동 확인.
- ✅ 예상 daily 비용: 4 페르소나 × (1 Haiku screen + ~20 Sonnet thesis) = ~$1.20/day. 월 ~$36 + chat baseline.
- 미래: 30일 연속 LLM 비용 < $300/월 유지. Schema validation failure rate < 2%.

## Notes / Open Questions

- **Chat 모델 선택** — Sonnet 4.6 vs 페르소나별 fine-tuned Haiku 결정은 Phase B 끝에 (이 ADR이 아니라 ADR-008 후보) → chat volume > 500/day/persona이면 fine-tune 검토.
- **Anthropic batch API** — 일일 thesis batch에 batch API 쓰면 50% 할인. Phase B에서 검토.
- 12개월 뒤 OpenAI / Gemini 모델 capability 재평가 의무 (calendar reminder).
