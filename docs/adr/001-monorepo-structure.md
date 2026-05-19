# ADR-001: Monorepo (apps/web + apps/worker + packages/shared + migrations)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-18 |
| **Authors** | @6ummy |
| **Tracks affected** | All |
| **Supersedes** | — |
| **Related** | `architecture.md` §3 stack, Phase A retro |

---

## Context

Tessera는 초기에 단일 Next.js 프로젝트로 시작했습니다. Frontend MVP만 있는 동안엔
`app/`, `components/`, `lib/`가 repo root에 있어 문제 없었습니다.

Phase A에 들어가면서 두 가지가 추가됐습니다:

1. **Python worker** — Cloud Run에서 daily batch (ingestion + feature build).
   판다스·pgvector·alpaca-py 같은 PyData 생태계 의존성. Next.js와 같은
   디렉토리에 둘 수 없음.
2. **Shared schemas** — `AnalystReport`, `Proposal`, `RiskCheckResult` 등의
   Pydantic 모델. Worker가 LLM 출력 validate하고, Frontend가 API response
   로 받는 타입. 한쪽이 바꾸면 다른 쪽도 알아야 함.

세 가지 코드베이스 (web TS / worker Python / shared)를 어떻게 조직할지 결정이
필요해졌습니다.

## Decision

**Monorepo로 간다.** 디렉토리 구조:

```
apps/
  web/                Next.js 14 (TypeScript)
  worker/             Python (FastAPI + 배치 잡)
packages/
  shared/             Pydantic schemas (Python). 미래에 TS 미러 추가 가능.
migrations/           SQL files (도구 중립).
docs/                 ADR + retro.
```

모든 것이 한 git repo 안. `git clone` 한 번으로 dev 환경 완성. 한 PR이
web + worker + shared schema를 동시에 변경 가능.

## Alternatives Considered

### Alt 1: Polyrepo (tessera-web / tessera-worker / tessera-shared)
- 각 repo가 독립된 CI, 독립된 deploy
- 명확한 boundary
- **거절 이유**:
  - Shared schema 변경 시 3개 PR (worker, web, shared 각각) 같이 머지해야 → coordination 부담
  - 솔로 dev에서 4인 팀으로 확장 중 — repo가 늘수록 신규 합류자 onboarding 비용 증가
  - 비용 추적, 이슈 트래킹이 분산 → 4인 팀엔 너무 많은 오버헤드

### Alt 2: 단일 Next.js + 내부에 `worker/` 디렉토리만 추가 (no packages/)
- 가장 가벼운 옵션
- Shared 코드는 단순 import path로 해결
- **거절 이유**:
  - Python ↔ TypeScript 경계가 흐려짐 (둘 다 src/ 안에 섞이면 헷갈림)
  - Shared schema가 어디 살아야 하는지 명확하지 않음 — Python 쪽? TS 쪽? 둘 다 복사?
  - `packages/shared`처럼 명시적 package boundary가 미래의 ts mirror 추가, 외부 export, npm/pip 배포 옵션을 열어둠

### Alt 3: Turborepo / Nx 같은 monorepo 도구 도입
- 빌드 캐싱, 의존성 그래프 자동 추적, parallel task 실행
- 큰 monorepo에 좋음
- **거절 이유**:
  - 5명 팀 + 2개 앱엔 over-engineering
  - 도구 학습 부담 (특히 신규 합류자)
  - 우리 빌드는 단순 — Vercel이 web을, Cloud Run이 worker를 알아서 빌드
  - 향후 필요해지면 추가 — 지금 도입은 premature

## Consequences

### Positive
- Repo 1개, dashboard 1개, issue tracker 1개 → 운영 단순
- Shared schema 변경 + worker 적용 + frontend 적용을 한 PR로 가능 → atomic deploy
- 신규 합류자가 `git clone https://github.com/6ummy/Tessera` 한 줄로 전체 코드 확보
- CODEOWNERS로 트랙별 자동 review 라우팅 가능 (path 기반)

### Negative
- Vercel의 root directory 설정을 `apps/web`으로 명시해야 함 (default가 repo root라 사고 1회 — 빈 빌드 발생)
- Python worker dev 시 `cd apps/worker` 필요 — 약간의 friction
- Repo가 web + worker 둘 다 포함 → public open-source 시 둘 다 노출 (의도된 결과)

### Neutral / 관찰할 것
- Repo 크기 — git 한 번에 frontend deps + python deps 다 받음. 현재 OK (~300MB), 1년 후 점검.
- 미래에 mobile app 추가 시 `apps/mobile/` 자연스럽게 들어감.
- TypeScript 미러 Pydantic 스키마가 필요해지면 `packages/shared`에 추가 가능 (예: zod or quicktype-generated).

## Verification

- ✅ `git clone` 후 두 readme (apps/web/, apps/worker/)만 보고 dev 환경 완성 가능
- ✅ Phase A end-to-end가 한 monorepo 안에서 동작 (worker가 schema 만들고 web이 같은 schema 인식)
- 향후: 새 합류자 첫 PR까지 소요 시간 < 4시간 (현재 측정 안 됨, Phase B에서 실측)

## Notes / Open Questions

- 미래에 worker만 따로 컨테이너화해서 사내 다른 팀에 배포할 일이 생기면 polyrepo 분리 재고. 지금은 가설일 뿐.
- ADR-006 (Vercel + Cloud Run 분리)이 이 결정 위에 세워짐 — 둘은 같이 봐야 의미 있음.
