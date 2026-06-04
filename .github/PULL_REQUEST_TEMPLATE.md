<!--
  ─────────────────────────────────────────────────────────────────────
  📝 작성 가이드 (지우지 말고 그대로 두세요. 머지 후엔 안 보임)

  처음이세요? CONTRIBUTING.md §2.0 "처음 PR 5분 튜토리얼" 참고.

  필수:
    1. 아래 What / Why 두 줄만 채우셔도 OK
    2. 본인 트랙 1개 체크
    3. "기본 체크" 5개 다 확인
    4. 본인 트랙의 acceptance 체크 (해당 없으면 비워둠)

  선택 (있으면 좋음):
    - How (변경 접근 / 결정)
    - Cost estimate (LLM 호출 PR이면 필수)
    - Migration checklist (schema 건드렸으면 필수)
    - Screenshots (UI 변경이면 좋음)

  PR title 형식:  <track>: <짧은 명령형>
    예) "llm: add Warren persona runner with prompt caching"
        "frontend: fix mobile nav overflow on /dashboard"
        "quant: add FCF yield + PEG features from FMP fundamentals"
  ─────────────────────────────────────────────────────────────────────
-->

## What
<!-- 1–3 줄. 이 PR이 뭘 바꾸는지. -->

## Why
<!-- 왜 이걸 하는지. Plan.md 어느 task / issue 번호. -->

## How  *(선택)*
<!-- 어떻게 접근했는지 / 주목할 결정. 큰 결정이면 ADR 링크. -->

---

## 트랙 (1개 체크)

- [ ] Frontend (한솔, 윤채)
- [ ] LLM Pipeline (한솔)
- [ ] Quant (예슬, 준원)
- [ ] Infra (준원)
- [ ] Docs / Persona voice (정우)
- [ ] Cross-track  → 어느 트랙들: ____________

---

## ✅ 기본 체크 (모든 PR 공통)

- [ ] PR title이 `<track>: ...` 형식
- [ ] API key / 비밀번호 / `.env` 출력 안 됨 (코드, 테스트, 로그 모두)
- [ ] 새 env var → `.env.example` 업데이트
- [ ] 새 deps → `pyproject.toml` / `package.json`에 버전 명시
- [ ] 우측 패널 Reviewers에 CODEOWNERS-지정 사람이 잡힘

---

## 🔍 트랙별 체크 *(해당 안 되는 섹션은 비워두세요)*

<details>
<summary><b>Frontend</b></summary>

- [ ] `npm run build` 통과 (apps/web)
- [ ] `npm run lint` 통과
- [ ] 모바일 (≥375 px) 깨짐 없음
- [ ] 새 data fetch → loading + error state 처리
- [ ] 색상은 `tailwind.config.ts` 토큰 사용 (hex 직접 X)
</details>

<details>
<summary><b>LLM Pipeline</b></summary>

- [ ] Pydantic 모델 정의 + 검증 통과
- [ ] Citation check 통과 (`cited_news_ids`가 `news` 테이블에 존재)
- [ ] Fixture / property test 1개+ 추가
- [ ] `cost_usd` + `tokens_in/out` 을 `llm_call_log`에 기록
- [ ] Prompt 변경 시 voice eval set 재실행
</details>

<details>
<summary><b>Quant</b></summary>

- [ ] `pytest tests/` 통과
- [ ] 새 feature → property test 추가
- [ ] 수익률 관련이면 canary assert (외부 데이터와 100 bps 이내)
- [ ] 새 column 필요하면 schema migration 동반 (NULL 허용)
</details>

<details>
<summary><b>Infra</b></summary>

- [ ] Dockerfile 변경 시 local build 성공
- [ ] Secret은 코드에 절대 안 들어감 (Secret Manager / Vercel env만)
- [ ] 새 logger → `httpx`/`urllib3`처럼 secret URL/header redact
- [ ] Cost 영향 있으면 description에 명시 (예: `+$2/mo Cloud Run`)
</details>

---

## 💰 LLM 비용 추정 *(Anthropic 호출 추가/변경 PR이면 필수)*

<!--
  예시:
    "chat backend SSE streaming 추가. Sonnet 4.6 ~$0.012/msg, caching 적용.
     현재 chat volume 기준 +$2–5/day. alert threshold 변경 없음."

  변경 없으면 "없음" 한 단어로 OK.
-->

없음 / ____________

---

## 🗄️ Schema migration *(스키마 건드린 경우만)*

- [ ] `migrations/NNN_*.sql` 새 파일, 다음 순번 N 사용
- [ ] Idempotent (`CREATE TABLE IF NOT EXISTS` 등)
- [ ] Staging Neon에 먼저 적용해서 검증

---

## 📸 Screenshots / output *(UI / 데이터 변경이면 좋음)*

<!-- Frontend: before/after. LLM: 예시 출력. Quant: 차트 또는 행 sample. -->

---

## 🔗 Linked

Closes #___
Refs `Plan.md` §___ , `architecture.md` §___
