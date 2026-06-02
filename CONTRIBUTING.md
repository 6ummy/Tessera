# Contributing to Tessera

환영합니다. 이 문서는 팀원이 어떻게 작업을 시작하고, 무엇을 책임지고,
PR을 어떻게 보내고 머지하는지 적은 운영 매뉴얼입니다.

처음 합류하시면: `README.md` → `architecture.md` → `Plan.md` →
`personalities.md` 순서로 한 번 훑어보시고 이 문서로 돌아오세요.

> Tessera는 **public open-source pilot**입니다. 코드는 공개돼 있고, GitHub
> branch protection이 활성화돼 있어 모든 변경은 PR을 통해서만 main에 들어
> 갑니다 (직접 push 금지). 외부 contributor의 issue/PR도 환영입니다.

> **🆕 Git/GitHub 처음이신 분**: 너무 걱정 마세요. 아래 순서로 보시면 됩니다.
> 1. **§0.5 한 줄 용어 사전** — branch, commit, PR이 뭔지 1분 안에
> 2. **§2.0 첫 PR 5분 튜토리얼** — 복사·붙여넣기로 따라하기
> 3. **§2.4 흔한 에러 + 해결법** — 막힐 때마다 여기
>
> 첫 PR 한 번만 해보면 그 다음부터는 같은 흐름 반복입니다.

---

## 0. 팀 & 트랙

| 트랙 | 담당 | GitHub | 핵심 책임 영역 |
|---|---|---|---|
| **Frontend** | 한솔 | @limserenahansol | Next.js UI, UX 폴리시, 모바일 반응형, 시각화, real-data swap |
| **LLM Pipeline** | 윤채, 한솔 | @yunchai-build, @limserenahansol | Anthropic SDK 연결, prompt assembly, Pydantic validation, citation check, chat backend |
| **Quant** | 예슬, 준원 | @genius-chang, @jlee0810 | Feature engineering, fundamentals 활용, backtest harness, risk gateway, performance attribution |
| **Infra** | 윤채, 준원 | @yunchai-build, @jlee0810 | Cloud Run 배포, GCP IAM/Secret, GitHub Actions CI, Sentry/Grafana, cost alerts |
| **All** | 정우 | @6ummy | 전체 코디네이션, compliance 준비, 모든 PR 참여 |

> **Persona voice는 팀 공동 책임** (ADR-008로 변경됨). `personalities.md`를
> 누구나 PR로 변경 + approve 가능. 큰 변경 (페르소나 추가, hard rules 수정)
> 시 카톡에서 가볍게 합의 후 PR.

---

## 0.5 Git/GitHub 용어 한 줄 사전

처음 보시면 의미만 머리에 넣고, 막힐 때 다시 돌아오세요.

| 용어 | 한 줄 |
|---|---|
| **repo (repository)** | 프로젝트 저장소. `https://github.com/6ummy/Tessera`가 우리 repo. |
| **clone** | repo를 내 컴퓨터에 복사해 오는 것. 한 번만 함. |
| **commit** | 변경사항 묶음 + 메시지를 history에 기록하는 단위. "저장 + 라벨". |
| **branch** | 작업 분기. `main`은 안정판, `feature/...`는 내 작업방. |
| **push** | 내 컴퓨터의 commit들을 GitHub에 올림. |
| **pull** | GitHub의 최신 변경을 내 컴퓨터로 가져옴. |
| **PR (Pull Request)** | "내 branch를 main에 합쳐 달라"는 요청. GitHub 페이지에서 만듦. |
| **merge** | PR이 승인되어 main에 합쳐지는 것. |
| **squash merge** | 여러 commit을 1개로 합쳐서 머지. 우리는 이거만 씀. |
| **rebase** | 내 branch를 main 최신 위로 옮기는 것. conflict 해결할 때. |
| **conflict** | 같은 줄을 두 사람이 다르게 고쳐서 git이 자동으로 못 합칠 때. |
| **CODEOWNERS** | "이 파일은 누가 리뷰하나"를 미리 정해둔 파일. PR 만들면 자동으로 그 사람한테 알림. |
| **CI (Continuous Integration)** | PR 만들 때 자동으로 돌아가는 검사 (lint, build, test). green ✅이면 통과. |

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
# (또는 GitHub repo 페이지 상단의 노란 "Compare & pull request" 배너)

# ⚠️ 배너는 push 후 ~1시간 안에만 뜸. 그 후엔 URL 패턴 직접 입력:
#    https://github.com/6ummy/Tessera/pull/new/<branch-name>
# (예: https://github.com/6ummy/Tessera/pull/new/feature/llm/warren-first-thesis)
# Push 출력에서 URL 못 본 경우, 또는 force-push로 다시 만든 경우 이 패턴 사용.

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

### 2.0 처음 PR 한 번 해보기 — 5분 튜토리얼

워밍업으로 docs 변경 1줄짜리 PR을 만들어 봅시다. 흐름을 익히는 게 목적.

**Step 1. 작업 시작 전 main 최신으로 맞춤**
```bash
cd Tessera          # repo 폴더로 이동
git checkout main   # main 브랜치로 전환
git pull            # GitHub의 최신 main 가져옴
```

**Step 2. 새 branch 만들기**
```bash
git checkout -b docs/<본인이름>-onboarding
# 예시: git checkout -b docs/hansol-onboarding
```

**Step 3. 아무 1줄 고침**
- `CONTRIBUTING.md` 열어서 typo 하나 찾아 고침, 또는 본인 이름 옆에 작은 코멘트 추가.

**Step 4. 변경사항 commit**
```bash
git status                                # 뭐가 바뀌었는지 확인
git add CONTRIBUTING.md                   # 바뀐 파일을 staging
git commit -m "docs: fix typo in §X"      # commit 메시지
```

**Step 5. GitHub에 push**
```bash
git push -u origin docs/<본인이름>-onboarding
```

성공하면 출력 끝에 이런 URL이 나옵니다:
```
remote: Create a pull request for 'docs/...' on GitHub by visiting:
remote:      https://github.com/6ummy/Tessera/pull/new/docs/...
```

**Step 6. URL 클릭 → PR 생성**
- GitHub PR 페이지가 열림.
- description에 `.github/PULL_REQUEST_TEMPLATE.md` 내용이 **자동으로 채워져 있음**.
- "What / Why / How" 짧게 채움 (typo fix면 "fix a small typo" 정도면 충분).
- 우측 패널 보면 **Reviewers**에 자동으로 사람들이 잡혀 있음 (CODEOWNERS가 해줌).
- 페이지 맨 아래 **"Create pull request"** 클릭.

**Step 7. Reviewer가 ✓ 누르면 Squash merge**
- 정우가 알림 받고 review → ✓ Approve.
- PR 페이지 맨 아래 **"Squash and merge"** 초록색 버튼이 활성화됨 → 클릭 → Confirm.
- 머지되면 본인 branch는 자동 삭제. main이 업데이트되고 Vercel이 재배포.

축하합니다, 첫 PR 끝. 이게 모든 작업의 기본 흐름입니다.

---

### 표준 흐름
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

- `personalities.md` → **팀 전체 owner** (ADR-008). 누구나 PR + approve 가능. 다만 voice 일관성 유지 위해 페르소나 추가/삭제, hard rules 큰 변경은 카톡에서 사전 합의 권장.
- `migrations/NNN_*.sql` → 번호 race condition. PR 보내기 직전 main의 latest 번호 확인하고 다음 번호 사용.
- `packages/shared/tessera_shared/schemas.py` → LLM/Frontend/Quant 셋 다 의존. 변경 시 **3 트랙 review 모두** 필요.

### 2.4 흔한 에러 + 해결법

#### 🔴 `error: failed to push some refs ... Updates were rejected`
누가 먼저 main에 머지했다는 뜻. 내 branch를 최신 main 위로 올려야 함.
```bash
git fetch origin
git rebase origin/main
# conflict 나면 파일 수정 후
git add <충돌난 파일>
git rebase --continue
# 이후 다시
git push --force-with-lease
```

#### 🔴 `remote: error: GH006: Protected branch update failed`
main에 직접 push하려고 한 경우. branch를 만들어서 PR로 가야 함.
```bash
git checkout -b feature/<track>/<desc>
git push -u origin feature/<track>/<desc>
# 그 다음 GitHub UI에서 PR 생성
```

#### 🟡 Merge conflict (PR 페이지에 빨간 "This branch has conflicts" 뜸)
GitHub 웹에서 풀리는 단순 conflict면 거기서 처리. 복잡하면 로컬에서:
```bash
git checkout feature/<my-branch>
git fetch origin
git rebase origin/main
# 충돌 파일을 에디터로 열어 <<<<<<<, =======, >>>>>>> 사이를 정리
git add <파일>
git rebase --continue
git push --force-with-lease
```

#### 🔴 CI 빨갛게 ❌ (status check failed)
PR 페이지에서 "Details" 클릭 → 어느 단계가 깨졌는지 확인 → 로컬에서 같은 명령:
- Frontend: `npm run build` / `npm run lint` (apps/web 안에서)
- Worker: `pytest tests/` (apps/worker 안에서)
- 고친 다음 `git commit` + `git push` → CI 자동 재실행.

#### 🟡 실수로 main에 commit해버렸을 때 (아직 push 안 함)
```bash
# 마지막 commit을 새 branch로 옮기기
git branch feature/<track>/<desc>     # 현재 위치에 새 branch 라벨
git reset --hard origin/main          # main을 원격 상태로 되돌림
git checkout feature/<track>/<desc>   # 새 branch로 이동
git push -u origin feature/<track>/<desc>
```

#### 🔴 `.env` 실수로 commit하려 할 때
`.gitignore`에 이미 있지만 한 번 더 확인:
```bash
git status              # .env가 보이면 큰일
git restore --staged .env   # staging에서 빼기
```

#### 🟡 PR 만들었는데 reviewer가 자동 지정 안 됨
- `.github/CODEOWNERS`에 본인 GitHub 핸들이 정확히 있는지 확인.
- 해당 reviewer가 repo collaborator로 추가돼 있는지 정우(@6ummy)에게 확인 요청.

#### 🟡 "I don't have permission to push" 비슷한 에러
- 정우(@6ummy)가 본인을 collaborator로 추가했는지 확인 (Settings → Collaborators).
- 안 됐으면 정우에게 GitHub 핸들 보내고 invite 요청.

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

- **PR/git 흐름이 막힘**: 먼저 §2.4 "흔한 에러 + 해결법"에 답이 있는지 확인.
- **그 외 막힘**: GitHub issue로 `help-wanted` 라벨, 또는 Slack `#tessera` 채널 (TODO: 셋업).
- **긴급**: 정우(@6ummy) 직접 DM.
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
- [ ] **§2.0 "처음 PR 5분 튜토리얼" 따라서 실제로 PR 1개 만들어봄** ← 가장 중요

---

이 문서는 항시 업데이트 되는는 운영 메뉴얼입니다. 
