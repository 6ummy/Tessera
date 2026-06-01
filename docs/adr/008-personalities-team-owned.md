# ADR-008: Open `personalities.md` ownership to the whole team

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-19 |
| **Authors** | @6ummy |
| **Tracks affected** | Persona Voice (primary), All |
| **Supersedes** | [ADR-004](004-four-personas-and-voice-gatekeeper.md) (단독 gatekeeper 부분만; 4-페르소나 구성 결정은 유효) |
| **Related** | `.github/CODEOWNERS` (personalities.md line), `CONTRIBUTING.md` §0 & §2.3 |

---

## Context

ADR-004는 두 가지를 결정했습니다:
1. **4명 페르소나** (Warren / Cathie / Ray / Peter) — 페르소나 구성
2. **정우 단독 voice gatekeeper** — `personalities.md` 변경/머지 권한

(1)은 product 컨셉 자체라 유효. 이 ADR은 (2)만 뒤집습니다.

Phase B 진입하면서 발견한 것:
- 윤채/한솔 (LLM Pipeline)이 페르소나 thesis 작성하며 spec 조정 욕구가 빈번해짐 (예: hard rule 정교화, voice few-shot 예시 추가)
- 예슬 (Quant)이 새 feature 추가할 때 페르소나가 그 feature를 활용하도록 spec에 mention 필요
- 매번 정우 단독 머지를 거쳐야 하는 게 **병목**으로 작동
- 또한 정우 본인이 `personalities.md` PR을 보내면 다른 owner가 없어 admin bypass 필요 (chicken-and-egg)

원래 ADR-004의 우려 (voice drift, cross-pollination) 재평가:
- 4명 팀이 매주 정기 sync하면 voice 일관성은 사회적 메커니즘으로 유지 가능
- PR review에서 voice diff 자연스럽게 catch
- 정우는 여전히 CODEOWNERS에 포함되어 모든 변경을 notification 받음
- 분산 ownership이 실제로 drift 일으키면 그때 ADR-XXX로 다시 좁힐 수 있음 (되돌리기 비용 낮음)

## Decision

`personalities.md`의 CODEOWNERS를 **팀 4명 전원**으로 확장.

```
# CODEOWNERS — 변경 후
personalities.md   @6ummy @limserenahansol @yunchai-build @genius-chang
```

운영 룰:
- 누구나 `personalities.md` PR 보낼 수 있고, 누구나 approve 가능 (자기 PR 제외)
- **큰 변경 (페르소나 추가/삭제, hard rules 수정)**은 PR 만들기 전 카톡 `#tessera`에서 가볍게 합의
- **작은 변경 (voice few-shot 예시 추가, typo, formatting)**은 바로 PR
- 분기별로 정우가 random sample 5개 thesis 보면서 voice drift 모니터링 (눈으로 catch되면 PR로 정정)

## Alternatives Considered

### Alt 1: ADR-004 유지 (정우 단독)
**거절 이유**: Phase B 들어가면서 병목 확실히 됨. 정우 본인 PR도 self-approve 불가로 매번 admin bypass 필요. 운영 비용이 voice 일관성 이득보다 큼.

### Alt 2: "Deputy gatekeeper" 1명 추가 (정우 + 한솔)
정우 + 한솔 둘만 owner.
- **거절 이유**:
  - 윤채/예슬도 페르소나 thesis 작성/feature 추가 시 spec 만지기 때문에 owner에서 빼면 또 병목
  - 4명 작은 팀에서 굳이 sub-tier 만들 이유 부족
  - 모두 owner 두는 게 정보 비대칭 줄임

### Alt 3: Voice 변경은 issue + 라벨 + 토론 후 정우가 PR
변경은 항상 정우 손으로, 다른 사람은 제안만.
- **거절 이유**:
  - 제안 → 정우 → PR → 머지 4단계 vs PR 직접 1단계
  - Friction이 voice 개선 자체를 위축시킴 — Phase B에서 활발한 voice 튜닝이 필요

### Alt 4: Auto-approval, review 없음
머지 자유 그 자체 — branch protection만 통과하면 OK.
- **거절 이유**:
  - voice는 디자인 결정이라 최소 1명 review 가치 있음
  - 4명 owner면 review 1명은 거의 자동으로 받아짐 → 마찰 거의 0
  - 완전 자유는 drift 위험만 커짐

## Consequences

### Positive
- **병목 제거** — 정우 부재 시에도 voice 개선 PR 흐름 정지 안 됨
- **분산 책임** — 팀 전체가 voice quality에 owner-ship 느낌
- **빠른 iteration** — Phase B의 voice 튜닝 사이클이 빨라짐
- **정우 본인 PR도 정상 흐름** — 다른 owner가 approve 가능 (admin bypass 불필요)

### Negative
- **Voice drift 위험 증가** — 4명이 각자 의도 살짝 다른 변경하면 일관성 흐려질 가능성
- **"내가 만진 부분만 신경 쓰는" 부분 최적화** — 전체 voice 큰 그림 누군가 책임 안 짐 (정우가 분기 모니터링으로 보완)
- **결정 책임 모호** — "왜 이렇게 voice 바뀌었지?" git blame이 분산됨 (mitigation: 큰 변경은 ADR 동반)

### Neutral / 관찰할 것
- **분기별 voice eval set 결과** — drift 측정. 페르소나별 known-good thesis sample이 새 spec으로 regenerate했을 때 같은 voice인지.
- **PR 빈도 + 머지 시간** — 병목 해소 효과 정량 측정 (3개월 평균 비교).
- **외부 contributor PR** — `personalities.md` 외부 PR 받았을 때 어떻게 처리할지 별도 가이드 필요해질 수도.

## Verification

- ✅ CODEOWNERS 업데이트 → 팀 4명 모두 owner
- ✅ CONTRIBUTING.md §0 + §2.3 업데이트 (정우 단독 gatekeeper 표현 제거)
- ✅ ADR-004 status: `Accepted` → `Superseded by ADR-008`
- 미래 (3개월 후): voice eval set 통과율 변화 측정 — 분산 ownership 후에도 페르소나 confusion 없음 확인. drift 감지되면 ADR-XXX로 정책 재검토.

## Notes / Open Questions

- **외부 contributor의 `personalities.md` PR** — open-source인지라 외부 사람이 페르소나 voice 변경 PR을 보낼 수 있음. 정책: 외부 PR은 자동 라벨 + 정우가 추가 review (트랙 owner 외).
- **5번째 페르소나 도입 시점에 재검토** — 페르소나 수 늘면 voice 일관성 부담 증가. 그때 다시 single gatekeeper로 좁힐지 결정.
- **Voice "deputy" 명시 가능성** — 만약 분산이 너무 자유로워 보이면, 한 명 (한솔?)을 "voice lead"로 지명하는 중간 단계 고려.
