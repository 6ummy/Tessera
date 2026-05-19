# ADR-007: Make repo public (open-source) instead of upgrading to paid GitHub plan

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-18 |
| **Authors** | @6ummy |
| **Tracks affected** | All (governance), Infra |
| **Supersedes** | — |
| **Related** | `.github/CODEOWNERS`, `CONTRIBUTING.md` welcome banner |

---

## Context

Phase A 끝나고 4명 팀이 합류하기로 결정한 시점에, GitHub branch protection +
CODEOWNERS enforcement 셋업을 시도했습니다. 발견한 사실:

> **GitHub Free + Private repo은 branch protection rules가 enforcement되지 않습니다.**
> UI에서 룰을 만들 수 있지만 저장만 될 뿐 실제로 main 직접 push를 막지 않습니다.

확인 메시지:
> "Your protected branch rules for your branch won't be enforced on this private
> repository until you move to a GitHub Team or Enterprise organization account."

선택지:
1. **현 상태 (Free private)** — branch protection 작동 안 함. 운영 약속만으로.
2. **GitHub Pro ($4/월)** — 개인 계정 private repo에서 일부 enforcement.
3. **GitHub Team ($4/user/월)** — org 계정 필요. 4명 = $16/월.
4. **Public 전환** — 모든 enforcement 무료. 단점은 코드/docs 공개.

작은 팀 (4명) + 솔로 owner + paper-trading pilot에 어느 게 맞는지 결정 필요.

## Decision

**Public 전환.** GitHub Free + public repo에서 branch protection 전 기능 무료로
사용. 모든 enforcement (require PR, require approval, require codeowners,
block force push 등) 작동.

부가적으로:
- repo 자체가 portfolio/연구 artifact 성격
- `personalities.md`, `architecture.md`, ADR 등 흥미로운 공개 자료
- 외부 사람 fork/contributor 받을 수 있는 길 열림

## Alternatives Considered

### Alt 1: GitHub Pro ($4/월) — private 유지
- 개인 계정 그대로 + 일부 기능 unlock
- **거절 이유**:
  - 정작 우리가 필요한 "Require review from Code Owners" enforcement는 Pro에서도 일부 제약 (Team 또는 Public에서 완전 동작)
  - 월 $4 자체는 작지만 — Free + public이 모든 기능 unlock하는데 굳이 결제할 이유 부족
  - 결제하면 vendor lock 발생 (취소하면 private이 다시 enforcement 잃음)

### Alt 2: GitHub Team ($4/user/월)
- Org 계정 전환 + 모든 기능 + 권한 관리 세분화
- **거절 이유**:
  - $16/월 (4인) — 파일럿 단계엔 과한 fixed cost
  - Org 전환 자체가 작업 (repo 이전, URL 변경, settings 다 재설정)
  - 4인 팀에 Team 권한 모델은 over-engineered

### Alt 3: Free private + 운영 약속만 (no enforcement)
- 비용 0, 비공개 유지
- 룰은 CONTRIBUTING.md에 쓰고 honor system
- **거절 이유 (시도 후 거절)**:
  - 실제 시도 → main 직접 push가 막히지 않음 확인. branch protection이 사실상 장식이 됨.
  - 4명 팀이지만 git 경험 differs → 실수로 main에 push할 위험 실재
  - "약속" 기반 운영은 incident 발생 후 후회 — 자동 차단이 안전
  - 우리는 client-side git hook 옵션도 고려했으나 (scripts/git-hooks/pre-push) 이 또한 bypass 가능 (`git push --no-verify`)

### Alt 4: Mirror 패턴 (private에 개발 + 별도 public mirror)
- 내부엔 private repo, 외부엔 public 거울
- Enforcement는 private에서, 공개는 mirror로
- **거절 이유**:
  - 두 repo 동기화 운영 부담
  - branch protection은 여전히 private 쪽에서 안 됨 → 핵심 문제 해결 안 됨
  - 솔로 dev 수준에선 과한 setup

## Consequences

### Positive
- **모든 branch protection enforcement 무료**: require PR, require approval, require CODEOWNERS, block force push, restrict deletions, require linear history 다 작동
- **외부 contributor 가능** — fork → PR → CODEOWNERS reviewer 자동 지정
- **Portfolio value** — personalities.md, architecture.md, ADR 시리즈가 공개 artifact로서 가치 (Tessera를 보고 합류하고 싶은 사람이 코드 보고 판단 가능)
- **CI 무료 분량 더 많음** (public repo는 GitHub Actions 무제한, private은 월 한도)
- **결제 0 — pivot 시 손해 없음**

### Negative
- **모든 코드/docs 공개** — 트레이드시크릿 노출 위험 점검 필요. 다행히:
  - `.env`는 gitignore, secret 0
  - persona spec(personalities.md)은 공개해도 본질 가치는 운영 + 데이터에 있음, 단순 복제 불가
  - 페르소나 prompt는 published spec으로 봐도 OK (오히려 학술/오픈소스 가치)
- **fork 가능** — 누군가 우리 코드로 경쟁 서비스 만들 수 있음. 트레이드 — 코드보다 운영/데이터/voice consistency가 진짜 moat라고 판단.
- **Public 후 private으로 되돌리려면 history도 함께 노출된 후** — 한 번 공개한 코드는 archive.org 등에 영구 보존 가능. 결정 되돌리기 어려움.
- **Compliance** — public이라 외부에서 PR로 sensitive 변경 시도 가능. CODEOWNERS + 정우 review로 막음.

### Neutral / 관찰할 것
- **External contributor 빈도** — 0~5명/월 예상. 많아지면 issue triage 부담 → CONTRIBUTING.md "외부 PR은 정우가 추가 review" 룰 적용.
- **README 업데이트** — open-source라는 점 분명히 (현재 banner에 명시)
- **License 추가 검토** — 현재 license 파일 없음. MIT 또는 BSL 검토 필요 (별도 ADR 또는 단순 LICENSE 파일 추가).

## Verification

- ✅ Public 전환 후 main 직접 push 시도 → `GH013: protected branch hook declined` 에러 (의도된 동작)
- ✅ Branch protection rules 저장 + 작동 확인 (Settings → Branches)
- ✅ CODEOWNERS auto-routing 작동 확인 (PR 만들면 우측 패널에 reviewer 자동 표시)
- 미래: 외부 PR 1개 받아서 process 완주 — 외부 contributor 흐름 검증

## Notes / Open Questions

- **LICENSE 추가** — 현재 없음. MIT, Apache 2.0, BUSL 등 검토 (별도 issue 또는 ADR).
- **외부 contributor가 personalities.md 변경 PR 보내면** — CODEOWNERS로 정우 단독 owner이므로 정우가 voice judgment하면 됨. 거절도 정중하게.
- **Trade-secret 발생 시점** — 우리만의 데이터 (사용자 행동, 백테스트 결과 등) 누적되면 private fork 또는 별도 데이터 layer 필요. 현재 모든 데이터는 외부 공개 데이터(시세 + 뉴스). 진짜 private은 사용자 portfolio + chat 기록 — 이건 Neon DB에 있고 repo엔 안 들어감.
- **Repo description / topics** — GitHub topics (`ai`, `llm`, `finance`, `multi-agent`, `paper-trading`) 추가하면 discoverability 향상.
