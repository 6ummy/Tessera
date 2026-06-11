# 코드베이스 진단 및 단계별 개선 계획 (2026-06-11)

> Phase B 종료(2026-06-05) 후 Phase C 착수 전 시점의 전체 코드베이스 감사.
> Plan.md / architecture.md의 로드맵·리스크 레지스터와 실제 코드를 대조 검증.
> 검증 도구: pytest(179 passed), ruff(102건), `mypy --strict`(216건/28파일),
> `tsc --noEmit`(clean), git 이력 시크릿 스캔(clean).
>
> **상태 표기**: ✅ 이 감사에서 즉시 수정됨 · ⏳ 후속 Step에 배정 · 📋 인지만

---

## 1. 잘 되어 있는 것 (유지할 패턴)

- 워커 테스트 전부 통과, 웹 typecheck clean
- LLM 안전장치 실동작: 백테스트 leakage 테스트, citation validator, hallucination canary, 일일 예산 hard-pause
- 시크릿 위생: `.env` gitignore + 커밋 이력 무결, `check_connections.py` redaction
- `gcp-auth.ts`의 IAM 토큰 전환 경로(bearer → OIDC) 설계 양호
- 인제스터 전반의 멱등 upsert(ON CONFLICT) 일관성

---

## 2. 발견 사항

### P0 — 데이터 정합성

| # | 문제 | 상태 |
|---|---|---|
| P0-1 | **OHLCV 달력일 중복 → 피처 오염.** `ohlcv_1d` PK가 `(ticker, ts)`(TIMESTAMPTZ)인데 Alpaca는 04:00Z, 2026-06-02 yfinance 백필은 00:00Z로 기록 → 2020-07~현재 약 6년 구간에서 같은 거래일이 2행 공존. `features/compute.py::_load_ohlcv`가 dedup 없이 읽어 행-윈도우 피처 전부 왜곡(`ret_30d` = 30행 ≈ 실제 15거래일, `ret_1y` ≈ 6개월, `vol_30d`/`rsi_14`/`sma_*`/`volume_z` 동일). 리스크 레지스터의 "Feature builder bug propagates as LLM-blessed thesis"가 실제로 발생한 사례. SPY 캐너리 0.49bps는 백필 **이전** 측정값. | ✅ `_load_ohlcv` + `/api/prices` DISTINCT ON dedup, `backfill_yahoo` 중복 방지, `006_ohlcv_canonical_day.sql`. **운영자 액션 필요** (§4) |
| P0-2 | **`/api/proposals` 집계기가 v1 전제.** v2(PR #87, 페르소나당 주 1행 = 전체 book)가 기본이 됐는데 집계기는 최근 20행(≈20주)을 union → 이번 주 book에서 빠진 종목이 과거 행에서 부활("유령 포지션"), cash_target 20주 평균, NAV 보존 로직이 혼합 book을 비례 축소해 그럴듯하게 노출. | ✅ 최신 `as_of_date` 배치만 집계(`MAX(as_of_date)` 서브쿼리), `_aggregate_book` 순수 함수 추출 + 회귀 테스트 6건 (`tests/test_main_api.py`). v2의 `notes_to_manager`도 응답에 복원 |
| P0-3 | **prod 이미지에 yfinance 부재.** `[backfill]` extra에만 있고 Dockerfile은 `pip install .` → Cloud Run에서 `yf_shares`(일)·`yf_history`(주) 스텝이 ImportError를 ticker별로 삼키고 **ok=True로 "성공"**. architecture.md가 "shipped + verified"로 기록한 V/MA 3-tier 폴백이 prod에서 무력화된 상태(로컬 실행 데이터로만 연명). | ✅ yfinance 코어 의존성 승격, 미설치 시 스텝이 명시적으로 실패(RuntimeError → step_failed → Sentry). **이미지 재빌드 필요** (§4) |

### P1 — 운영 안정성 / 보안

| # | 문제 | 상태 |
|---|---|---|
| P1-1 | ingest(~7분)·persona_batch(5–10분)가 Cloud Run **Service**의 `BackgroundTasks`에서 실행 — scale-to-zero/CPU 스로틀링 시 중간 사망 가능(architecture.md "Long-job survival note"의 미해결 todo). 제품 신뢰성의 기반이므로 Phase C 첫 작업으로. | ⏳ Step 2-1 |
| P1-2 | **CI 부재.** Plan §9는 "Week 1부터 GitHub Actions"라 했지만 `.github/workflows` 없음. ruff 102건·mypy 216건이 방치되고 179개 테스트가 PR에서 실행 안 됨. 공개 레포(ADR-007)인데 머지 게이트 0. 약속된 시크릿 pre-commit 훅도 부재. | ⏳ Step 1 |
| P1-3 | **공개 chat 남용 방어 부재.** Vercel 프록시 무인증 + 레이트리밋 없음 + `message`/`history` 길이 무제한(클라이언트 제어). 일일 예산 캡이 thesis 배치와 공유라 챗 남용 → 금요일 배치 기아 가능. | ⏳ Step 2-3 |
| P1-4 | ingest 동시 실행 락 없음(architecture.md 문서화된 todo). `pg_advisory_lock` 한 줄. | ⏳ Step 2-2 |
| P1-5 | Bearer 비교가 비-상수시간(`!=`). | ✅ `hmac.compare_digest` (worker). 웹 Edge 라우트는 낮은 우선순위로 ⏳ |

### P2 — 정확성/품질 부채

- **P2-1** adjusted-price 정책 미정: Yahoo 백필(`auto_adjust=False`)과 Alpaca IEX의 분할/배당 처리 기준 검증 안 됨. Plan §5 "Quant data integrity gates" 미체크 항목. ⏳ Step 2-4와 함께
- **P2-2** SPY 캐너리가 수동 스크립트 — 자동화돼 있었으면 P0-1을 기계가 잡았음. ⏳ Step 2-4 (오케스트레이터 read-only 스텝으로 승격)
- **P2-3** 테스트 사각지대: main.py API 핸들러(P0-2가 살았던 곳 — 이번에 일부 해소), `portfolio_construction.py`, 인제스터. ⏳ Step 3-6
- **P2-4** `check_daily_budget()` read-then-act 레이스 — 동시 chat 호출 시 캡 소폭 초과 가능. 📋 파일럿 허용
- **P2-5** `_normalize_conviction`의 0.5 중앙값 채움 — 누락 필드 조용한 날조. 로그는 있음. 📋 canary 체크 후보
- **P2-6** 페르소나 ID 튜플 하드코딩 산재(main.py/chat.py/웹 라우트). 📋
- **P2-7** 모델 단가 하드코딩(`anthropic_runner._MODEL_PRICING`) — 가격 변경 시 비용 로그 조용히 왜곡. 📋
- **P2-8** mypy strict 설정은 있으나 216건 방치 — "설정만 strict" 상태. ⏳ Step 1-3 (모듈별 점진 적용)

### P3 — 문서/위생

- architecture.md 파일맵 낡음("agents/ — empty", "13 hypothesis tests" 등) — ✅ 이번에 동기화
- migrations/README 표에 005 누락 — ✅ 005·006 추가
- Plan.md "Cross-source disagreement dashboards" 중복 기재 — ✅ 제거
- README가 존재하지 않는 `deck-script-ko.md` 참조 — ✅ 제거
- Phase 회고 문서 없음(Plan §9 약속 `docs/retro-phase-X.md`) — ⏳ Step 4
- 레포 루트 pptx 5개(일부 git 추적) — 📋 공개 레포 용량/잡음

---

## 3. 단계별 개선 계획

### Step 0 — 데이터 정합성 핫픽스 ✅ (2026-06-11 본 변경)

코드는 전부 반영됨. **운영자 액션(§4)이 남아 있음.**

### Step 1 — CI/품질 게이트 ✅ (2026-06-11 후속 PR)

1. ✅ `.github/workflows/ci.yml`: worker(ruff 차단 + pytest 차단 + mypy 비차단) + web(`tsc --noEmit` + `next lint`) 매 PR/main push.
2. ✅ ruff 백로그 **102 → 0** (자동 96 + 수동 ~50: SIM105 contextlib.suppress ×10, E701 전개, E501 줄바꿈, B007 `_`-prefix, F841 제거, E402 import 재배치, B017 `ValidationError` 구체화, C417 genexp). 179 테스트 통과 유지.
3. ✅ web에 `.eslintrc.json` 추가(없어서 CI의 `next lint`가 인터랙티브 프롬프트로 멈출 상태였음). `react/no-unescaped-entities`만 비활성(산문 아포스트로피 18건; 구조 오류는 typecheck가 잡음).
4. ✅ `.pre-commit-config.yaml` + gitleaks — Plan §9가 약속한 시크릿 훅. 개발자별 1회 `pip install pre-commit && pre-commit install`.
5. ⏳ mypy strict 216건은 비차단 리포트로 노출 — 모듈별 청산 후 차단 전환 (P2-8).

### Step 2 — 운영 안정성 ✅ (2026-06-11 후속 PR)

1. ✅ **배치 실행 모델 (부분)**: `deploy_cloud_run.ps1`에 `--no-cpu-throttling` 추가 — **다음 배포부터 적용**(또는 운영자가 `gcloud run services update tessera-worker --region us-east1 --no-cpu-throttling`로 즉시 적용). 구조적 해법인 Cloud Run **Jobs** 전환은 Phase C 본 작업으로 잔존.
2. ✅ `db.try_advisory_lock("ingest_daily")` — run() 전체를 감싸고, 중복 트리거는 `advisory_lock` no-op 스텝으로 즉시 반환. 세션 레벨 락이라 크래시 시 자동 해제.
3. ✅ chat 방어 3중: worker 측 message ≤4K자(400) + history 정제(≤20턴, role 검증, content 절단) + **chat 전용 일일 예산 풀**(`LLM_MAX_DAILY_COST_CHAT_USD`, 기본 $2 — 글로벌 캡과 별도라 챗 남용이 금요일 배치를 굶기지 못함). Edge 프록시: IP당 10회/분 레이트리밋(isolate별 best-effort) + 크기 사전 차단. 기존 버그도 수정: `LlmDailyBudgetExceeded`가 `ChatBudgetExceeded`로 변환되지 않아 SSE 에러 이벤트 타입이 generic으로 새던 것.
4. ✅ SPY 캐너리 자동화: `jobs/spy_canary.py` + `ingest_daily`의 13번째 `canary` 스텝. >100bps → RuntimeError → step 실패 → exit 1/Sentry. Yahoo 불통은 skip(우리 회귀가 아님). adjusted-price 정책(P2-1)은 미결 — 현재 실측 2.62bps로 비교 자체는 건전.
5. ✅ 배포 스크립트 정리: 낡은 "Next: set WORKER_WEBHOOK_URL … /jobs/ingest-daily" 안내문을 base-URL 안내로 교체(gcp-auth.ts가 경로를 어차피 제거하고 IAM audience는 base URL이어야 함), `LLM_MAX_DAILY_COST_CHAT_USD=2.0` env 추가.

### Step 3 — Phase C 본 작업 (Plan.md §5와 정렬)

1. ~~2-pass 페르소나~~ → v2로 출하 완료. 집계기 정리도 본 변경에서 완료.
2. ✅ 리스크 게이트웨이(`risk/gateway.py`) — **shipped 2026-06-11**. 얇은 검증기: 유니버스 멤버십(반-환각 최종 관문), sum=1.0·single-name cap 재확인, 그리고 그동안 프롬프트로만 존재하던 **sector cap 강제**. `construct_portfolio` retry 루프에 연결되어 거부 사유가 LLM 재시도 피드백으로 전달됨. cash 범위·conviction floor는 soft(로그만). VaR·drawdown floor·Ray regime 게이트는 페이퍼 엔진(포지션 존재) 이후. 테스트 7개.
3. PaperEngine + 원장 + mark-to-market → `persona_performance` 채우기.
4. 프론트 mock 교체(`lib/mock/performance.ts` — 현재 랜딩/대시보드/카드에 시드 랜덤워크 표시 중). 교체 전까지 "시뮬레이션 데이터" 라벨 권장.
5. Grafana 비용 + cross_validated 불일치 대시보드, Voyage prod 활성화.
6. main.py 나머지 핸들러·portfolio_construction·인제스터 테스트 보강.

### Step 4 — 문서 (~반나절)

1. `docs/retro-phase-B.md` 작성.
2. pptx류 Release 자산 이전 검토.

---

## 4. 운영자 체크리스트 (Step 0 반영을 prod에 적용)

> **✅ 전 항목 완료 — 2026-06-11.** 결과 기록:
> 1. 006 적용 (Neon SQL Editor) — 중복 달력일 0건, 고아 feature 행 0건,
>    `ticker_features` 260K → 203K (중복분 ~5.7만 행 정리)
> 2. 피처 재계산 — 203K → 211.7K 행 (canonical ts 기준 재생성)
> 3. **SPY 캐너리 2.62 bps** (임계 100 bps) — 수정 전 측정 불가 상태에서 복귀
> 4. 워커 이미지 재빌드 + 재배포 (yfinance 포함) 완료
>
> 아래는 적용 당시의 원본 절차 (기록용):

```bash
# 1. 마이그레이션 적용 (중복 ohlcv 행 + 고아 ticker_features 행 삭제)
psql "$DATABASE_URL" -f migrations/006_ohlcv_canonical_day.sql

# 2. 피처 전체 재계산 (canonical ts 기준으로 재생성; 품질 컬럼 포함)
python -m tessera_worker.jobs.ingest_daily --only features coverage

# 3. 캐너리 재검증 — 수정 전후 ret_1y/vol_30d 차이를 기록해 둘 것
python -m scripts.ingest_spy_canary

# 4. 워커 이미지 재빌드 + 배포 (yfinance가 이미지에 들어가도록)
.\scripts\deploy_cloud_run.ps1

# 5. 배포 후 다음 cron에서 yf_shares 스텝이 rows>0으로 도는지 확인
gcloud logging read "resource.labels.service_name=tessera-worker" --freshness=1d | grep yf_shares
```

검증 포인트:
- 006 적용 직후 `SELECT ticker, ts::date, COUNT(*) FROM ohlcv_1d GROUP BY 1,2 HAVING COUNT(*)>1` → 0행
- `/api/proposals/warren` 응답의 종목 수가 최신 배치 book과 일치(과거 종목 부활 없음)
- SPY 캐너리 100bps 이내 복귀
