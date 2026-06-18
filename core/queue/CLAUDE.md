# core/queue — 큐 아키텍처 설계 가이드

> 이 파일은 `core/queue/` 하위 작업 시 AI가 반드시 읽어야 하는 설계 문서입니다.
> 에이전트 레벨 큐 설계(TaskMessage 사용 예, Brand Agent 연동 등)는
> `agents/brand/CLAUDE.md` 7절을 함께 참고하세요.

---

## 1. 역할

모든 에이전트(product, news, cafe, brand, local 등)가 공통으로 사용하는 큐 인프라.
에이전트 코드는 `QueueBackend` 인터페이스만 사용하고, 로컬/SQS 구현체는 몰라도 된다.

---

## 2. 파일 구조

```
core/queue/

├── CLAUDE.md           ← 이 파일
├── __init__.py         ← get_queue(), TASK_QUEUE_MAP 외부 노출
├── backend.py          ← QueueBackend / LocalQueue / SQSQueue
├── log.py              ← QueueLogger (queue_log 테이블 연동)
├── task_worker.py      ← TaskWorker: Task Queue → 에이전트 실행 → ack/nack 결정
├── ingest_worker.py    ← IngestWorker: Ingest Queue → Raw 레이어 적재
└── store_raw.py        ← RawStore: Raw 레이어 저장 (SQLite → S3 교체 가능)
```

---

## 3. 전체 흐름

```
[스케줄러 / run_site()]
        │ put(TaskMessage)  ← sequence_num 부여 (0, 1, 2, ...)
        ▼
┌─────────────────┐
│   Task Queue    │  에이전트가 처리할 작업 대기열 (URL / SKU / 키워드 등)
└────────┬────────┘
         │ get(TaskMessage)
         ▼
   TaskWorker          agent_type 보고 해당 에이전트 실행
   (task_worker.py)
         │
         ├─ 성공 → 에이전트가 ingest_q.put(IngestMessage) → TaskWorker ack()
         └─ 실패 → TaskWorker nack() → 재시도 → retry >= MAX_RETRY → DLQ
         ▼
┌─────────────────┐
│  Ingest Queue   │  크롤링 결과 대기열
└────────┬────────┘
         │ get(IngestMessage)
         ▼
   IngestWorker        Raw 레이어에 적재
   (ingest_worker.py)
         │
         ▼
   RawStore (store_raw.py)  ← sequence_num 저장 → 조회 시 ORDER BY sequence_num
```

**역할 분리 원칙**

- TaskWorker : Task Queue에서 꺼내서 에이전트 실행 + ack/nack 결정만 담당
- Agent : 수집 성공 시 직접 Ingest Queue에 push (실패는 exception raise → TaskWorker가 nack)
- IngestWorker: Ingest Queue에서 꺼내서 RawStore에 저장만 담당

| 구간         | 로컬 (현재)                         | 운영 (SQS 전환 시)        |
| ------------ | ----------------------------------- | ------------------------- |
| Task Queue   | `LocalQueue` (Python `queue.Queue`) | AWS SQS (agent_type별 큐) |
| Ingest Queue | `LocalQueue`                        | AWS SQS (`ingest-queue`)  |
| DLQ          | `LocalQueue`                        | AWS SQS DLQ               |

- Redis 미사용
- SQS 전환 시 `QueueBackend` 서브클래스만 교체 — 에이전트/워커 코드 무변경

---

## 4. backend.py — QueueBackend 인터페이스

```python
class QueueBackend:
    def put(self, message: dict) -> str: ...       # message_id 반환
    def get(self) -> tuple[str, dict] | None: ...  # (receipt_handle, message), 없으면 None
    def ack(self, handle: str): ...                # 처리 완료 — 큐에서 삭제
    def nack(self, handle: str, delay_sec=0): ...  # 처리 실패 — 재처리 예약

class LocalQueue(QueueBackend):
    """개발/테스트용. Python queue.Queue 기반. 프로세스 재시작 시 초기화됨."""

class SQSQueue(QueueBackend):
    """운영용. boto3 기반."""
    def __init__(self, queue_name: str): ...
```

---

## 5. **init**.py — get_queue() / TASK_QUEUE_MAP

```python
# 에이전트 타입 → Task Queue 이름 매핑 (방식 2: 에이전트별 큐)
TASK_QUEUE_MAP = {
    "product":  "task_product",
    "news":     "task_news",
    "cafe":     "task_cafe",
    "brand":    "task_brand",
    "banner":   "task_banner",
    "directory":"task_directory",
    "order":    "task_order",
    "local":    "task_local",
}

def get_queue(name: str) -> QueueBackend:
    """큐 이름으로 인스턴스를 반환한다. 환경변수 USE_SQS=1 이면 SQSQueue 반환."""
```

사용 예:

```python
from core.queue import get_queue

task_q   = get_queue("task_local")   # Task Queue
ingest_q = get_queue("ingest")       # Ingest Queue
dlq      = get_queue("dlq_ingest")   # DLQ
```

---

## 6. 메시지 스키마

### 6.1 TaskMessage

```python
TaskMessage = {
    "task_id":      str,   # UUID4
    "agent_type":   str,   # "local" | "product" | "brand" | ...
    "site_id":      int,
    "sequence_num": int,   # enqueue 순서 (0부터) — 재시도로 ingest 순서가 바뀌어도 원래 순서 보존
    "payload_type": str,   # "url" | "sku" | "keyword"
    "payload":      str,   # 실제 처리 값
    "metadata":     dict,  # 에이전트별 부가 정보 (자유 형식)
    "priority":     int,   # 0이 가장 높음
    "retry_count":  int,
    "created_at":   str,   # ISO8601 UTC
}
```

### 6.2 IngestMessage

```python
IngestMessage = {
    "ingest_id":    str,   # UUID4
    "task_id":      str,   # 원본 TaskMessage의 task_id
    "agent_type":   str,
    "site_id":      int,
    "sequence_num": int,   # TaskMessage의 sequence_num 그대로 전달 — RawStore에 저장
    "crawled_at":   str,   # ISO8601 UTC
    "payload_type": str,
    "source_url":   str,   # 실제 수집한 페이지 URL
    "data":         dict,  # 에이전트가 수집한 결과
    "status":       str,   # "success" | "blocked"
    "error_msg":    str,
}
```

> `status`에 `"failed"`가 없는 이유: 수집 실패는 에이전트가 exception을 raise하여
> TaskWorker가 nack → DLQ로 처리한다. Ingest Queue에는 성공/차단 결과만 들어온다.

---

## 7. log.py — QueueLogger

`queue_log` 테이블에 메시지 상태 변화를 기록한다.

```sql
CREATE TABLE IF NOT EXISTS queue_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_name   TEXT    NOT NULL,
    message_id   TEXT    NOT NULL,
    agent_type   TEXT,
    site_id      INTEGER,
    status       TEXT    NOT NULL,  -- enqueued | dequeued | acked | failed | dlq
    retry_count  INTEGER DEFAULT 0,
    error_msg    TEXT,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);
```

상태 전이:

```
put()  → enqueued
get()  → dequeued
ack()  → acked
nack() → failed  (retry_count < MAX_RETRY)
nack() → dlq     (retry_count >= MAX_RETRY)
```

---

## 8. DLQ

`retry_count >= MAX_RETRY(3)` 시 DLQ로 이동. **DLQ 적재는 TaskWorker가 담당한다.**

```
에이전트 실패 (exception raise)
        ↓
TaskWorker → nack() → Task Queue 재적재 (retry_count: 0→1→2)
        ↓ retry_count >= 3
TaskWorker → dlq.put(msg) + task_q.ack(handle)
           → queue_log(status="dlq") 기록
```

TaskWorker의 ack/nack/DLQ 처리 흐름:

```python
try:
    agent.fetch_product(url)       # 성공 시 에이전트가 ingest_q.put()
    task_q.ack(handle)
except:
    msg["retry_count"] += 1
    if msg["retry_count"] >= MAX_RETRY:
        dlq.put(msg)               # DLQ 적재
        task_q.ack(handle)         # 원본 큐에서 제거
    else:
        task_q.nack(handle, delay_sec=60)  # 재시도 예약
```

**DLQ 이후 처리:**

- `queue_log` 테이블에 `status='dlq'`로 기록 (자동)
- 웹 UI에서 DLQ 실패 목록 조회 가능하도록 구현 예정 (site_id / payload / retry_count / error_msg 표시)
- 원인 파악 후 `scripts/replay_dlq.py` 로 DLQ → 원본 Task Queue 재적재 (수동)

> **TODO**: DLQ 현황 UI 페이지 또는 사이트별 실패 뷰 구현 (CrawlResults 혹은 별도 페이지)

---

## 9. 절대 규칙

| 규칙                                          | 이유                               |
| --------------------------------------------- | ---------------------------------- |
| `ack()`는 저장 완료 후에만 호출               | 저장 실패 시 메시지 유실 방지      |
| 새 agent_type 추가 시 `TASK_QUEUE_MAP`에 등록 | 큐 누락 시 작업 적재 불가          |
| `LocalQueue`는 운영 환경 사용 금지            | 프로세스 재시작 시 메시지 초기화됨 |
| SQS 전환 시 `QueueBackend` 서브클래스만 교체  | 에이전트/워커 코드 무변경 원칙     |
| 큐 작업마다 `QueueLogger` 호출 필수           | 이력 없으면 DLQ 판단/재처리 불가   |

---

## 10. 구현 순서

```
1. backend.py     — QueueBackend / LocalQueue / SQSQueue
2. log.py         — QueueLogger + queue_log 테이블 생성
3. __init__.py    — get_queue() / TASK_QUEUE_MAP
4. task_worker.py — TaskWorker
5. ingest_worker.py / store_raw.py — IngestWorker / RawStore
6. 에이전트 수정   — run_site() → enqueue_tasks() 패턴으로 전환
```
