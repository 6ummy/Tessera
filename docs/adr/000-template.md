<!--
  Filename convention:  NNN-short-kebab-title.md
  N starts at 001. Pick the next unused number.

  Copy this file, then fill the sections below.
  Aim for 1–2 pages when done. ADRs > 5 pages don't get read.
-->

# ADR-NNN: <Short imperative title>

| | |
|---|---|
| **Status** | Proposed |
| **Date** | YYYY-MM-DD |
| **Authors** | @github-handle (역할), ... |
| **Tracks affected** | LLM \| Frontend \| Quant \| Infra \| Persona Voice |
| **Supersedes** | — (or `ADR-NNN`) |
| **Related** | `Plan.md` §_, `architecture.md` §_, PR #__ |

---

## Context

<!--
  무엇이 문제이고 왜 지금 결정이 필요한지. 2–4 단락.

  배경 정보:
  - 어떤 상황에서 이 결정이 필요해졌나
  - 어떤 제약조건이 있나 (비용, 시간, 기술적 한계, 규제)
  - 이전에 관련된 시도/실패가 있었으면 언급
  - 측정 가능한 사실 위주로 (의견은 다음 섹션에서)
-->

## Decision

<!--
  무엇을 결정했는지. 한 문단으로 명확하게.

  좋은 형식:
    "We will [action] to [achieve outcome]."

  예시:
    "We will store both numerical features and persona memory embeddings in
     the same Neon Postgres instance (Timescale + pgvector extensions) rather
     than maintaining separate time-series and vector databases."
-->

## Alternatives Considered

<!--
  최소 2개. 각각 왜 reject했는지.

  ### Alt 1: <옵션 이름>
  - 어떻게 작동하나
  - 장점 1–2개
  - 거절 이유 1–2개

  ### Alt 2: <옵션 이름>
  ...

  이 섹션이 ADR의 진짜 가치. "왜 이거 안 했나?"가 6개월 뒤 가장 자주 받는
  질문이고, 여기에 답이 있으면 같은 토론을 반복할 일이 없음.
-->

## Consequences

<!--
  Trade-offs 솔직하게. Positive + Negative + Neutral.

  ### Positive
  - ...

  ### Negative
  - ...

  ### Neutral / 관찰할 것
  - 새로 모니터링해야 할 metric
  - 6개월 뒤 재평가할 신호
  - 이 결정이 다음에 영향 주는 부분
-->

## Verification

<!--
  이 결정이 잘 작동하는지 어떻게 알 수 있는가.
  비어둘 수도 있지만 가능하면 측정 가능한 신호 1–2개.

  예시:
  - LLM 비용 < $300/mo for 30 consecutive days
  - schema validation failure rate < 2% in 30-day backtest
  - persona voice eval set pass rate > 80% on every PR
-->

## Notes / Open Questions

<!--
  미해결 부분. 미래의 reader가 이걸 보고 "아 이게 결정 못 한 부분이구나" 알 수 있게.

  - 예: "Cathie의 spot crypto allocation은 이번 ADR 범위에서 빼고, Phase B
    데이터 본 후 ADR-008에서 따로 결정."
-->
