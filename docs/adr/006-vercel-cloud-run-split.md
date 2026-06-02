# ADR-006: Frontend on Vercel, Worker on Cloud Run (split, not unified)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-18 |
| **Authors** | @6ummy |
| **Tracks affected** | Infra, Frontend |
| **Supersedes** | — |
| **Related** | ADR-001 (monorepo), `architecture.md` §3 stack, `apps/web/vercel.json`, `apps/web/app/api/cron/daily/route.ts` |

---

## Context

Tessera는 두 가지 runtime이 필요합니다:

1. **Frontend** (Next.js) — 사용자 facing, low latency, CDN 필요, preview deployment 자주.
2. **Worker** (Python) — daily batch (ingestion + feature build + LLM thesis), 잡 하나가 보통 30초~90초, 최대 ~8분 (fundamentals 첫 backfill).

"하나의 platform에 다 올리자"라는 유혹이 있습니다. Vercel만 또는 GCP만으로
가는 길. 우리는 둘을 split했습니다. 왜.

## Decision

- **Frontend → Vercel** (Hobby 또는 Pro). Next.js native, edge CDN, preview deployment per PR.
- **Worker → Google Cloud Run Jobs**. Python container, scale-to-zero, 60-min job limit, Cloud Tasks 통합.
- **Trigger 연결**: Vercel Cron이 매일 21:30 UTC에 `/api/cron/daily` ping → Bearer auth 후 Cloud Run worker에 fan-out webhook.
- **공유 데이터**: 둘 다 같은 Neon Postgres 연결 (ADR-002).

## Alternatives Considered

### Alt 1: All-Vercel (Vercel Functions로 worker 처리)
- 단일 platform, 단일 dashboard, 단일 billing
- **거절 이유**:
  - **Vercel Hobby Function timeout 10초, Pro 60초** — 우리 daily batch가 ~8분 → 100% 불가능
  - "Vercel Background Functions"는 일부 기능 있지만 batch 제어가 Cloud Run보다 약함
  - Python runtime이 Node에 비해 second-class — Pydantic, pandas, alpaca-py 무거운 deps 최적화 미흡
  - Cron의 trigger로만 쓰는 게 Vercel의 sweet spot

### Alt 2: All-GCP (Cloud Run으로 Next.js도 호스팅)
- 단일 cloud provider, 같은 IAM/billing
- **거절 이유**:
  - **Vercel Edge / CDN 손실** — 정적 자산, ISR, preview deployment 직접 구현 필요 (큰 작업)
  - **Preview deployment per PR** — PR 머지 전 미리 보고 review 가능한 게 Vercel의 핵심 가치. Cloud Run에선 따로 만들어야 함.
  - Next.js의 Vercel-specific 최적화 (Image, Font, partial pre-rendering) 못 씀
  - 프로젝트 시작 부담 — Cloud Run에 Next.js 띄우는 작업 vs Vercel `git push`로 끝나는 작업

### Alt 3: AWS Lambda + S3 + RDS
- 가장 mature한 serverless, 비용 세분화
- **거절 이유**:
  - 우리 stack에 AWS 자체가 없음 — 추가는 또 다른 IAM/billing/네트워크
  - Lambda timeout 15분이라 daily batch는 가능하지만 cold start, 컨테이너 size 제약 등 골치
  - 무엇보다 — Vercel + Cloud Run에 비해 갖다 줄 이점 없음

### Alt 4: Worker도 Vercel Cron으로 — daily batch를 여러 짧은 함수로 쪼개기
- 한 cron이 단계 1 → 다른 cron이 단계 2 → ...
- **거절 이유**:
  - 분산 batch는 실패 시 부분 성공/실패 처리가 복잡
  - 결국 우리가 직접 작은 Airflow를 만드는 셈
  - Cloud Run Jobs가 이미 이 문제 푼 도구임

## Consequences

### Positive
- **각 stack이 자기 워크로드에 최적화**: Vercel은 frontend latency/preview, Cloud Run은 긴 batch 처리.
- **Vercel preview deployment** — PR 머지 전 `https://tessera-pr-12-...vercel.app` URL로 미리 보기 가능. UI 변경 review 품질이 크게 향상.
- **GCP에 Firebase + Cloud Run + Neon (간접)** 묶여 있어 secret/IAM 한 곳 관리 가능.
- **Vercel Cron이 GCP fan-out trigger** — 양쪽 강점 다 활용.
- **Cloud Run scale-to-zero** — Worker가 batch 외엔 비용 0.

### Negative
- **운영 dashboard 2개** — Vercel + GCP. 모니터링 alert를 어디서 받을지 결정 필요.
- **Billing 2곳** — 합계 추적 수동 (현재 액셀로).
- **Secret 2곳에 둠** — `CRON_SECRET`은 Vercel env, `ANTHROPIC_API_KEY`는 GCP Secret Manager. 팀 공유는 카톡 pinned 메시지로.
- **Cron → Worker 통신 latency** — Vercel edge → Cloud Run 호출. 보통 < 500ms, daily batch context엔 무시 가능.

### Neutral / 관찰할 것
- **Worker 비용** — Cloud Run pricing은 vCPU·메모리·time 기준. 현재 free tier 안 (월 무료 180K vCPU-초). Phase B에서 LLM thesis 추가되면 batch 시간 증가 → 검토.
- **Vercel Hobby → Pro 전환 시점** — 외부 사용자 traffic 증가 시. Pro $20/mo.
- **장애 격리** — Vercel 다운 → 사용자 사이트 못 봄 + cron 못 fire. Cloud Run 다운 → batch 못 돔. 동시에 다 다운날 거의 없음.

## Verification

- ✅ Vercel deployment `https://tessera-ruby.vercel.app/` 200 OK, latency < 200ms (Korea 측정)
- ✅ Cloud Run Jobs schema test (Phase A): worker 잡 1회 ~8분 무사 완료
- ✅ Vercel Cron `/api/cron/daily` Bearer auth + noop 응답 정상
- ✅ **End-to-end shipped (2026-06-01)**: Vercel cron → Cloud Run `/jobs/ingest-daily` → 6/6 steps green, Neon row counts incremented. See `architecture.md` §6 "Daily data flow" for the deployed diagram.

## Implementation notes (added 2026-06-01)

These choices were made during the actual deploy and are sticky enough to record here:

- **Service auth: `--allow-unauthenticated` + shared bearer in app code**, not IAM. Trade-off chosen vs Cloud Run IAM (which would require Vercel to mint short-lived ID tokens via service account impersonation, adding token-plumbing complexity for a 2-service system). Single shared secret in Secret Manager + Vercel env is enough for Phase B; revisit if a third caller (Cloud Tasks, external partner) ever needs to invoke `/jobs/*`.
- **`BackgroundTasks` for long jobs.** Vercel edge fetch has a short timeout (8s wired in code). Cloud Run accepts the request, returns 202 immediately, then runs the ~7-minute ingest in FastAPI's background task. Means `/api/cron/daily` only ever sees a fast 200; failure visibility moves to Cloud Run logs + Sentry.
- **Non-root container** (`USER tessera` in Dockerfile). Hardening for the public-internet-exposed (--allow-unauthenticated) service.
- **`min-instances=0, max-instances=2`.** Cost over latency: cold start adds ~3s to the first cron of the day, which is fine because the cron is async. Max 2 caps the blast radius if a runaway loop somewhere fires repeatedly.
- **Secret hygiene gotcha (Windows-specific)**: PowerShell 5.1's pipeline output encoding wraps stdin-piped strings with UTF-8 BOM. The initial `gcloud secrets versions add SENTRY_DSN --data-file=-` injected `﻿` at the start of the DSN, which made `sentry_sdk` parse the scheme as empty and crash the container on startup. Fix: write the value to a temp file with `[System.Text.UTF8Encoding]::new($false)` (no BOM), then `--data-file=$tmp`. The `deploy_cloud_run.ps1` flow does not hit this — it's only a concern when loading secrets from PowerShell.

## Notes / Open Questions

- **Worker 배포 자동화** — 현재 수동 `gcloud run deploy`. Phase A 끝나면 GitHub Actions에서 `apps/worker/**` 변경 시 자동 deploy 검토.
- **Multi-region** — Tessera는 US-only product이지만 미래 사용자 확장 시 Vercel은 자동 multi-region, Cloud Run은 region별 별도 deploy.
- **Cost dashboard 통합** — Vercel + GCP + Anthropic + Neon 합쳐 보는 single page. Phase C 또는 D에서 GitHub Actions로 일일 cost 합계 메모.
