# Architecture Decision Records (ADRs)

Tessera에서 비교적 큰 의사결정은 여기에 기록합니다. 한 결정 = 한 파일.

## 왜 ADR을 쓰나

코드는 *무엇을* 했는지 보여주지만 *왜* 그렇게 했는지는 안 보여줍니다.
6개월 뒤 본인 또는 신규 합류자가 "왜 X를 안 쓰고 Y를 썼지?"를 30초 안에
이해할 수 있도록 — 그게 ADR의 목적입니다.

## 언제 ADR을 쓰나 (yes / no)

**쓰자:**
- 스키마/DB 변경 (예: `migrations/003_*`보다 큰 변화)
- 새 도구·서비스 도입 (예: Redis 추가, Vector DB 변경)
- LLM 모델·전략 변경 (예: Sonnet → Opus, conviction-only schema 전환)
- 페르소나 voice 변경 (예: Cathie의 crypto exposure 정책)
- 외부 의존성 변경 (예: Alpaca → IBKR)
- 비용·운영에 영향 큰 결정 (예: free tier → paid tier 전환 시점)

**안 써도 됨:**
- 단순 버그 fix
- 라이브러리 패치 버전 업
- 색상·copy 변경
- typo

기준: "1년 뒤 이걸 왜 그렇게 했지?"를 누가 물을 만한 결정.

## 어떻게 쓰나

1. **번호 다음 거 찾기** — `docs/adr/`의 가장 큰 NNN 다음 번호
2. **파일 만들기** — `docs/adr/NNN-short-kebab-title.md`
3. **`000-template.md` 복사** 후 채우기
4. **PR로 보내기** — 단독 PR 또는 관련 코드 변경과 같은 PR에 포함
5. **머지되면 Status: Accepted**

## 라이프사이클

```
Proposed → Accepted → (시간 흐름) → Deprecated
                                    또는 Superseded by ADR-NNN
```

- **Proposed**: PR 열렸지만 머지 전. 토론 중.
- **Accepted**: 머지됨. 현재 따르는 결정.
- **Deprecated**: 더 이상 안 따름. 대체 결정 없음 (그냥 안 함).
- **Superseded by ADR-NNN**: 새 ADR로 대체됨. 파일은 historical 기록으로 남김 (절대 삭제 X).

기존 ADR 결정을 바꿀 때는 **그 파일을 수정하지 말고** 새 ADR을 만들어
`Superseded by`로 링크합니다. 그래야 history가 보존됩니다.

## 좋은 ADR 특징

- **1–2 페이지**. 5페이지 ADR은 안 읽힘.
- **Alternatives considered** 섹션 필수 — 그게 ADR의 가치
- **Consequences** 솔직하게 — 좋은 점만 적지 말기
- **링크 박기** — 관련 PR, Plan.md 섹션, 외부 자료

## 현재 인덱스

| # | Title | Status | Date |
|---|---|---|---|
| 000 | Template (skeleton) | — | — |
| (다음 ADR이 여기에 추가됨) |

## 백로그 (작성하면 좋은 ADR)

지금까지 내려진 결정 중 backfill하면 좋을 것들:

- ADR-001: Monorepo (apps/web + apps/worker + packages/shared + migrations) 선택 이유
- ADR-002: TimescaleDB + pgvector — 별도 시계열·벡터 DB 안 쓰고 Postgres 하나에 합친 이유
- ADR-003: Claude vs OpenAI — Anthropic만 쓰기로 한 이유
- ADR-004: 페르소나 4명 (Warren/Cathie/Ray/Peter) 선택과 voice 분리 게이트키퍼 패턴
- ADR-005: Hallucination 방어 — "LLM은 narrative만, 숫자는 Python" 원칙
- ADR-006: Vercel + Cloud Run 분리 — 둘 다 GCP/Vercel 단일화하지 않은 이유
- ADR-007: Open-source 전환 (Free private + branch protection 활성화)
- ADR-008 (예정): conviction-only schema 전환 (Phase C에서 결정 예정)

새 결정 내릴 때 위 list에서 가까운 게 있으면 함께 빈 ADR로 추가하면 좋습니다.
