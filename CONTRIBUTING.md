# Contributing to Tessera

환영합니다. 이 문서는 팀원이 어떻게 작업을 시작하고, 무엇을 책임지고,
PR을 어떻게 보내고 머지하는지 적은 운영 매뉴얼입니다.

처음 합류하시면: `README.md` → `architecture.md` → `Plan.md` →
`personalities.md` 순서로 한 번 훑어보시고 이 문서로 돌아오세요.

---

## 0. 팀 & 트랙

| 트랙 | 담당 | 핵심 책임 영역 |
| **Frontend** | 한솔 | Next.js UI, UX 폴리시, 모바일 반응형, 시각화, real-data swap |
| **LLM Pipeline** | 윤채, 한솔 | Anthropic SDK 연결, prompt assembly, Pydantic validation, citation check, chat backend |
| **Quant** | 예슬 | Feature engineering, fundamentals 활용, backtest harness, risk gateway, performance attribution |
| **Infra** | 윤채 | Cloud Run 배포, GCP IAM/Secret, GitHub Actions CI, Sentry/Grafana, cost alerts |
| **All** | 정우 | 전체 코디네이션, 페르소나 voice 게이트키퍼, compliance 준비, 모든 PR 참여 |

---

## 1. 브랜치 rule

**Trunk-based + short-lived feature branches.** 

- `main` — 항상 deploy 가능한 상태. 직접 push 금지. PR 통해서만 변경.
- `feature/<track>/<short-desc>` — feature 브랜치. 보통 1~5일 안에 머지.
- `fix/<track>/<short-desc>` — 버그 fix.
- `chore/<short-desc>` — 의존성 업데이트, 정리 작업.
- `docs/<short-desc>` — 문서 변경만.

### Branch 이름 예시

```
feature/frontend/xxx (Frontend, 한솔)
for example:
    feature/frontend/mobile-test

feature/llm/xxx (LLM Pipeline, 윤채, 한솔)
for example: 
    feature/llm/persona-runner-skeleton  
    feature/llm/warren-thesis-end-to-end
    fix/llm/pydantic-retry-on-schema-fail

feature/quant/xxx (quant, 예슬)
for example: 
    feature/quant/fcf-yield-from-fundamentals

feature/infra/xxx (Infra, 윤채)
for example: 
    feature/infra/cloud-run-deploy

```

### 머지 규칙

- **Squash merge** 기본 (커밋 history 깔끔하게).
- 머지 메시지: 처음에 트랙 prefix (예: `llm: add Warren persona runner`).
- 머지 직후 feature 브랜치 자동 삭제 (GitHub 설정).
- main에 머지되면 Vercel이 자동으로 frontend 재배포.

### Rebase vs Merge

작업 중 main이 앞서 갔으면 **rebase** (merge commit 안 만들기):

```bash
git fetch origin
git rebase origin/main
```

Conflict 나면 그 자리에서 해결 후 `git rebase --continue`.


### Push 예시

# 1. 본인 로컬을 main 최신으로 맞춤
git checkout main
git pull

# 2. 새 branch 만들기 (작업명)
git checkout -b feature/llm/warren-first-thesis

# 3. 코드 작성 + 커밋
# ... 파일 수정 ...
git add .
git commit -m "llm: add Warren persona runner"

# 4. 브랜치를 GitHub에 push
git push -u origin feature/llm/warren-first-thesis

여기까지 하면 push 결과에 이런 URL이 나옴:
remote: Create a pull request for 'feature/llm/warren-first-thesis' on GitHub by visiting:
remote:      https://github.com/6ummy/Tessera/pull/new/feature/llm/warren-first-thesis

# 5. 그 URL 클릭 → GitHub PR 페이지 열림

우리가 만든 .github/PULL_REQUEST_TEMPLATE.md가 자동으로 description에 채워짐
"What / Why / How" 채우고, 체크박스 확인 (채울게 없으면 그냥 적당히 적어주시면 됩니다)
우측 패널에 CODEOWNERS가 지정한 reviewer가 자동으로 추가돼 있음
"Create pull request" 클릭

# 6. Reviewer가 보고, Approve (merge) → main에 들어감 → branch 자동 삭제
결과: 
[PR #42] llm: add Warren persona runner

Files changed (3)  •  Reviewers: 한솔 (pending), 정우 (pending)
─────────────────────────────────
What: Warren persona runner that calls Sonnet 4.6...
Why:  Plan.md Phase B Week 2 deliverable...
─────────────────────────────────
[Diff of changed files in green/red]
[Comments thread]
[Approve / Request changes / Comment] (reviewer 보는 버튼)
[Merge pull request] (모두 approve되면 활성화)
---

## 2. PR 흐름

### 흐름
1. **Issue 먼저** (가능하면) — 무엇을 왜 하는지 적고 라벨 (track + type).
2. **Branch 생성** — 위 네이밍 규칙대로.
3. **작업 + 로컬 테스트** — 본인 트랙의 acceptance 체크 (3절).
4. **PR 오픈** — `.github/PULL_REQUEST_TEMPLATE.md` 자동으로 채워짐. 모든 체크박스 확인.
5. **CODEOWNERS 자동 reviewer 지정**됨 — track 담당자가 자동으로 review 요청 받음.
6. **Reviewer가 ✓** 또는 변경 요청 → 처리 후 다시 push.
7. **CI green + 1+ approval → 머지** (Squash).
8. **머지 후**: 본인 브랜치 삭제, deploy 확인 (frontend면 Vercel, worker면 Cloud Run).

### Reviewer 1명 룰

- 본인 트랙 PR은 **본인이 review 1명 + 정우(@6ummy) 자동**. 정우는 모든 PR auto-reviewer.
- 두 트랙 걸치는 PR (예: shared 스키마 변경) → 양쪽 트랙 review 모두 필요.
- 긴급 fix면 정우 단독 approve로 머지 가능.

### Conflict zones — 특히 조심

- `personalities.md` → **정우만** 변경 권한 (CODEOWNERS로 강제. Personalities add 할때 추가 파일 애드후 정우가 merge). 페르소나 voice는 디자인 결정, 분산되면 일관성 깨짐.
- `migrations/NNN_*.sql` → 번호 race condition. PR 보내기 직전 main의 latest 번호 확인하고 다음 번호 사용.
- `packages/shared/tessera_shared/schemas.py` → LLM/Frontend/Quant 셋 다 의존. 변경 시 **3 트랙 review 모두** 필요.

---

## 3. 트랙별 acceptance 체크 (PR 머지 전)

PR 보내기 전에 본인 트랙 체크 항목을 다 통과해야 합니다.

### Frontend
- [ ] `npm run build` 통과 (apps/web)
- [ ] `npm run lint` 통과
- [ ] 모바일 가로/세로 둘 다 깨짐 없음 (Chrome DevTools 375px 이상)
- [ ] 새 컴포넌트면 loading + error state 둘 다 처리
- [ ] 색상은 `tailwind.config.ts`의 디자인 토큰 사용 (hex 직접 박지 말기)

### LLM Pipeline
- [ ] Pydantic 모델 정의 + 검증 통과
- [ ] Citation check 통과 (`cited_news_ids` 모두 DB에 존재)
- [ ] Property test 또는 fixture test 1개 이상
- [ ] LLM 호출 시 `cost_usd` + `tokens_in/out` 로깅
- [ ] Prompt 변경 시 voice eval set 재실행 (`tests/persona_voice/`)
- [ ] 비용 dashboard에 영향 없음 또는 명시 (예: `+$5/day on review pass`)

### Quant
- [ ] Property test 추가 (`hypothesis`)
- [ ] Canary assert 추가 (외부 데이터와 10 bps 이내)
- [ ] `pytest tests/` 13/13 + 신규 통과
- [ ] feature 추가 시 schema 마이그레이션 동반 (NULL 허용 column으로)

### Infra
- [ ] Dockerfile 변경 시 local build 성공
- [ ] Secret은 코드에 절대 commit 금지 (Secret Manager만)
- [ ] Logger 추가 시 → `httpx`/`urllib3` 패턴처럼 시크릿 URL/header 가리는지 확인
- [ ] Cost 영향 예상 → PR description에 명시 (예: `+$2/mo Cloud Run`)

### 모든 트랙 공통
- [ ] PR description에 무엇/왜/어떻게 명확히
- [ ] Sensitive data (API key, DB password) 출력 안 됨 (테스트 로그 포함)
- [ ] 새 env var 추가 시 `.env.example` 업데이트
- [ ] 새 deps 추가 시 `pyproject.toml` / `package.json` 명시

---

## 4. 일정 (Phase 단위)

`Plan.md`의 6주 일정을 트랙별로 펼친 것입니다.

### Week 1 — Phase A→B 전환

| 트랙 | Deliverable | 산출물 |
|---|---|---|
| **Frontend (한솔)** | 모바일 반응형 audit + 3 PR로 fix | issue 3개 → PR 3개 머지; chat backend 스트리밍 통합 spec 1장 |
| **LLM (윤채+한솔)** | Warren 1명 first real thesis (Sonnet 호출 → Pydantic 통과 → DB 저장) | `agents/runner.py` + `agents/prompt.py` + 첫 `analyst_reports` row |
| **Quant (예슬)** | 3개 new feature (FCF yield, PEG, EPS CAGR 3y) + property test | `compute.py` 확장 + `tests/test_features.py` 16/16; 백테스트 harness 설계 doc |
| **Infra (윤채)** | Worker Dockerfile + Cloud Run deploy + Vercel WORKER_WEBHOOK_URL wire | deployed URL + Vercel cron이 실제로 worker 깨움; GitHub Actions CI 기본 (lint+typecheck) |
| **All (정우)** | 위 모든 파트 기여여

**Week 1 종료 조건**: Anthropic 호출 1개 성공, Cloud Run 배포 완료, web/mobile 깨짐 0건. mockup 말고 실제 backend 연결결


## 5. 로컬 dev 환경 셋업

처음 합류하면 이 순서대로:

```bash
# 1. Repo clone
git clone https://github.com/6ummy/Tessera.git
cd Tessera

# 2. Frontend
cd apps/web
npm install
npm run dev                 # → http://localhost:3000

# 3. Worker (Python 3.11+ 필요)
cd ../worker
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash; macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

# 4. 환경변수 받기
cp .env.example .env
# → 정우(@6ummy)에게 .env 값 요청 (sensitive한 키는 공유 예정)

# 5. 연결 확인
PYTHONIOENCODING=utf-8 python scripts/check_connections.py
# → 6/6 ✓ 떠야 정상

# 6. 한 번 daily orchestrator 돌려보기
python -m tessera_worker.jobs.ingest_daily --only ohlcv_equity features
```

> Anthropic 키는 dev/staging/prod 분리합니다.

---

## 6. 커밋 메시지 컨벤션 (가볍게)

 다만 머지 메시지(squash 제목)는 트랙 prefix 권장:

```
llm: add Warren persona runner with prompt caching
frontend: fix mobile nav overflow on /dashboard
quant: add FCF yield + PEG features from FMP fundamentals
infra: deploy worker to Cloud Run, wire Vercel WORKER_WEBHOOK_URL
docs: clarify Phase B acceptance criteria in Plan.md
chore(web): bump next 14.2.18 → 14.2.35
```
---

## 7. 비용 & 보안 룰 

1. **Production API key를 dev/local에 절대 쓰지 마세요.** 
2. **새 API source 추가 시 → `logging.py` redaction 패턴 확인.** Phase A에서 두 번 leak됨 (httpx INFO 레벨, FMP error URL). 새 로거 추가하면 `logging.WARNING`으로 silence.
3. **`.env`, secret 파일 never commit.** `.gitignore`에 들어있지만 한 번 더 `git status`로 확인.

---

## 8. 의사결정 — Architecture Decision Records (ADR)

큰 결정 (스키마 변경, 도구 추가, persona 가설 변경)은 `docs/adr/NNN-short-title.md`에 기록.

ADR 한 장 = 무엇을 결정했고, 왜 그렇게 했고, 다른 옵션은 무엇이었고, 무엇이 trade-off였는지. 미래의 본인 + 신규 합류자가 30초 안에 맥락 잡을 수 있게.

템플릿: [`docs/adr/000-template.md`](docs/adr/000-template.md) · 사용 규칙은 [`docs/adr/README.md`](docs/adr/README.md)

---

## 9. 도움 요청 / 막힐 때

- **막힘**: GitHub issue로 olar `help-wanted` 라벨, 또는 Slack의 `#tessera` 채널 (TODO: 셋업)
- **긴급**: 정우(@6ummy) 직접 DM
- **외부 API down**: 본인 외 다른 사람이 이미 처리 중일 수 있음. 먼저 issue 검색.

---

## 10. 합류자 첫날 체크리스트

- [ ] Repo clone, `npm run dev` 띄움 (frontend 정상)
- [ ] Worker venv 셋업, `check_connections.py` 6/6 ✓
- [ ] 본인 트랙의 코드 위치 파악 (위 1절 + `architecture.md` 6절 파일맵)
- [ ] 본인 트랙의 Week 1 deliverable 확인 (4절)
- [ ] CODEOWNERS에 본인 핸들 들어있는지 확인 (`.github/CODEOWNERS`)
- [ ] PR template 한 번 읽기 (`.github/PULL_REQUEST_TEMPLATE.md`)
- [ ] 본인용 dev API 키 받음 (Anthropic, Alpaca paper)

---

이 문서는 항시 업데이트 되는는 운영 메뉴얼입니다. 
