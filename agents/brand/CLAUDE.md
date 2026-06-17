# Brand Agent — 설계 가이드

> 이 파일은 `agents/brand/` 하위 작업 시 AI가 반드시 읽어야 하는 설계 문서입니다.

---

## 1. 목표 아키텍처

브랜드 공식 홈페이지에서 상품 가격을 수집하는 파이프라인.
수집 주기가 돌면 Brand Agent가 들어온 상품 데이터를 확인하고, Discovery Agent가 해당 상품의 브랜드 공홈 상세 페이지 URL을 매핑하여 반환하면, 큐 기반으로 크롤링 → 결과 저장까지 이어지는 구조.

---

## 2. 전체 파이프라인

두 가지 운영 모드가 존재한다. 사이트 등록([1])과 후반부 저장([6]~[10])은 공통이며, 상품 URL 확보 방식([2]~[4])만 다르다.

```
[1] UI — 사이트 등록 (공통)
        브랜드명, 브랜드 공홈 URL, 수집 주기, 수집 항목, 상품 검색 URL 형식

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Mode A — 자동 배치 (자사 시스템 상품 데이터 기반)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[A-2] 자사 시스템 — 상품 데이터 유입
        랭킹 기준, 카테고리 기준 등 N건의 상품 데이터 (상품코드, Ref No, 상품명, 이미지 등)

[A-3] Discovery Agent
        ├─ 매핑 확인: 입력 상품 데이터에 대한 상세 페이지 URL이 DB에 존재?
        │       └─ YES → 매핑된 상세 페이지 URL 반환
        │       └─ NO  → 상품 데이터(브랜드, 상품명, 상품코드, Ref No, 이미지 등)를
        │                이용해 브랜드 공홈에서 해당 상품의 상세 페이지 탐색
        │                → 상세 페이지 URL 매핑 DB에 저장
        │                → 매핑된 URL 반환
        └─ 반환값: 브랜드 공홈 상품 상세 페이지 URL

[A-4] Queue — 상품 상세 페이지 URL 적재

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Mode B — 수동 직접 관리 (사용자 URL 직접 입력)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[B-2] UI — 상품 상세 URL 직접 입력
        사용자가 브랜드 공홈 상품 상세 페이지 URL을 직접 입력 (단건 / 다건)
        Discovery Agent 없이 입력된 URL을 그대로 사용

[B-3] URL 검증 (선택)
        입력된 URL의 유효성 확인 (Playwright Stealth 기반 — urllib 단순 HTTP 사용 금지)

[B-4] Queue — 검증된 URL 적재

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  이후 공통
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[5] Crawling Agents — 큐에서 읽어 크롤링 (공통)
        ├─ 사이트별 에이전트가 각각 존재 (agents/brand/{brand}/engine.py)
        ├─ 에이전트를 여러 개 병렬로 띄울 수 있도록 설계
        └─ 봇 차단 우회 정책 적용 (적응형 백오프, stealth 브라우저 등)

[6] AWS SQS — 크롤링 결과 적재
        크롤링 속도와 저장 속도를 분리하는 버퍼

[7] Ingest Worker — SQS에서 읽어 Medallion 레이어에 적재/변환

[8–10] Medallion Architecture
        Raw    → 수집된 원본 데이터 그대로 적재
        Bronze → 기본 정제 (공백 제거, 타입 변환 등)
        Silver → 값 매핑 (브랜드코드, 통화 정규화 등)
        Gold   → 미정
```

---

## 3. 현재 구현 상태

| 단계                               | 상태                           | 위치                                                    |
| ---------------------------------- | ------------------------------ | ------------------------------------------------------- |
| [1] 사이트 등록 UI                 | 구현됨                         | `web/frontend/src/pages/SiteSettings.jsx` — BrandConfig |
| [A-2] 자사 시스템 상품 데이터 유입 | 미구현 (연동 미정)             |                                                         |
| [A-3] Discovery Agent              | 미구현 (설계 중)               | `agents/brand/discovery/` (예정)                        |
| [A-4] 자동 배치 Queue              | 미구현                         |                                                         |
| [B-2] 수동 URL 직접 입력 UI        | 부분 구현 (임시)               | `SiteSettings.jsx` — BrandConfig 내 textarea            |
| [B-3] URL 검증                     | 부분 구현 (urllib — 개선 필요) | `POST /api/sites/{id}/check-url`                        |
| [B-4] 수동 Queue 적재              | 미구현                         |                                                         |
| [5] Crawling Agents                | 부분 구현                      | `agents/brand/{brand}/engine.py`                        |
| [6] AWS SQS 연동                   | 미구현                         |                                                         |
| [7] Ingest Worker                  | 미구현                         |                                                         |
| [8–10] Medallion                   | 미구현                         |                                                         |

---

## 4. 현재 파일 구조

```
agents/brand/
├── CLAUDE.md           ← 이 파일
├── base.py             ← BrandAgent 공통 베이스 (run_site, fetch_product 등)
├── dispatcher.py       ← AGENT_REGISTRY 진입점 (brand_type으로 위임)
├── __init__.py
├── longchamp/engine.py ← LongchampAgent (fetch_by_sku 구현됨)
├── cartier/engine.py   ← CartierAgent
├── chanel/engine.py    ← ChanelAgent
├── toryburch/engine.py ← ToryBurchAgent
├── rogervivier/engine.py
├── iwc/engine.py
├── jlc/engine.py
└── louisvuitton/engine.py
```

---

## 5. Discovery Agent 설계 방향

- **역할**: 상품 데이터 → 브랜드 공홈 상세 페이지 URL 매핑
- **트리거**: Brand Agent 수집 주기 실행 시, 처리할 각 상품에 대해 호출
- **매핑 DB**: `brand_url_mapping` 테이블 (예정)
  - `(brand_type, product_code, ref_no, product_name, product_url, mapped_at)`
- **실행 흐름**:
  1. 입력 상품 데이터(브랜드, 상품명, 상품코드, Ref No, 이미지 등)로 매핑 테이블 조회
  2. 매핑된 `product_url` 존재 → 바로 반환
  3. 매핑 없음 → 브랜드 공홈에서 상품 탐색하여 상세 페이지 URL 확보
     → `brand_url_mapping`에 저장
     → URL 반환
- **탐색 방법**: 브랜드별 검색 페이지 또는 `search_url_template` 활용 (규칙 기반)
- **위치**: `agents/brand/discovery/` (예정)

---

## 6. 브랜드 에이전트 개발 규칙

### 6.1 새 브랜드 추가 시 체크리스트

```
1. agents/brand/{brand}/engine.py 생성
   - BrandAgent 상속
   - agent_type 프로퍼티 구현
   - fetch_by_sku(sku) 구현  ← 검색 → URL → 가격 수집
   - _sku_from_url(url) 구현 (선택)
   - _DOM_PRICE_JS 오버라이드 (선택)

2. dispatcher.py 의 _BRAND_MAP 에 등록

3. UI에서 brand_type 선택 옵션 추가 (필요 시)

4. CHANGELOG.md 작성 (agents/brand/{brand}/CHANGELOG.md)
```

### 6.2 각 브랜드 에이전트가 구현할 것 vs 공통

| 항목                                            | 위치                |
| ----------------------------------------------- | ------------------- |
| `fetch_by_sku(sku)` — 검색 → 상품 URL 탐색      | 브랜드별 구현       |
| `_sku_from_url(url)` — URL에서 SKU 추출         | 브랜드별 구현       |
| `_DOM_PRICE_JS` — DOM 가격 셀렉터               | 브랜드별 오버라이드 |
| `run_site(site_id)` — 키워드 루프 + 결과 저장   | base.py 공통        |
| `fetch_product(url)` — JSON-LD → API → DOM 수집 | base.py 공통        |
| `_search_api_for_price()` — 네트워크 캡처 분석  | base.py 공통        |

---

## 7. Queue 아키텍처

> 이 섹션은 Brand Agent만이 아니라 **모든 에이전트(product, news, cafe, brand 등)의 공통 큐 설계**다.
> Brand Agent 관련 세부 사항은 7.6절 참고.

---

### 7.1 전체 구조 — 두 개의 큐

에이전트 실행 전·후로 독립된 큐가 하나씩 존재한다.

```
[스케줄러 / run_site()]
        │ put(TaskMessage)
        ▼
┌─────────────────┐
│   Task Queue    │  ← 에이전트가 처리할 작업 대기열 (URL / SKU / 키워드 등)
└────────┬────────┘
         │ get(TaskMessage)
         ▼
   Task Worker        ← agent_type 보고 해당 에이전트 실행
   (각 에이전트)
         │ put(IngestMessage)
         ▼
┌─────────────────┐
│  Ingest Queue   │  ← 크롤링 결과 대기열 (AWS SQS)
└────────┬────────┘
         │ get(IngestMessage)
         ▼
  Ingest Worker       ← Medallion Raw 레이어에 적재
         │
         ▼
  Raw → Bronze → Silver
```

| 구간 | 현재 (로컬) | 운영 (SQS) |
| ---- | ----------- | ---------- |
| Task Queue | `LocalQueue` (Python `queue.Queue` 기반) | AWS SQS (agent_type별 큐) |
| Ingest Queue | `LocalQueue` (개발 중) | AWS SQS (`ingest-queue`) |
| DLQ | `LocalQueue` | AWS SQS DLQ |

**기타 방침**
- Redis 미사용
- 로컬 환경: SQLite 계속 사용
- SQS 전환 시 `QueueBackend` 서브클래스만 교체 — 에이전트 코드 무변경

---

### 7.2 Queue 추상화 레이어 (`core/queue.py`)

모든 큐는 `QueueBackend` 인터페이스를 통해 동작한다. 로컬/SQS 구현체를 인터페이스로 분리하여 에이전트 코드가 구현체에 의존하지 않도록 한다.

```python
class QueueBackend:
    def put(self, message: dict) -> str: ...        # message_id 반환
    def get(self) -> tuple[str, dict] | None: ...   # (receipt_handle, message) 반환, 없으면 None
    def ack(self, handle: str): ...                 # 처리 완료 확인 (큐에서 삭제)
    def nack(self, handle: str, delay_sec=0): ...   # 처리 실패 (재처리 예약)

class LocalQueue(QueueBackend):
    """개발/테스트용. Python queue.Queue 기반. 프로세스 재시작 시 초기화됨."""

class SQSQueue(QueueBackend):
    """운영용. boto3 기반. 큐 이름으로 초기화."""
    def __init__(self, queue_name: str): ...
```

큐 인스턴스는 `get_queue(name)` 팩토리 함수로 가져온다.

```python
from core.queue import get_queue

task_q   = get_queue("task_brand_cartier")   # Task Queue (cartier 전용)
ingest_q = get_queue("ingest")               # Ingest Queue
dlq      = get_queue("dlq_ingest")           # Ingest DLQ
```

---

### 7.3 Task Queue — TaskMessage 스키마

Task Queue에 적재하는 메시지. **모든 에이전트가 동일한 포맷을 사용**하고, `payload_type`으로 내용물 종류를 식별한다.

```python
TaskMessage = {
    "task_id":      str,    # UUID4 — 중복 방지 / 이력 추적
    "agent_type":   str,    # "product" | "news" | "cafe" | "brand" | "banner" | ...
    "site_id":      int,    # crawling_sites.id
    "payload_type": str,    # "url" | "sku" | "keyword" | "product_code" | "text"
    "payload":      str,    # 실제 처리 값 (에이전트가 해석)
    "metadata":     dict,   # 에이전트별 부가 정보 (자유 형식)
    "priority":     int,    # 0이 가장 높음 (낮을수록 먼저 처리)
    "retry_count":  int,    # 재시도 횟수 (DLQ 이동 여부 판단에 사용)
    "created_at":   str,    # ISO8601 UTC
}
```

에이전트별 `payload_type` / `payload` / `metadata` 사용 예:

| agent_type | payload_type | payload 예시 | metadata 예시 |
| ---------- | ------------ | ------------ | ------------- |
| brand (cartier) | `url` | `https://cartier.com/ring/123` | `{"brand_type": "cartier"}` |
| brand (chanel) | `sku` | `P73001` | `{"brand_type": "chanel", "search_url_template": "https://chanel.com/search?q={sku}"}` |
| product | `url` | `https://lotte-df.com/p/456` | `{"category": "시계"}` |
| news | `keyword` | `"샤넬 신상품"` | `{"date_from": "2026-06-01"}` |
| cafe | `keyword` | `"롯데면세 후기"` | `{"cafe_id": "29072709"}` |
| directory | `url` | `https://brand.com/brands/` | `{}` |

---

### 7.4 Ingest Queue — IngestMessage 스키마

크롤링 결과를 Medallion Raw 레이어로 전달하는 메시지.

```python
IngestMessage = {
    "ingest_id":    str,    # UUID4
    "task_id":      str,    # 원본 TaskMessage의 task_id (추적용)
    "agent_type":   str,
    "site_id":      int,
    "crawled_at":   str,    # ISO8601 UTC
    "payload_type": str,    # 원본 TaskMessage의 payload_type
    "source_url":   str,    # 실제 수집한 페이지 URL (fetch_product가 접속한 URL)
    "data":         dict,   # 에이전트가 수집한 결과 (자유 형식 — 에이전트마다 다름)
    "status":       str,    # "success" | "failed" | "blocked"
    "error_msg":    str,    # 실패 시 오류 메시지 (성공 시 "")
}
```

---

### 7.5 DLQ (Dead Letter Queue)

`retry_count`가 임계값(기본 `MAX_RETRY = 3`)을 초과하면 DLQ로 이동한다.

```
Task Queue 처리 실패 → retry_count++ → nack(delay_sec=60)
                           ↓ retry_count >= MAX_RETRY
                       DLQ(task) 이동 → queue_log(status="dlq")

Ingest Queue 처리 실패 → 동일 패턴 → DLQ(ingest) 이동
```

- DLQ 모니터링: `queue_log` 테이블에서 `status='dlq'` 건수 조회
- 수동 재처리: `scripts/replay_dlq.py` 스크립트로 DLQ → 원본 큐 재적재

---

### 7.6 Task Queue 분리 방식

Task Queue를 얼마나 잘게 나눌지에 따라 세 가지 방식이 있다. 격리 수준과 관리 복잡도가 트레이드오프다.

---

**방식 1 — 단일 큐 (가장 단순)**

```
task 큐: [product site=1 url, brand cartier url, news site=3 kw, ...]
                    ↓
              TaskWorker 1개
              agent_type + site_id 보고 처리
```

- 큐 1개, 관리 제일 단순
- 느린 에이전트(예: brand)가 모든 다른 에이전트 작업까지 막음
- 에이전트 타입 간 격리 없음

---

**방식 2 — 에이전트별 큐 (권장)**

```
task_product 큐: [site=1 url, site=2 url, ...]  → ProductWorker
task_brand   큐: [cartier url, chanel url, ...]  → BrandWorker → BrandDispatcher → CartierAgent / ChanelAgent
task_news    큐: [site=3 kw, ...]               → NewsWorker
...
```

- 큐 수 = agent_type 수(약 7~8개) → 관리 부담 낮음
- 에이전트 타입 간 격리 보장 (brand가 느려도 product/news 영향 없음)
- 같은 에이전트 타입 내 사이트 간 지연은 여전히 발생 가능 → 워커 수로 완화
- Brand Agent는 메시지 내 `metadata.brand_type`으로 BrandDispatcher가 CartierAgent 등으로 라우팅 (기존 구조 그대로 연결)

---

**방식 3 — 사이트별 큐 (가장 강한 격리)**

```
task_brand_cartier 큐: [url, url, ...]  → CartierAgent 전용 워커
task_brand_chanel  큐: [url, url, ...]  → ChanelAgent 전용 워커
task_product_1     큐: [url, url, ...]  → 롯데면세점 전용 워커
...
```

- 사이트 간 완벽한 격리 — 한 사이트가 느려도 다른 사이트 무관
- 큐 수 = 사이트 수 → SQS 큐 관리 비용 증가, 새 사이트 추가 시 큐도 생성 필요

---

> **현재 결정**: 방식 2 (에이전트별 큐) 채택.
> 관리 단순성과 에이전트 타입 간 격리를 동시에 확보하고,
> 기존 BrandDispatcher 구조와 자연스럽게 연결됨.

---

### 7.7 큐 이력 로깅 (`core/queue_log.py`)

큐 메시지의 상태 변화를 SQLite `queue_log` 테이블에 기록한다. 큐 작업 시 반드시 로깅해야 한다.

```sql
CREATE TABLE IF NOT EXISTS queue_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_name   TEXT    NOT NULL,   -- 'task_brand_cartier' | 'ingest' | 'dlq_ingest' 등
    message_id   TEXT    NOT NULL,   -- task_id 또는 ingest_id
    agent_type   TEXT,
    site_id      INTEGER,
    status       TEXT    NOT NULL,   -- enqueued | dequeued | acked | failed | dlq
    retry_count  INTEGER DEFAULT 0,
    error_msg    TEXT,
    created_at   TEXT    NOT NULL,   -- ISO8601 UTC
    updated_at   TEXT    NOT NULL    -- ISO8601 UTC
);
```

상태 전이:

```
put()  → status = "enqueued"
get()  → status = "dequeued"
ack()  → status = "acked"       (정상 처리 완료)
nack() → status = "failed"      (retry_count < MAX_RETRY — 재처리 예약)
nack() → status = "dlq"         (retry_count >= MAX_RETRY — DLQ 이동)
```

---

### 7.8 파일 위치

```
core/
├── queue.py              ← QueueBackend / LocalQueue / SQSQueue / get_queue() / TASK_QUEUE_MAP
├── queue_log.py          ← QueueLogger (queue_log 테이블 연동)
└── ingest/
    ├── task_worker.py    ← TaskWorker: Task Queue → agent 실행 → Ingest Queue push
    ├── ingest_worker.py  ← IngestWorker: Ingest Queue → Medallion Raw 적재
    └── store_raw.py      ← RawStore: brand_price_raw 등 Raw 레이어 저장 (SQLite → S3 교체 가능)
scripts/
└── replay_dlq.py         ← DLQ 메시지 수동 재처리 (DLQ → 원본 큐)
```

---

### 7.9 에이전트에서 큐 사용 패턴

**Task Queue에 작업 적재 (스케줄러 / `run_site()` 진입 시)**

```python
from uuid import uuid4
from datetime import datetime, timezone
from core.queue import get_queue

def enqueue_tasks(site_id: int, agent_type: str, items: list[dict]):
    """items: [{"payload_type": "url", "payload": "https://...", "metadata": {...}}, ...]"""
    q = get_queue(f"task_{agent_type}")
    for item in items:
        q.put({
            "task_id":      str(uuid4()),
            "agent_type":   agent_type,
            "site_id":      site_id,
            "payload_type": item["payload_type"],
            "payload":      item["payload"],
            "metadata":     item.get("metadata", {}),
            "priority":     0,
            "retry_count":  0,
            "created_at":   datetime.now(timezone.utc).isoformat(),
        })
```

**크롤링 결과 → Ingest Queue push (에이전트 내부)**

```python
from core.queue import get_queue

ingest_q = get_queue("ingest")
ingest_q.put({
    "ingest_id":    str(uuid4()),
    "task_id":      task["task_id"],
    "agent_type":   task["agent_type"],
    "site_id":      task["site_id"],
    "crawled_at":   datetime.now(timezone.utc).isoformat(),
    "payload_type": task["payload_type"],
    "source_url":   result.get("url", ""),
    "data":         result,
    "status":       "success" if not result.get("error") else "failed",
    "error_msg":    result.get("error", ""),
})
```

---

### 7.10 Queue 절대 규칙

| 규칙 | 이유 |
| ---- | ---- |
| **`ack()`는 저장 완료 후에만 호출** | 저장 실패 시 메시지 유실 방지 |
| **새 agent_type 추가 시 `TASK_QUEUE_MAP`에 등록** | 큐 누락 시 작업 적재 불가 |
| **새 브랜드 추가 시 `task_brand_{brand}` 큐 등록** | 브랜드별 큐 분리 원칙 유지 |
| **`LocalQueue`는 운영 환경 사용 금지** | 프로세스 재시작 시 메시지 초기화됨 |
| **메시지 스키마 변경 시 `queue_log` 테이블도 동시 변경** | 이력 추적 필드 누락 방지 |
| **SQS 전환 시 `QueueBackend` 서브클래스만 교체** | 에이전트 코드 무변경 원칙 |

---

## 8. 알려진 이슈

| 항목                           | 내용                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fetch_by_sku` 미구현 브랜드   | rogervivier, iwc, jlc, louisvuitton, chanel                                                                                                                                                                                                                                                                                                                                                              |
| 원가/할인율/할인가 분리 수집   | 미구현 — 현재 `price` 단일 필드만 반환                                                                                                                                                                                                                                                                                                                                                                   |
| 프록시 비활성화                | 한국 브랜드 공홈 SSL 충돌로 전면 비활성화                                                                                                                                                                                                                                                                                                                                                                |
| 병렬 크롤링                    | 미구현 — 현재 순차 실행                                                                                                                                                                                                                                                                                                                                                                                  |
| 상품 상세 URL 검증             | `POST /api/sites/{id}/check-url` 에서 `urllib.request`(단순 HTTP)로 체크 중 — 럭셔리 브랜드 사이트는 Cloudflare 등 봇 차단으로 유효한 URL도 403/차단 응답이 올 수 있음. Mode B URL 검증 구현 시 Playwright Stealth 브라우저로 전환 필요                                                                                                                                                                  |
| Mode B UI (임시)               | 현재 BrandConfig 내 textarea는 임시 구현. Mode B 정식 구현 시 단건 입력 / 다건 일괄 입력(줄바꿈 또는 CSV) 모두 지원해야 함                                                                                                                                                                                                                                                                               |
| Mode A 자사 연동               | 자사 시스템과의 연동 방식(API 푸시 vs 배치 풀) 미정. Discovery Agent 구현 전 연동 방식 확정 필요                                                                                                                                                                                                                                                                                                         |
| 상품 검색 URL 형식 위치 적정성 | 현재 [1] 사이트 등록 시 `상품 검색 URL 형식`을 입력받고 있으나, 이는 Discovery Agent(Mode A 전용)가 브랜드 공홈에서 상품을 탐색할 때만 사용하는 값임. Mode B는 이 필드가 불필요하고, Mode A도 Discovery Agent 설계 확정 후 어디서 관리할지 재검토 필요. 사이트 등록(공통)에 포함시키는 것이 적절한지, Mode A 전용 설정으로 분리하는 것이 맞는지 미결 상태                                                |
| 크롤링 매트릭스 설계 필요      | 브랜드 × 상품 × 수집 주기 조합을 명시하는 크롤링 매트릭스 개념이 미정. 매트릭스는 수집 주기 도래 시 "오늘 크롤링할 URL 목록"을 큐에 적재하는 원천 데이터가 됨. Mode A에서는 자사 시스템 상품 데이터가 이 역할을 하고, Mode B에서는 사용자가 직접 입력한 URL 목록이 이 역할을 함. 매트릭스 스키마(`site_id`, `brand_type`, `product_url`, `schedule`) 및 저장 위치, 수집 주기와의 연동 방식을 설계해야 함 |
