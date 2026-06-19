# 버그 케이스 스터디 — 최종 발표 자료

> 2026-06-11~12 감사 + Phase C 가동 과정에서 실제로 잡은 버그 모음.
> 각 케이스는 발표 슬라이드 1장 분량으로 정리: **증상 → 추적 → 원인 →
> 수정 → 교훈**. PR 링크가 1차 증거. (이 파일은 발표 준비용 "개별 참조
> 산출물"이라 docs/에 둔다 — phase별 교훈 인라인 원칙은 Plan.md §9 참조.)
>
> **관통하는 주제: 침묵 실패(silent failure).** 12건 중 5건(CS-3/4/5/6/12)이
> "에러가 났는데 아무도 모르게 삼켜진" 계열이다 — `suppress`,
> `setdefault`, `ok=True`, 그리고 무시된 종료 코드. 예외를 잡으면 반드시
> 어딘가에 큰 소리를 내야 한다.

---

## 1. 데이터 정합성

### CS-1. 같은 날이 두 번 — 6년치 피처가 조용히 절반 지평으로 (P0-1, #90)

- **증상**: 없음. 그게 문제였다. SPY 캐너리는 백필 *이전* 측정값(0.49bps)
  이었고, 아무 알람도 없었다.
- **추적**: 전체 코드 감사 중 `_load_ohlcv`가 dedup 없이 읽는 것을 발견
  → Plan.md의 "⚠️ mixed-source 노트"(백테스트만 문제라고 적혀 있던)와
  대조 → 프로덕션 피처 빌더도 같은 테이블을 읽는다는 걸 확인.
- **원인**: `ohlcv_1d` PK가 `(ticker, ts TIMESTAMPTZ)`. Alpaca는 04:00Z,
  yfinance 백필은 00:00Z로 기록 → 같은 거래일이 2행. 모든 피처가
  행-윈도우 연산이라 `ret_30d`=30행≈실제 15거래일, `ret_1y`≈6개월.
  LLM이 몇 주간 왜곡된 숫자로 thesis를 썼다.
- **수정**: migration 006(중복 삭제 + 정본 소스 규칙), 읽기 경로
  `DISTINCT ON (ticker, ts::date)`, 백필의 covered-day 스킵, **SPY
  캐너리를 nightly 자동 스텝으로 승격**(수동 스크립트였던 게 미탐의
  공범). 수정 후 캐너리 2.62bps 복귀.
- **교훈**: 리스크 레지스터의 "feature builder bug propagates as
  LLM-blessed thesis"가 실제로 일어났다. **데이터 불변식은 문서가 아니라
  기계(캐너리)가 지켜야 한다.**

### CS-2. 유령 포지션 — 집계기가 20주치 book을 합성 (P0-2, #90)

- **증상**: UI의 "현재 포트폴리오"가 그럴듯해 보였다(이것도 문제).
- **추적**: v2 배치("페르소나당 주 1행, 행에 전체 book")로 전환된 뒤에도
  `/api/proposals`가 v1 가정("종목당 1행")으로 최근 20행을 union하는
  것을 코드 리뷰로 발견.
- **원인**: 이번 주 book에서 빠진 종목이 과거 행에서 부활하고, cash는
  20주 평균, NAV 보존 로직이 그 혼합물을 비례 축소해 "합이 1.0인
  그럴듯한 거짓말"을 만들었다.
- **수정**: `MAX(as_of_date)` 스코핑 + 집계를 순수 함수로 추출 + 회귀
  테스트("이전 배치에만 있던 종목은 응답에 없어야 한다").
- **교훈**: **스키마 전환(v1→v2) 시 모든 reader를 전수 조사**할 것.
  쓰는 쪽만 바꾸면 읽는 쪽이 조용히 거짓을 만든다.

---

## 2. 침묵 실패 — 예외/기본값이 삼킨 버그들

### CS-3. 설치된 적 없는 의존성이 "성공"으로 보고 (P0-3, #90)

- **증상**: 문서에는 "yfinance 폴백 shipped + verified". prod에서는
  매일 밤 no-op.
- **원인**: yfinance가 `[backfill]` extra에만 있고 Dockerfile은
  `pip install .` — 이미지에 없음. 인제스터가 ticker별 ImportError를
  잡아 `no_data`로 분류 → 스텝이 **ok=True**로 끝남. 검증은 로컬
  (yfinance 있음)에서만 했었다.
- **수정**: 코어 의존성 승격 + **미설치면 스텝이 크게 실패**하도록.
- **교훈**: "모든 항목이 no_data인 성공"은 성공이 아니다. **전제조건
  실패는 부분 실패가 아니라 전체 실패로 보고**해야 한다.

### CS-4. LLM이 써준 날짜가 서버를 이김 — 17개월 묵은 book 날짜 (#98)

- **증상**: 페이퍼 엔진 첫 검증 런 로그에 `ray book="2025-01-24"`.
  작성일은 2026-06-10인데.
- **추적**: ray의 모든 행이 같은 잘못된 날짜 → `build_regime_report`의
  `parsed.setdefault("as_of", ...)` 발견.
- **원인**: `setdefault`는 LLM 출력에 `as_of`가 이미 있으면 그걸
  유지한다. Ray의 Sonnet은 프롬프트 맥락에서 베낀 날짜를 꼬박꼬박
  넣었고, 몇 주간 이겼다. `MAX(as_of_date)` 스코핑이 동작한 건 모든
  행이 *똑같이* 틀려서였던 순전한 운.
- **수정**: 서버 권위 필드는 **force-set** + 회귀 테스트 + prod UPDATE.
- **교훈**: **LLM 출력과 서버 값이 겹치는 필드에 setdefault 금지.**
  "LLM이 그 필드를 넣을 리 없다"는 가정은 항상 깨진다.

### CS-5. 재시도가 멀쩡한 book을 버림 — `char 0`의 정체 (#110)

- **증상**: 금요 배치에서 warren·cathie가 4번 연속(프로덕션 2 + 로컬
  재실행 2) 동일 패턴 실패: 1차 게이트 거부(정상) → 2차
  `JSONDecodeError: Expecting value: char 0`.
- **추적**: "빈 응답"이라기엔 `tokens_out=1992~4527`. 응답에 내용이
  가득한데 0번째 글자에서 실패 → **JSON 앞에 뭔가 있다**.
- **원인**: 재시도 프롬프트("이전 출력이 거부됨: <사유>")가 모델로
  하여금 *무엇을 고쳤는지 설명*하고 싶게 만든다. `parse_llm_json`은
  JSON *뒤*의 잡담만 허용하고 *앞*의 산문에서 즉사. 재시도에서만 100%
  재현되는 이유까지 설명된다. 버려진 응답 안에는 섹터를 57%→51%로
  고친 유효한 book이 들어 있었다.
- **수정**: 첫 `{`부터 순차 스캔(산문 속 중괄호 대응 루프) 후 파싱.
- **교훈**: **LLM 출력 파서는 양방향 잡담을 가정**해야 한다. 그리고
  "에러 메시지의 char 0"과 "tokens_out 4527"이 같이 보이면 파서를
  의심하라 — 모델이 아니라.

### CS-6. 잘 돌던 유사도 검색이 1주일간 "recency"로 자수 (#111)

- **증상**: 사용자 질문 "sim=0.xx 태그가 어디에도 안 보이는데?"
  운영자가 Voyage 키를 재등록해도 마찬가지 → "키가 root cause가 아닌
  것 같다"는 직감이 적중.
- **추적**: 3겹을 차례로 벗김 —
  1. `sim=` 태그는 **로그에 아예 안 찍힌다**(프롬프트 텍스트 전용).
     문서의 "배치 로그에서 sim= 확인" 지시는 태생부터 검증 불가였다.
  2. 프롬프트 안에서도 항상 "recency": SQLAlchemy 2.0 `Row`는 불변이라
     `r._recall_tag = ...`가 AttributeError → `with
     suppress(AttributeError)`가 꿀꺽. **유사도 검색은 내내 정상 작동**
     (실측 거리 0.36~0.60)하면서 라벨만 거짓이었다.
  3. prod의 invalid key는 진짜지만 독립적인 3번째 문제(아래 CS-9).
- **수정**: 태그를 실을 수 있는 경량 객체 반환(suppress 제거) +
  `memory_recall.strategy` 로그 이벤트 신설 — 이제 관측 가능.
- **교훈**: **`suppress`/`except: pass`는 침묵 실패 제조기.** 그리고
  "검증 방법"을 문서에 쓸 때는 그 방법이 실제로 신호를 낼 수 있는지
  코드로 확인할 것 — 우리는 확인 불가능한 검증 지시를 두 번 썼다.

### CS-7. 테스트를 쓰다가 발견한 prod 갭 — cash 클램프 (#99)

- **증상**: 없음 — `normalize_book` 테스트 스위트를 *작성하는 과정*에서
  발견.
- **원인**: cash 범위 클램프가 "합이 틀렸을 때"의 분기 안에만 있어서,
  합이 정확히 1.0이면 Cathie가 cash 70%(mandate 상한 10%)를 들고도
  통과.
- **수정**: 클램프를 무조건 실행으로; 포지션이 차액을 흡수.
- **교훈**: **테스트 보강은 회귀 방지가 아니라 발견 도구.** "이 함수가
  뭘 보장한다고 docstring에 적혀 있나"를 테스트로 옮기면 거짓말이
  드러난다.

---

## 3. 인프라/운영

### CS-8. 22:47에 시작한 배치, 23:02에 인스턴스와 함께 사망

- **증상**: 금요 배치가 cathie research 도중 끊김. `analyst_reports`
  0행, LLM 비용 $0.69만 소모.
- **원인**: 배치가 Cloud Run **Service**의 BackgroundTask(202 응답 후
  실행). `--no-cpu-throttling`은 CPU는 보장하지만 **유휴 인스턴스
  회수는 못 막는다** — 마지막 요청 후 ~15분에 SIGTERM. 알려진 구조적
  한계가 실제 사고로.
- **수정(임시)**: 로컬 수동 재실행. **수정(구조)**: Cloud Run Jobs
  전환 — 이 사고로 "여유 있을 때"에서 "다음 금요일 전 필수"로 승격.
- **교훈**: 응급처치(`--no-cpu-throttling`)가 막아주는 범위를 정확히
  알 것. **15분짜리 작업을 요청-응답 모델에 싣는 건 시한부.**

### CS-9. 시크릿에 잡문자 1개 — 그리고 가설을 해시로 판정한 이야기 (#101 runbook)

- **증상**: prod 로그 `Provided API key is invalid` (Voyage 서버 응답,
  23:01 UTC). 그런데 운영자: "내 키는 잘 동작하고 대시보드에 활동도
  보이는데?" — 둘 다 사실이었다.
- **추적 (이 케이스의 백미)**: AI의 1차 가설은 "runbook의 bash
  `echo -n`을 PowerShell에서 실행해 개행이 섞였다". 운영자가 의심하자
  **추정 대신 바이트 검증**으로 전환 — Secret Manager의 버전별 값과
  로컬 .env 키를 SHA-256/길이/말단바이트로 비교(키 비노출):
  - v1(최초, 실패 시점 활성): **47바이트**, 로컬과 다른 해시, 끝이
    `V/` — **여분 문자 1개가 붙은 키**. 개행(0x0A) 아님 → bash/개행
    가설 기각, 복사-붙여넣기 잡문자로 정정.
  - v2/v3(재등록): 46바이트, **로컬과 SHA-256까지 동일** — 이미 해결.
- **수정**: 재등록(운영자가 이미 완료) + runbook을 바이트 정확한
  업로드 방식으로 교체 + `:latest`는 인스턴스 시작 시 해석된다는 주석.
- **교훈 1**: 서버의 "invalid" 응답과 "내 키는 멀쩡하다"는 **둘 다
  참일 수 있다** — 저장된 사본이 다를 뿐. 시크릿 디버깅은 값 비교가
  아니라 **해시 비교**로 (노출 없이 판정 가능).
- **교훈 2**: 그럴듯한 가설(echo -n)을 운영자가 의심하면 **추정을
  방어하지 말고 검증 수단을 바꿔라.** 이 케이스에서 AI의 1차 진단은
  "키 값이 잘못됐다"(맞음)였지만 메커니즘(개행)은 틀렸다 — 해시 비교가
  3분 만에 둘 다 판정했다.

### CS-10. 스택 PR이 main이 아니라 서로에게 머지됨 (#91/#92→#93)

- **증상**: PR 상태는 MERGED인데 main에 코드가 없음.
- **원인**: GitHub은 base 브랜치가 **삭제될 때만** 자식 PR을 main으로
  retarget. base를 남겨둔 채 머지하면 스택 안으로 흡수된다.
- **수정**: 원본 커밋 cherry-pick 재상륙(#93) + "Automatically delete
  head branches" 활성화 + CLAUDE.md 프로세스 규칙화.
- **교훈**: 도구의 자동화 가정(retarget)을 확인하지 않은 채 워크플로를
  설계하지 말 것.

### CS-12. exit code를 무시한 9일 — Job 전환이 들춰낸 침묵 실패 (#119)

- **증상**: Cloud Run **Job**의 첫 테스트런이 빨간 X(`exit code 1`).
  "Job 전환이 실패했나?" 싶었지만, 로그를 보니 **14스텝을 전부 완주**
  하고(paper engine 24체결, canary 2.62bps) 딱 한 스텝만 실패:
  `ohlcv_equity → APIError: invalid symbol: AVAX/USD`.
- **추적**: AVAX/USD는 크립토인데 왜 **주식** API(Alpaca)에 갔나?
  `_step_ohlcv_equity`가 전체 유니버스(`TICKERS`, 크립토 포함)를 한 번의
  `StockBarsRequest`로 보냈고, Alpaca는 크립토 심볼 하나에 **요청 전체를
  거부**. 데이터 확인: AAPL/NVDA 마지막 값이 **2026-06-05 — 9일 전.**
  크립토 페어가 유니버스에 추가된 06-09부터 주식 OHLCV가 동결돼 있었다.
- **원인 (이중)**:
  1. 기능 버그 — equity 스텝이 크립토를 걸러내지 않음.
  2. **왜 9일이나 안 보였나**: 기존 Service 경로는 배치를 202 응답 후
     BackgroundTask로 돌려 **종료 코드를 아무도 확인하지 않았다.** 스텝
     하나가 매일 실패하고 exit 1을 반환해도 Service는 무시. **Job은 종료
     코드를 충실히 따지므로 즉시 빨간 X**로 드러냈다.
- **수정**: equity 스텝을 `by_asset_class("equity")+("etf")`로 제한
  (크립토는 Coinbase 경로). 회귀 테스트로 "크립토가 Alpaca에 가지 않음"
  고정. 수정 후 즉시 갱신 — AAPL 06-05 → 06-12, 1020행.
- **교훈**: **CS-8의 Job 전환은 "배치가 안 죽는다"만 준 게 아니다 —
  종료 코드 정직성을 복원해, Service가 9일간 삼켜온 침묵 실패를 첫
  런에서 잡아냈다.** 관측 가능성을 고치면 숨어 있던 버그가 따라 나온다.

---

## 4. AI/LLM 동작 특성

### CS-11. 페르소나의 고집 — 에러를 내지 않고 규칙을 어기는 AI

- **증상**: Cathie 페르소나가 포트폴리오 생성 시 `risk_gateway`의 섹터 한도(최대 50%)를 반복해서 초과하며 최종 배치 실패.
- **추적**: 1차 시도에서 기술주(Technology) 67% 배정으로 거절됨. 재시도(attempt=1) 시 JSON 파서는 정상 동작했으나, 수정된 포트폴리오에서도 기술주 비중을 56%까지만 낮추며 여전히 한도를 초과함.
- **원인**: 시스템이 피드백 에러로 "Technology weight 0.5600 > sector cap 0.50"을 명확히 전달했음에도, 기술 혁신 기업 투자를 지향하는 Cathie 페르소나의 성향이 시스템의 수학적 제한보다 더 강하게 작용함.
- **수정**: 없음 (오히려 AI가 부여된 페르소나를 충실히 연기한 매우 흥미로운 결과).
- **교훈**: **LLM은 시스템의 명시적 제한(Rule)보다 자신에게 부여된 역할(Role)을 더 우선시할 수 있다.** 필수적인 룰은 AI의 자발적 수정을 기대하기보다 리스크 게이트웨이처럼 시스템 단에서 강제 차단하는 것이 올바른 구조임을 완벽하게 증명함.
- **후속 (2026-06-12 → 06-15)**: 섹터 한도를 50% → 70%로 올렸다가, 결국 **Cathie의 섹터 캡을 완전히 제거**했다. 핵심 깨달음: 이 페르소나에게 섹터 캡은 *애초에 잘못된 도구*였다 — "S-curve 섹터 집중"이 곧 그녀의 맨데이트이므로 테크 집중은 통제할 리스크가 아니다. 그녀의 실제 리스크는 단일종목 16% + VaR99 8.5% + 드로다운 35%로 여전히 하드 게이트된다. **CS-11의 교훈은 그대로다: 캡을 내리는 이유는 "AI가 자꾸 어겨서"가 아니라 "그 캡이 틀린 통제라서"여야 한다.** 전자로 캡을 푸는 것은 게이트를 무력화하는 안티패턴이고, 후자는 통제 대상을 올바로 재정의하는 것이다.

---

## 5. 데이터 품질 (재방문)

### CS-13. 사라진 XBRL 콘셉트 — COIN의 2.7년 묵은 TTM이 sanity bound을 통과한 사연 (#128)

- **증상**: 06-14 baseline 직전 점검. AAPL/AMZN/NVDA는 PR2(fy_end_month) + #70(EDGAR concept priority)로 in-band 복귀. **COIN만 여전히 fcf_yield 11.71%** (~5% 이상이 비현실적).
- **추적**: 진단 스크립트로 COIN의 raw cash_flow 행을 newest-first로 펼침:
  ```
  2026-03-31  None      ← 모든 최근 행 FCF=null
  2025-12-31  None
  ... (2024–2026 전부 None) ...
  2023-09-30  $0.93B    ← 가장 최근 non-null
  2023-06-30  $0.61B
  ```
- **원인**: EDGAR의 표준 `freeCashFlow` 콘셉트가 COIN의 2024 이후 filings에서 안 나옴 (issuer side의 XBRL 태그 변경 가능성). `_load_fundamentals_latest`의 null-skip 로직은 옛 row까지 walk back → `sum_ttm_fcf`가 period_end 데이터 없는 fall-back에서 `max(window)` = 2021 크립토 불런 시기의 $4.16B를 픽업. **±100% sanity bound는 unit/currency 에러용으로 설계됐기에 "값은 합리적이지만 2.7년 묵음" 케이스는 통과**.
- **수정**: `sum_ttm_fcf(rows, *, as_of: date)` 에 freshness guard 추가 — 가장 최근 non-null FCF row가 `FCF_STALENESS_MAX_DAYS=400` (≈13개월, 가장 긴 10-K 지연도 통과) 보다 묵으면 **None 반환** + `features.fcf_yield.stale_fundamentals` 워닝. 효과 (prod Neon 실측):
  ```
  COIN    legacy=  4.16B  guarded= None    ← 거짓 신호 제거
  UNH     legacy= 19.67B  guarded=19.67B   ← 변화 없음
  AAPL    legacy=129.17B  guarded=129.17B  ← 변화 없음
  ```
- **교훈**: **데이터 freshness는 별개 차원의 sanity check이다.** 우리의 sanity 박스(±100%, P/E ≤ 500 등)는 단위·통화 에러를 잡지만, "최근 N년이 통째로 비어 있어도 옛 값이 합리적 범위에 있으면 통과"하는 케이스를 못 잡는다. **upstream provider의 mapping은 조용히 깨질 수 있다** — XBRL 콘셉트가 바뀌면 인제스터는 에러를 안 내고 그냥 null을 채운다. Loader walk-back은 빈 구멍을 메우려고 만든 기능인데, 너무 멀리 walk back하면 같은 침묵 실패 가족이 된다. **각 잡힌 값에 "언제 측정됐는지" 메타가 따라다녀야 하고, 소비자는 그걸 무시할 수 있는 권리가 없다.**
- **이어진 발견 (UNH는 애초에 버그가 아니었음)**: 같은 진단 스크립트가 UNH도 함께 펼치자, Plan §5에 적혀 있던 `UNH (5.7% vs real ~3%)` 노트가 **검증되지 않은 의심**이었음이 드러났다. 우리 계산 $19.67B GAAP TTM / $371B mcap = 5.30%는 수학적으로 정확하고, UNH의 실제 연간 FCF 시계열($24B → $25B → $20.7B → $16.07B)의 5년 평균 ~$21B / 현 mcap = ~5.6%라 5.30%가 정상 수렴값. 외부의 "~3%"는 forward/normalized 추정(2024 사이버공격 회복 제외 + 미래 정상화 가정)으로 보이며, trailing GAAP yield와 비교했던 것 자체가 사과 vs 오렌지였다. **고칠 게 없었음을 진단으로 확인한 것 자체가 결과** — Phase B 때 누군가 외부 reference 메트릭의 정의를 명시하지 않고 "real ~3%"라 적어둔 노트가 한 분기 동안 "edge case" 리스트를 점거했다. 교훈: **외부 reference로 우리 계산을 의심할 때는 그 reference의 메트릭 정의를 먼저 확인하라** — 정의가 다르면 그건 버그가 아니라 별개 feature 요청.

---

## 6. 인프라 (재방문)

### CS-14. 14스텝 다 성공한 Job이 "실패"로 마킹된 사연 — idle-in-transaction이 죽인 advisory lock (#140 suppress + #143 commit)

- **증상**: Phase D 직전 컬럼(#132~#134) 배포 후 `gcloud run jobs execute tessera-ingest-daily --wait`가 **exit code 1**. 그런데 데이터는 멀쩡히 들어옴. 같은 코드가 어떤 run은 성공(hzmzk 07:04), 어떤 run은 실패(8mfkt 07:38, s5d4j 08:01).
- **추적**: 실패한 run의 로그를 `jsonPayload.event="ingest_daily.summary"`로 직접 조회하니 **세 run 전부 `passed=15, failed=0`**. summary는 08:01:18에 찍히고 execution은 08:01:23에 실패 종료 — **summary 이후 5초 안에 뭔가가 exit 1**. severity≥WARNING 로그를 당기자 `db.py`의 traceback: `try_advisory_lock`의 `__exit__`에서 `pg_advisory_unlock`을 실행하는 `conn.execute()`가 던짐. 성공한 run(hzmzk)은 4분, 실패한 run들은 8분+ 걸렸다는 게 결정타.
- **원인**: SQLAlchemy 2.0 future-mode는 첫 `execute()`에 암묵적 트랜잭션을 연다. advisory lock 전용 커넥션이 lock SELECT 후 commit 없이 run 내내 **idle-in-transaction**으로 앉아 있었다. Neon의 `idle_in_transaction_session_timeout`(~5분)이 8분짜리 run의 lock 커넥션을 중간에 강제로 끊음. run 종료 시 unlock을 시도하면 이미 죽은 커넥션에 말을 걸어 예외 → context manager 밖으로 전파 → `sys.exit(main())`이 비정상 종료 → **14스텝이 전부 성공했는데도 Cloud Run이 run 전체를 "Failed"로 마킹**. (이전에 'benign side effect'로 분류했던 그 현상 — 무해하지만 모니터링을 빨갛게 물들이는 범인.)
- **수정**: 두 겹.
  1. **증상 차단 (#140)** — unlock을 `contextlib.suppress(Exception)`로 감쌈. 어떤 이유로든 커넥션이 죽으면 서버가 disconnect 시 lock을 풀어주므로, teardown 단계에서 실패한 unlock 때문에 크래시하면 안 된다.
  2. **근본 원인 제거 (후속)** — lock 획득 직후 `conn.commit()`. 트랜잭션을 닫으면 커넥션이 plain *idle*(Neon이 안 죽임)이 되고, **session-level advisory lock은 commit 너머로 유지**된다 (`pg_advisory_unlock` 또는 disconnect만 푼다). 이제 lock이 run 전체를 실제로 보호하고 unlock도 살아있는 커넥션에서 동작.
- **교훈**: **"teardown에서 던지는 예외"는 작업 성공/실패를 거꾸로 뒤집는다.** 14스텝이 다 성공한 run을, 마지막 정리 한 줄의 예외가 exit 1로 만들었다. 두 가지 원칙: (1) **cleanup/finally 경로의 예외는 결과를 오염시키지 않게 격리**하라 (suppress 또는 로그-후-삼킴). (2) **장기 실행 작업이 잡은 DB 리소스는 트랜잭션 상태를 의식적으로 관리**하라 — "잡고 그냥 두면" 매니지드 Postgres(Neon/RDS)의 idle 리퍼가 조용히 끊는다. CS-12와 한 가족(종료 코드 정직성)이지만 방향이 반대다: CS-12는 진짜 실패를 삼켰고, CS-14는 진짜 성공을 실패로 뒤집었다.

### CS-15. 새 컬럼이 38개 중 1개만 채워진 사연 — loader가 annual 마커를 안 실어줌 (#144)

- **증상**: `fcf_yield_normalized`(#134) 배포 + Job 성공(exit 0) 후에도 prod `ticker_features`의 해당 컬럼이 **59개 중 단 1개**만 non-NULL. 코드는 돌았는데(features 스텝 ok) 값이 거의 다 NULL.
- **추적**: "재배포가 안 됐나? Job이 옛 이미지인가?"부터 의심했지만 — 이미지 태그(`094657`)는 #134 머지 *뒤* 빌드 확인, Job도 exit 0 확인. 즉 **새 코드가 돌았는데 함수가 거의 모두 None을 반환**. `compute_fcf_yield_normalized`를 따라가니 `_annual_income_rows(cash_rows)`로 연간 FY 행을 고르는데, 이 필터는 `period in ('FY','Q4') OR form=='10-K' OR fp=='FY'`. 그런데 `_load_fundamentals_latest`의 cash_rows는 `period`만 싣고 **`form`/`fp`는 안 실었다.** EDGAR-소스 cash_flow 행은 `period`가 NULL이고 form/fp로 연간을 표시 → ~39개 EDGAR 커버 티커 전부 연간 매칭 0 → `< 3` → None. 유일하게 통과한 1개는 FMP가 `period='FY'`를 명시해준 티커.
- **부수 원인**: cash bucket cap이 8행이라, form/fp를 실어줘도 분기 filer는 8행=2년치 → 5년 normalized엔 부족.
- **수정**: (1) `cash_sql`에 `form`/`fp` SELECT 추가 + bucket dict에 실어줌. (2) cap 8 → 24 (5+ 회계연도). 기존 trailing `sum_ttm_fcf`는 내부에서 `[:8]` 슬라이스라 무영향(안전). 재배포+execute 후 **norm 1 → 38** 확인.
- **교훈**: **"코드는 맞는데 값이 비어 있다"의 1순위 용의자는 배포가 아니라 그 함수에 들어가는 입력의 모양이다.** compute 함수(`_annual_income_rows`)가 가정한 필드(form/fp)를 loader가 안 실어주면, 함수는 에러 없이 조용히 빈 결과를 낸다 — CS-3/CS-13과 같은 침묵 실패 가족. 재사용 헬퍼(`_annual_income_rows`)를 새 데이터 소스(cash_rows)에 적용할 때는 **그 소스가 헬퍼의 전제 필드를 다 갖췄는지** 먼저 확인할 것. 그리고 디버깅 순서: "재배포 의심" 전에 **이미지 태그 시각 vs 머지 시각 + Job exit code**부터 확인하면 1분 만에 "코드는 돌았다"를 확정하고 입력 쪽으로 직행할 수 있다.

> **운영 메모 (CS-14/15 공통, deploy 워크플로 footgun)**: 같은 사건에서 `deploy_cloud_run_jobs.ps1 -ImageTag "20260615-002125"`가
> `Image 'mirror.gcr.io/library/...' not found`로 실패했다. 스크립트가 베어 태그를 full 레퍼런스로 그대로 gcloud에 넘겨 Docker Hub library 이미지로 오인된 것 (#139에서 베어태그/full 둘 다 받도록 수정 + `deploy_cloud_run.ps1`이 끝에 다음 Jobs 명령을 그대로 출력하도록 보강). 또 하나: `deploy_cloud_run_jobs.ps1`은 Job 정의(이미지)만 갱신한다 — features 재계산은 `gcloud run jobs execute ... --wait`를 따로 돌려야 일어난다. "배포했는데 데이터가 안 바뀐다"의 흔한 원인.

### CS-16. `CREATE TABLE IF NOT EXISTS`가 새 컬럼을 조용히 빠뜨릴 뻔한 사연 (#150 → 후속 fix)

- **증상**: Phase D 킥오프(#150)가 `012_users.sql`을 `CREATE TABLE IF NOT EXISTS users (...)` 형태로 추가하면서 `photo_url`/`last_login_at`을 포함시켰다. 운영자가 적용하기 직전, read-only 사전점검에서 prod에 **이미 `users` 테이블이 존재**(row 0)하는데 그 두 컬럼만 없는 걸 발견.
- **원인**: `users`(와 `user_portfolios`)는 사실 `001_init.sql §5 "User layer (Phase D)"`에 이미 정의돼 prod에 적용돼 있었다. 새 마이그레이션을 쓰면서 **기존 스키마를 확인하지 않았다.** 그대로 적용했다면 `CREATE TABLE IF NOT EXISTS`는 테이블이 있으니 **statement 전체를 no-op** → 두 신규 컬럼은 영영 안 생기고, 에러도 안 난다(인덱스 `CREATE INDEX IF NOT EXISTS`만 따로 실행돼 성공). 전형적인 "조용한 부분 성공".
- **수정**: 012를 추가(additive) 형태로 재작성 — `ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url ... / last_login_at ...`. `CREATE TABLE IF NOT EXISTS`는 신규/빈 DB 대비로 남기되, prod의 실제 작업은 ALTER가 한다. 적용 전 발견이라 prod 영향 0.
- **교훈**: **`CREATE TABLE IF NOT EXISTS`(그리고 `ADD COLUMN`이 아닌 모든 "전부 아니면 전무" DDL)는 기존 객체와 새 정의가 어긋날 때 그 차이를 조용히 삼킨다.** 새 마이그레이션을 쓰기 전에 `\d <table>`(혹은 `information_schema.columns`) 한 번으로 실제 스키마를 확인할 것. 그리고 운영자에게 넘기기 전 **read-only 사전점검으로 대상 객체의 현재 상태를 직접 보라** — 이번엔 그 한 번이 적용 직전 부분 no-op을 잡았다. 컬럼 추가는 항상 `ALTER ... ADD COLUMN IF NOT EXISTS`(멱등 + 기존 테이블에 실제로 동작).

### CS-17. Ray의 보라색 점이 사라진 사연 — Tailwind가 안 본 디렉터리의 클래스 (#170)

- **증상**: 랜딩(Desk)에서 Ray 카드만 이름 옆 **점**과 hover **글로우**가 안 떴다. Warren/Cathie/Peter는 정상.
- **추적**: Ray의 accent는 `plum`. 빌드된 CSS를 grep하니 `.bg-coral-500{`는 있는데 **`.bg-plum-500{`이 통째로 없었다.** `bg-plum-500` 리터럴이 어디 있나 보니 `lib/mock/personas.ts`의 `ACCENT_CLASS`(점/글로우가 쓰는 곳)와 `badge.tsx`의 `bg-plum-500/10`(opacity 변형 — solid 아님)뿐. 그런데 **Tailwind `content` 글로브가 `app/` + `components/`만 스캔하고 `lib/`는 빠져 있었다.** Tailwind는 *스캔한 파일에 리터럴로 나타난* 클래스만 생성한다 → `ACCENT_CLASS`의 클래스들은 사실 app/components 어딘가에 **우연히 중복 등장**해서 생성돼 왔던 것. `coral/sage/ink`는 다른 곳에도 리터럴이 있어 살아남았지만, `bg-plum-500`은 how-it-works 페이지에만 리터럴로 있었는데 **#147(how-it-works 압축)이 그 줄을 지우면서** 마지막 참조가 사라져 클래스가 CSS에서 증발 → plum을 쓰는 유일한 페르소나 Ray만 깨졌다. 에러도 빌드 실패도 없음.
- **수정(#170)**: `tailwind.config.ts`의 `content`에 `./lib/**/*.{ts,tsx}` 추가. 빌드 후 `.bg-plum-500{` 재생성 확인. (글로우는 accent hex 인라인으로도 보강.)
- **교훈**: **동적 클래스 레지스트리(`ACCENT_CLASS` 같은 "맵에 담아 런타임에 고르는" 클래스)는 그 파일이 Tailwind `content`에 없으면, 다른 곳의 중복 리터럴 덕에 *우연히* 동작할 뿐이다.** 그 중복을 리팩터가 지우면 가장 드문 값(plum=Ray 한 명)만 조용히 깨진다 — 침묵 실패 가족의 프런트엔드판. **클래스 이름 리터럴을 담는 모든 디렉터리(`lib/` 포함)를 `content`에 넣어라.** 그리고 색/배경처럼 "값마다 클래스가 다른" 패턴은 가능하면 인라인 style(hex)로 두는 게 JIT 누락에 안전하다.

---

### CS-18. 클라이언트는 멀쩡, 서버만 500 — neon이 돌려준 Date 객체와 `.slice` (#178)

- **증상**: 투자자 리더보드가 영원히 로딩 스피너. 같은 계좌-재구성 로직(`buildAccountIndex`)을 쓰는 대시보드 **차트는 정상**인데, 그걸 서버에서 호출하는 `/api/leaderboard/users`만 죽었다. 배포본 직접 호출 → **HTTP 500** `{"error":"leaderboard lookup failed"}`.
- **추적**: SQL은 psql/SQLAlchemy로 돌리면 멀쩡(1032행 반환). 차이는 **드라이버**였다. `@neondatabase/serverless`는 `timestamptz`/`date` 컬럼을 **JS `Date` 객체**로 반환한다(문자열 아님). 서버 라우트는 `follow_events.ts`를 그대로 `buildAccountIndex`에 넘기는데, 그 안에서 `e.ts.slice(0,10)` 호출 → `Date`엔 `.slice`가 없어 **throw** → 라우트 try/catch가 500으로. **클라이언트 경로는 왜 멀쩡했나**: 타임라인 API가 JSON으로 직렬화하면서 `Date`→ISO **문자열**이 되어 클라이언트엔 항상 문자열이 도착했기 때문. 같은 함수, 다른 입력 타입.
- **수정(#178)**: SQL 경계에서 `fe.ts::text`, `(ts::date)::text`, `id::text`로 캐스팅 → neon이 문자열을 반환(probe로 검증). 그리고 컴포넌트는 `!res.ok`일 때도 로딩 상태를 **반드시 해제**(빈 보드 표시)하도록 고쳤다 — 안 그러면 500이 무한 스피너로 둔갑(침묵 실패의 프런트판).
- **교훈**: **"SQL이 맞다"와 "런타임이 맞다"는 다르다 — 드라이버의 타입 매핑을 의심하라.** 같은 코드가 클라이언트(JSON 문자열)에선 동작하고 서버(드라이버 네이티브 타입)에선 깨질 수 있다. DB 값을 **순수 함수에 직접** 넘길 땐 경계에서 타입을 고정(`::text`)하거나 명시적으로 정규화하라. 그리고 모든 fetch는 **에러 응답에서도 로딩을 끝내야** 한다.

### CS-19. 표는 Cathie, 차트는 Warren — 가장 늦은 피드에 묶인 축 (#175/#177)

- **증상**: 사용자가 Warren→Cathie로 바꿨는데, 대시보드 **포지션 표**는 Cathie(맞음)인데 **계좌 곡선 차트의 마지막 구간은 여전히 Warren**. 게다가 전환 시 수익률이 0%로 리셋돼 보였다.
- **추적(둘)**: (1) **리셋** — 싱글팔로우 전환은 `user_portfolios` 행을 새 $100K로 재시드한다(행 = 팔로우). 그 행을 읽으면 이전 애널리스트의 손익이 사라진다. → 계좌 가치/수익률을 **`follow_events`에서 재구성**(since-first-follow)하도록 바꿈(#175). (2) **차트 끝이 Warren** — 계좌 곡선의 축을 **S&P(SPY) 날짜**로만 잡았는데, 시장데이터 인제스트가 페이퍼 스냅샷보다 **하루 늦다**(SPY 06-17까지, persona NAV 06-18까지). Cathie 전환이 06-18에 일어났으니 **축이 전환일 전에 끝나** 그 이벤트가 영영 처리되지 않음 → 마지막 구간이 Warren으로 남음.
- **수정(#177)**: 축 = **S&P ∪ persona 스냅샷 날짜 합집합**. 가장 늦은 소스에 끌려가지 않고 최신 persona 데이터까지 곡선이 그려진다.
- **교훈**: **파생 뷰의 시간 축을 "가장 늦게 갱신되는 입력"에 묶지 마라** — 모든 소스의 날짜 합집합을 쓰라. 안 그러면 오늘 일어난 상태 변화가 가장 느린 피드가 따라올 때까지 안 보인다. 그리고 **상태가 행에 덮어써지는(reseed) 모델에서 "누적" 지표는 행이 아니라 이벤트 로그에서 재구성해야** 한다 — 같은 침묵-왜곡이 표(현재 행)와 차트(이벤트)의 불일치로 드러났다.

---

## 메타 교훈 (발표 마무리 슬라이드용)

| # | 패턴 | 해당 케이스 |
|---|---|---|
| 1 | **침묵 실패가 1등 버그 클래스** — `suppress`/`except: pass`/`setdefault`/ok=True/무시된 exit code/통과해버리는 sanity bound/loader가 안 실어준 입력 필드/기존 객체에 no-op되는 `CREATE ... IF NOT EXISTS`/스캔 안 된 디렉터리의 Tailwind 클래스 드롭/에러 응답에서 로딩 안 끄는 무한 스피너로 빈 결과가 전부 실사고로 | CS-3,4,5,6,12,13,15,16,17,18 |
| 2 | **검증 장치는 자동이어야 의미가 있다** — 수동 캐너리는 없는 것과 같다 | CS-1, CS-6 |
| 3 | **LLM은 신뢰 경계 밖** — 날짜를 써주고, 산문을 덧붙이고, 형식을 어긴다. 파서·필드 권위·게이트가 방어선 | CS-4, CS-5 |
| 4 | **스키마/계약이 바뀌면 reader 전수조사** | CS-2 |
| 5 | **테스트 작성은 발견 행위** — 커버리지 숫자가 아니라 docstring의 거짓말을 찾는 일 | CS-7 |
| 6 | **운영 환경(셸·플랫폼)을 문서에 명시하고 그 환경에서 검증** | CS-8, CS-9, CS-10 |
| 7 | **LLM의 역할(Role) 몰입은 명시적 규칙(Rule)을 이길 수 있다** — 시스템 단의 통제가 필수적 | CS-11 |
| 8 | **데이터에는 시간 차원이 있다** — 값의 합리성과 신선도는 별개 검증, 둘 다 필요 | CS-13 |
| 9 | **외부 reference로 자기 계산을 의심하기 전에 reference의 정의부터 확인** — "real ~X%"라는 노트가 메트릭 정의 없이 남으면 한 분기 동안 가짜 backlog가 된다 | CS-13 (UNH 부수 발견) |
| 10 | **종료 코드 정직성은 양방향이다** — cleanup/finally의 예외가 성공한 작업을 실패로 뒤집을 수 있다. 장기 실행이 잡은 DB 리소스는 트랜잭션 상태를 의식적으로 관리 | CS-12(성공으로 위장한 실패) ↔ CS-14(실패로 위장한 성공) |
| 11 | **드라이버 타입 매핑을 의심하라** — 같은 코드가 클라이언트(JSON 문자열)와 서버(드라이버 네이티브 `Date`)에서 다르게 동작. DB 값을 순수 함수에 직접 넘길 땐 경계에서 타입 고정(`::text`) | CS-18 |
| 12 | **파생 뷰의 축을 가장 늦은 입력에 묶지 마라** — 날짜 축은 모든 소스의 합집합. 그리고 reseed(행 덮어쓰기) 모델의 "누적" 지표는 현재 행이 아니라 이벤트 로그에서 재구성 | CS-19 |

> 부록: 모든 케이스의 1차 자료는 PR 본문과 커밋 메시지에 있다 —
> #90, #93, #98, #99, #105–#108, #110, #111, #128, #139, #143, #144.
