# 크롤링 플랫폼 — 전체 프로세스 메모

> 개인 학습/참고용. 세부 사항은 각 CLAUDE.md 참고.
> 마지막 업데이트: 2026-06-19

---

## 1. 프로젝트 개요

멀티 사이트 웹 크롤링 플랫폼. React 웹 대시보드에서 사이트 등록/설정/실행/결과 확인을 관리한다.

- **Backend**: FastAPI (port 8000) + PostgreSQL
- **Frontend**: React 18 + Vite (port 5173)
- **브라우저**: Playwright + playwright_stealth (봇 차단 우회)
- **에이전트**: product / news / cafe / promotion / banner / directory / brand / order
- **처리 방식**: DB + Queue 기반 비동기 (crawl_tasks DB → 에이전트 → Ingest Queue → Medallion)

---

## 2. 전체 파이프라인

```
[1] UI — 사이트 등록 + 크롤링 실행 요청 (run_id 발급)
        에이전트 타입 결정 (product / news / cafe / brand / banner / directory / order)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  URL / 작업 확보 방식
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [Mode A (자동 배치)]
        자사 시스템 상품 데이터 유입 (랭킹/카테고리 기준 N건)
              ↓
        Discovery Agent — 브랜드 공홈 상품 URL 매핑
              ├─ brand_url_mapping DB에 URL 존재 → 바로 반환
              └─ 없음 → 브랜드 공홈 탐색 → DB 저장 → URL 반환
              ↓
        crawl_tasks DB 적재 (status='pending')

  [Mode B (수동)]
        사용자가 URL / 키워드 직접 입력
              ↓
        URL 검증 (Playwright Stealth — urllib 단순 HTTP 사용 금지)
              ↓
        crawl_tasks DB 적재 (status='pending')

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  이후 공통 (모든 에이전트)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[2] crawl_tasks (DB) — agent_type별 필터링
        run_id로 같은 site_id라도 실행 건 구분 가능

[3] TaskWorker — crawl_tasks 폴링 → agent_type 보고 에이전트 실행
        Brand Agent는 dispatcher.py → brand_type으로 브랜드별 engine.py 라우팅

[4] 에이전트 — Stealth 브라우저로 크롤링
        ├─ 성공  → ingest_q.put(status='success') → crawl_tasks status='done'
        ├─ 차단  → ingest_q.put(status='blocked') → crawl_tasks status='done'
        │          (HTTP 200이지만 봇차단 페이지. 차단은 결과의 하나 — exception X)
        └─ 실패  → exception raise → retry_count++ → crawl_tasks status='pending' (재시도)
                       ↓ MAX_RETRY(3) 초과
                   crawl_tasks status='failed' (DLQ 없음 — DB에서 직접 관리)

[5] Ingest Queue — 공통 1개 (ingest)

[6] IngestWorker — Ingest Queue에서 꺼내 RawStore에 저장

[7] Medallion
        Raw → Bronze → Silver → Gold
```

---

## 3. 큐/DB 구조

| 구간 | 방식 | 이름/위치 | 비고 |
|------|------|----------|------|
| Task | DB 테이블 | `crawl_tasks` | 별도 큐 인프라 없음 |
| Ingest Queue | Queue | `ingest` | 공통 1개 |
| DLQ | 없음 | — | `status='failed'`로 DB에서 직접 관리 |

---

## 4. 핵심 설계 결정

| 항목 | 결정 |
|------|------|
| Task Queue → DB | `crawl_tasks` 테이블로 대체. 별도 큐 인프라 불필요 |
| DLQ 제거 | `status='failed'`가 DLQ 역할. SQL로 바로 조회/재처리 가능 |
| 실패 처리 | retry_count < MAX_RETRY → pending 복구 / 초과 → failed |
| 타임아웃 복구 | processing 30분 경과 시 자동 pending 복구 (에이전트 죽음 대비) |
| 차단(blocked) | exception 없이 return → status='done'. ingest에 status='blocked'로 기록 |
| run_id | crawl_tasks/IngestMessage 모두 포함. 같은 site_id 실행 건 구분용 |

---

## 5. agents/brand/CLAUDE.md 수정 필요 항목

core/queue/CLAUDE.md와 불일치하는 부분:

- [x] **Task Queue → crawl_tasks DB로 전환** — TaskMessage 스키마 → crawl_tasks 테이블 컬럼으로 변경
- [x] **run_id 추가** — crawl_tasks/IngestMessage 모두 포함 필요
- [x] **DLQ 관련 내용 전체 제거** — dlq_task, dlq_ingest, nack→dlq 전이 모두 삭제
- [x] **IngestMessage status에서 "failed" 제거** — 실패는 crawl_tasks status='failed'. Ingest에는 success/blocked만
- [x] **파일 위치 수정** — `core/queue.py` 단일 파일 → `core/queue/` 디렉토리 구조로 변경
- [x] **큐 사용 예시 수정** — `task_brand_cartier`(방식 3) → crawl_tasks DB INSERT 패턴으로 전환
