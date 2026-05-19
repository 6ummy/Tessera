# ADR-002: One Postgres (Timescale + pgvector) instead of separate time-series, OLTP, and vector stores

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-18 |
| **Authors** | @6ummy |
| **Tracks affected** | Quant, LLM Pipeline, Infra |
| **Supersedes** | — |
| **Related** | `architecture.md` §3 stack, `migrations/001_init.sql` |

---

## Context

Tessera는 세 가지 종류의 데이터를 저장해야 합니다.

1. **시계열** — OHLCV 분/일봉, 매크로 시리즈 (FRED 20개). 수만 row, append-mostly, 시간 범위 쿼리 위주.
2. **관계형** — 페르소나 포트폴리오, 거래 ledger, 사용자, fundamentals (jsonb). ACID 트랜잭션 필요 (특히 paper engine).
3. **벡터** — 페르소나 메모리 (과거 thesis), 뉴스 임베딩. 코사인 유사도로 recall.

전통적 답은 **3개의 다른 DB**: InfluxDB/Timescale Cloud + Postgres + Pinecone/Weaviate.
우리는 그것을 거절했습니다.

## Decision

**Neon Postgres 하나에 다 담는다.** 활성화한 extensions:

- **TimescaleDB** — `ohlcv_1d`를 hypertable로. Continuous aggregate (예: 분봉 → 일봉) 지원.
- **pgvector** — `news.embedding VECTOR(1536)`, `persona_memory.embedding VECTOR(1536)`. ivfflat 인덱스로 ANN 검색.
- **uuid-ossp** — UUID PK 생성.

`migrations/001_init.sql` 하나로 전체 schema (14 테이블) + 3 extensions 셋업. Neon free tier에서 작동.

## Alternatives Considered

### Alt 1: Timescale Cloud (시계열) + Neon Postgres (관계형) + Pinecone (벡터)
각 도구가 자기 영역에서 최고. 대규모 production에선 표준 패턴.
- **거절 이유**:
  - 3개 dashboard, 3개 결제, 3개 connection string, 3개 backup 정책
  - 트랜잭션이 cross-DB로 갈 수 없음 — paper engine이 ohlcv 읽고 ledger 쓰는 게 한 트랜잭션이어야 안전
  - 벡터 + 관계형 join이 안 됨 (예: "이 ticker의 최근 thesis 5개" 쿼리)
  - Free tier 합쳐서 월 $100~200 → 파일럿엔 과함
  - Phase A 단계의 데이터 규모(~14k OHLCV row, 555 news, 13k features)에 Pinecone/Timescale Cloud는 over-provisioned

### Alt 2: DynamoDB + S3 + OpenSearch (AWS-only)
- **거절 이유**:
  - 우리 stack은 GCP (Cloud Run) + Vercel. AWS 추가는 IAM/billing/네트워크 다중화
  - Pydantic/SQLAlchemy 같은 익숙한 도구 못 씀, DynamoDB SDK 학습 필요
  - 시계열에 DynamoDB는 partition key 설계가 까다로움

### Alt 3: SQLite + Faiss (로컬 only)
파일럿용으로 가장 간단.
- **거절 이유**:
  - Vercel 서버리스 함수가 같은 SQLite 파일을 못 공유
  - Cloud Run 잡이 동시 실행되면 lock contention
  - Backup, replication, point-in-time recovery 없음 → 운영 곤란

### Alt 4: Postgres만 (TimescaleDB 없이) + 직접 시계열 쿼리
Postgres 인덱스만으로 시계열 가능.
- **거절 이유**:
  - 시계열 쿼리 (특정 기간 다중 ticker aggregate)에서 성능 차이가 큼
  - Continuous aggregate 같은 편의 기능 직접 짜야 함
  - TimescaleDB는 Neon이 native 지원 — 추가 비용 0

## Consequences

### Positive
- **운영 단순**: 하나의 connection pool, 하나의 backup, 하나의 monitoring
- **트랜잭션 일관성**: paper engine이 시세 읽고 ledger 쓰는 작업이 ACID로 묶임
- **Join 가능**: "Cathie의 최근 thesis 5개의 cited_news 임베딩 평균" 같은 쿼리 한 번에 가능
- **무료**: Neon free tier (0.5GB) + TimescaleDB + pgvector 다 무료. Phase A 데이터(~50MB)는 한참 멀었음
- **SQL이 universal interface**: 신규 합류자가 새로운 DB 쿼리 언어 학습 안 함

### Negative
- **Postgres에 묶임** — 만약 timescale 한계 도달 (1B+ row) 또는 벡터 검색 latency 한계 도달 시 전환 비용 발생. 현실에선 파일럿 + 첫 1년은 한참 멀음.
- **Neon vendor lock-in** — Neon serverless 기능 (branching, autoscale) 활용 시 다른 Postgres host로 옮길 때 작업 필요. 다만 우리는 stock Postgres 기능만 써서 마이그레이션 부담 낮음.
- **단일 장애점**: Neon down → 모든 plane 정지. Trade-off — 분리하면 partial down 가능하지만 ops 부담 증가.

### Neutral / 관찰할 것
- 데이터 크기 — Phase B 이후 (실 LLM theses + news 1년치) 1GB 넘으면 Neon paid ($19/mo) 검토.
- 벡터 검색 latency — `ivfflat` 인덱스가 row 수가 늘수록 정확도/속도 trade-off. 10만 row 넘으면 HNSW로 전환 (재인덱스 시간 1시간 내).

## Verification

- ✅ `001_init.sql` 14 테이블 + 3 extensions free tier 통과
- ✅ Phase A end-to-end: 14k OHLCV + 13k features + 555 news + 255 fundamentals 모두 1 DB
- ✅ Paper engine 단일 트랜잭션 가능 (이론적, Phase C에서 검증 예정)
- 미래: 데이터 크기 800MB 도달 시 paid 전환 결정. 벡터 recall p99 < 100ms 유지.

## Notes / Open Questions

- HNSW 인덱스 (ivfflat 대안)로 전환 시점은 row 수가 결정 — 100k 도달 시 검토.
- Neon branch 기능을 dev/staging 분리에 활용 검토 (지금은 단일 DB).
