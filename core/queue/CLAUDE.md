# core/queue — 큐 아키텍처 설계 가이드

> 이 파일은 `core/queue/` 하위 작업 시 AI가 반드시 읽어야 하는 설계 문서입니다.
> 에이전트 레벨 큐 설계(TaskMessage 사용 예, Brand Agent 연동 등)는
> `agents/brand/CLAUDE.md` 7절을 함께 참고하세요.

---

## 1. 역할

모든 에이전트(product, news, cafe, brand 등)가 공통으로 사용하는 작업 처리 인프라.

- **Task**: DB 테이블(`crawl_tasks`)로 관리. 별도 큐 인프라 없음.
- **Ingest**: 크롤링 결과를 Ingest Queue → IngestWorker → RawStore로 전달.

---

## 2. 파일 구조

```
core/queue/
├── CLAUDE.md           ← 이 파일
├── __init__.py         ← get_queue() / INGEST_QUEUE_NAME 외부 노출
├── backend.py          ← QueueBackend / LocalQueue / SQSQueue (Ingest Queue 전용)
├── log.py              ← QueueLogger (queue_log 테이블 연동)
├── task_worker.py      ← TaskWorker: crawl_tasks DB 폴링 → 에이전트 실행
├── ingest_worker.py    ← IngestWorker: Ingest Queue → Raw 레이어 적재
└── store_raw.py        ← RawStore: Raw 레이어 저장 (SQLite → S3 교체 가능)
```

---

## 3. 전체 흐름

```
[스케줄러 / run_site()]
        │ INSERT (run_id 발급, status='pending')
        ▼
┌─────────────────────┐
│   crawl_tasks (DB)  │  에이전트가 처리할 작업 목록 (URL / SKU / 키워드 등)
│  status: pending    │  ← agent_type별로 필터링
└──────────┬──────────┘
           │ SELECT FOR UPDATE SKIP LOCKED → status = 'processing'
           ▼
   TaskWorker
   (task_worker.py)    agent_type 보고 해당 에이전트 실행
           │
           ▼
   에이전트              Stealth 브라우저로 크롤링
   (product/news/brand/...)
           │
           ├─ 성공  → ingest_q.put(status='success') → crawl_tasks status = 'done'
           ├─ 차단  → ingest_q.put(status='blocked') → crawl_tasks status = 'done'
           │          (차단은 결과의 하나 — exception X, 재시도 X)
           └─ 실패  → exception raise → crawl_tasks retry_count++ → status = 'pending'
                          ↓ retry_count >= MAX_RETRY(3)
                      crawl_tasks status = 'failed' (DLQ 없음 — DB에서 직접 관리)
           ▼
┌─────────────────┐
│  Ingest Queue   │  크롤링 결과 대기열 (공통 1개: ingest)
└────────┬────────┘
         │ get(IngestMessage)
         ▼
   IngestWorker
   (ingest_worker.py)  Raw 레이어에 적재
         │
         ▼
   RawStore
   (store_raw.py)      sequence_num 저장 → 조회 시 ORDER BY sequence_num
```

**역할 분리 원칙**

- TaskWorker : crawl_tasks DB 폴링 → 에이전트 실행 → 상태 업데이트만 담당
- Agent : 수집 성공/차단 시 직접 Ingest Queue에 push (exception raise 시만 TaskWorker가 실패 처리)
- IngestWorker: Ingest Queue에서 꺼내서 RawStore에 저장만 담당

**차단(blocked) 처리 원칙**

차단은 예외(exception)가 아니라 수집 결과의 하나로 취급한다.
- `base_agent._is_blocked()` → True 시 해당 페이지 스킵
- 에이전트가 `ingest_q.put(IngestMessage, status='blocked')`로 직접 push
- TaskWorker는 status = 'done' 처리 (재시도 하지 않음)

> 차단을 재시도하지 않는 이유: 같은 IP로 재시도해도 차단이 풀리지 않으며,
> 프록시 교체는 `_is_blocked()` 내부에서 이미 처리한다.

---

## 4. crawl_tasks 테이블 (Task Queue 대체)

```sql
CREATE TABLE IF NOT EXISTS crawl_tasks (
    id           SERIAL PRIMARY KEY,
    task_id      TEXT UNIQUE NOT NULL,   -- UUID4
    run_id       TEXT NOT NULL,          -- 실행 단위 식별자 (같은 site_id라도 실행마다 다름)
    agent_type   TEXT NOT NULL,
    site_id      INTEGER NOT NULL,
    sequence_num SERIAL,                  -- 적재 순서 (결과 정렬용, DB 자동증가 — 에이전트가 직접 채우지 않음)
    payload_type TEXT NOT NULL,          -- "url" | "sku" | "keyword"
    payload      TEXT NOT NULL,
    metadata     JSONB DEFAULT '{}',     -- 에이전트별 부가 정보
    priority     INTEGER DEFAULT 0,      -- 0이 가장 높음 (낮을수록 먼저 처리)
    status       TEXT DEFAULT 'pending', -- pending | processing | done | failed
    retry_count  INTEGER DEFAULT 0,
    picked_at    TIMESTAMPTZ,            -- processing 전환 시각 (타임아웃 감지용)
    error_msg    TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 5. 작업 상태 전이

```
pending
   │ SELECT FOR UPDATE SKIP LOCKED
   ▼
processing  ← picked_at 기록
   ├─ 성공/차단 → done
   ├─ 실패 (retry_count < MAX_RETRY) → pending (retry_count++, picked_at = NULL)
   └─ 실패 (retry_count >= MAX_RETRY) → failed
```

**타임아웃 복구** — TaskWorker 폴링 시마다 실행:
```sql
UPDATE crawl_tasks
SET status = 'pending', picked_at = NULL, updated_at = NOW()
WHERE status = 'processing'
AND picked_at < NOW() - INTERVAL '30 minutes';
```
> 에이전트가 processing 상태에서 죽으면 영원히 처리 안 됨 → 30분 경과 시 자동 pending 복구

**작업 꺼내기** — 동시에 여러 에이전트가 같은 작업 안 가져가도록:
```sql
SELECT * FROM crawl_tasks
WHERE status = 'pending' AND agent_type = %(agent_type)s
ORDER BY priority ASC, created_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

**실패 처리** — DLQ 없음. status='failed'로 DB에서 직접 관리:
```sql
-- 실패 건 조회
SELECT * FROM crawl_tasks WHERE status = 'failed' ORDER BY updated_at DESC;

-- 수동 재처리: retry_count 초기화 후 pending 복구
UPDATE crawl_tasks SET status = 'pending', retry_count = 0 WHERE status = 'failed';
```

**실패 시 상태 전이는 반드시 단일 UPDATE로** — retry_count 증가와 status 변경을 두 쿼리로 나누면
크래시 시 retry_count는 올랐는데 status가 pending으로 안 돌아오는 불일치가 발생한다:
```sql
-- TaskWorker 실패 처리 (exception catch 시 이 쿼리 한 방만 실행)
UPDATE crawl_tasks
SET
    retry_count  = retry_count + 1,
    status       = CASE
                     WHEN retry_count + 1 >= 3 THEN 'failed'
                     ELSE 'pending'
                   END,
    picked_at    = NULL,
    error_msg    = %(error_msg)s,
    updated_at   = NOW()
WHERE id = %(id)s AND status = 'processing';
```
> `AND status = 'processing'` 조건: 이미 타임아웃 복구로 상태가 바뀐 row를 실수로 덮어쓰는 것을 방지한다.

---

## 6. IngestMessage 스키마

```python
IngestMessage = {
    "ingest_id":    str,   # UUID4
    "task_id":      str,   # 원본 crawl_tasks의 task_id
    "run_id":       str,   # crawl_tasks의 run_id 그대로 전달 — 실행 단위 조회에 사용
    "agent_type":   str,
    "site_id":      int,
    "sequence_num": int,   # crawl_tasks의 sequence_num 그대로 전달 — DB SERIAL로 자동 채번, 에이전트가 직접 채우지 않음
    "crawled_at":   str,   # ISO8601 UTC
    "payload_type": str,
    "source_url":   str,   # 실제 수집한 페이지 URL
    "data":         dict,  # 에이전트가 수집한 결과
    "status":       str,   # "success" | "blocked"
    "error_msg":    str,
}
```

> `status`에 `"failed"`가 없는 이유: 수집 실패는 exception → TaskWorker가 crawl_tasks 상태 업데이트.
> Ingest Queue에는 성공/차단 결과만 들어온다.

---

## 7. Ingest Queue — backend.py

Ingest Queue는 QueueBackend 인터페이스로 관리한다.

```python
class QueueBackend:
    def put(self, message: dict) -> str: ...       # message_id 반환
    def get(self) -> tuple[str, dict] | None: ...  # (receipt_handle, message), 없으면 None
    def ack(self, handle: str): ...                # 처리 완료 — 큐에서 삭제
    def nack(self, handle: str, delay_sec=0): ...  # 재처리 예약(재적재)만 담당

class LocalQueue(QueueBackend):
    """개발/테스트용. Python queue.Queue 기반. 프로세스 재시작 시 초기화됨."""

class SQSQueue(QueueBackend):
    """운영용. boto3 기반."""
    def __init__(self, queue_name: str): ...
```

| 구간 | 큐 이름 | 로컬 | 운영 |
| ---- | ------- | ---- | ---- |
| Ingest Queue | `ingest` (공통 1개) | `LocalQueue` | AWS SQS |

- Task Queue는 DB(`crawl_tasks`)로 대체되어 QueueBackend 미사용
- SQS 전환 시 `QueueBackend` 서브클래스만 교체 — IngestWorker 코드 무변경

---

## 8. 절대 규칙

| 규칙 | 이유 |
| ---- | ---- |
| `status = 'done'`은 저장 완료 후에만 업데이트 | 저장 실패 시 작업 유실 방지 |
| 실패 처리는 retry_count 증가 + status 변경을 단일 UPDATE로 | 두 쿼리로 나누면 크래시 시 retry_count/status 불일치 발생 |
| 새 agent_type 추가 시 `crawl_tasks` 필터링 확인 | agent_type 오타 시 작업 영원히 pending |
| `LocalQueue`는 운영 환경 사용 금지 | 프로세스 재시작 시 메시지 초기화됨 |
| 큐 작업마다 `QueueLogger` 호출 필수 | 이력 없으면 장애 판단 불가 |
| 타임아웃 복구 쿼리는 TaskWorker 폴링마다 실행 | processing 상태 영속 방지 |

---

## 9. 구현 순서

```
1. crawl_tasks 테이블 생성 (DB 마이그레이션)
2. backend.py     — QueueBackend / LocalQueue / SQSQueue (Ingest 전용)
3. log.py         — QueueLogger + queue_log 테이블 생성
4. __init__.py    — get_queue() / INGEST_QUEUE_NAME
5. task_worker.py — TaskWorker (DB 폴링 + 타임아웃 복구)
6. ingest_worker.py / store_raw.py — IngestWorker / RawStore
7. 에이전트 수정  — run_site() → crawl_tasks INSERT 패턴으로 전환
```
