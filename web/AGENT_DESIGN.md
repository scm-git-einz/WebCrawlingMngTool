# Agent 설계 문서

## 1. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        실행 진입점                                │
│                                                                 │
│   CLI (main.py)              Web UI (FastAPI /api/crawl/run)    │
│   python main.py run --id 1  POST {"site_ids": [1,2,3]}        │
│         │                           │                           │
│         └─────────┬─────────────────┘                           │
│                   ▼                                             │
│          agents/__init__.py                                     │
│          AGENT_REGISTRY → get_agent(agent_type)                 │
│                   │                                             │
│   ┌───────┬───────┼───────┬──────────┬──────────┐               │
│   ▼       ▼       ▼       ▼          ▼          ▼               │
│ Product  News   Cafe   Promotion  Banner   Directory            │
│ Agent    Agent  Agent  Agent      Agent    Agent                │
│ (v2)                              (v2)     (v2)                │
│   │       │       │       │          │          │               │
│   └───────┴───────┼───────┴──────────┴──────────┘               │
│                   ▼                                             │
│             BaseAgent (추상 클래스)                               │
│             ├── CrawlDB (SQLite)                                │
│             ├── BrowserManager (Playwright Stealth)              │
│             ├── ProxyManager (무료 프록시 IP 로테이션)              │
│             ├── 적응형 백오프 (429/503 대응)                       │
│             ├── 소프트 차단 감지 (HTTP 200 빈 페이지/이미지만)       │
│             └── 인간형 행동 시뮬레이션                              │
└─────────────────────────────────────────────────────────────────┘
```

### 1.1 에이전트 레지스트리

```python
# agents/__init__.py
AGENT_REGISTRY = {
    "product":   ProductAgent,     # v2 — 상품/랭킹 수집
    "news":      NewsAgent,        # 뉴스 기사 수집
    "cafe":      CafeAgent,        # 카페 인기글 수집
    "promotion": PromotionAgent,   # 이벤트/프로모션 수집
    "banner":    BannerAgent,      # v2 — 배너/비주얼 캡처
    "directory": DirectoryAgent,   # v2 — 브랜드/이벤트 목록
    "order":     OrderAgent,       # 주문서 결제정보 수집
}

def get_agent(agent_type: str, db=None):
    """agent_type 문자열로 에이전트 인스턴스를 생성"""
    cls = AGENT_REGISTRY[agent_type]
    return cls(db=db)
```

### 1.2 실행 흐름

```
[CLI 실행]
  main.py run --id 1
    → db.get_site(1)
    → site['agent_type'] = 'product'
    → agent = get_agent('product', db)
    → agent.run_site(1)

[Web UI 실행]
  POST /api/crawl/run {"site_ids": [1,2,3]}
    → 각 site_id 별로 subprocess.Popen 으로 별도 프로세스 실행
    → subprocess: python -u main.py run --id {N}
    → stdout → logs/crawl_{id}_{timestamp}.log 파일 기록
    → env: PYTHONIOENCODING=utf-8 (Windows cp949 대응)
    → PID 기반으로 실행 상태 추적

[Web UI 중지]
  POST /api/crawl/stop {"site_id": 1}
    → Windows: taskkill /F /T /PID (자식 프로세스 포함)
    → Linux: os.kill(pid, signal.SIGTERM)
    → 로그에 중지 메시지 기록
```

---

## 2. 설계 원칙

| 원칙 | 설명 | 적용 |
|------|------|------|
| **LLM 불필요** | 모든 분석/추출은 규칙 기반 (RuleAnalyzer) | 플랫폼 감지, 데이터 추출, 키 이름 매핑 |
| **하드코딩 금지** | 사이트별 로직 없음, 플랫폼 감지 + 템플릿으로 동적 대응 | 추출 전략 + 필드 매핑 패턴 |
| **봇 차단 대응** | Stealth 브라우저 + 인간형 행동 + 적응형 백오프 + 프록시 로테이션 + 소프트 차단 감지 | ANTI_BOT.md 참조 |
| **이중화** | OCR (Document Parse → Tesseract), 추출 (API → DOM fallback) | 자동 폴백 |
| **쿠키 영속화** | 도메인별 쿠키 저장으로 로그인 세션 유지 | data/cookies/ 디렉토리 |
| **UI-Agent 분리** | UI는 사용자 친화적 필드, Agent는 내부 필드 | `_normalize_config()` 변환 레이어 |

---

## 3. Agent 실행 조건

### 3.1 실행 트리거

| 트리거 | 방식 | 코드 |
|--------|------|------|
| CLI 개별 실행 | `python main.py run --id 1` | `agent.run_site(site_id)` |
| CLI 프록시 실행 | `python main.py run --id 1 --proxy` | `agent.enable_proxy()` → `run_site()` |
| CLI 전체 실행 | `python main.py run` | `agent.run_all()` → 활성 사이트 순회 |
| CLI 에이전트별 | `python main.py run --agent product` | 해당 타입만 `run_all()` |
| Web UI 실행 | `POST /api/crawl/run {"site_ids": [1,2]}` | `subprocess.Popen(main.py run --id N)` |
| Web UI 프록시 | `POST /api/crawl/run {"site_ids": [1], "use_proxy": true}` | `subprocess.Popen(... --proxy)` |
| Web UI 일괄 실행 | 카테고리별/주기별 버튼 | 여러 site_id를 각각 별도 프로세스로 실행 |

### 3.2 실행 전제 조건

```
1. crawl_sites.is_active = 1 (활성 상태)
2. crawl_sites.agent_type 에 맞는 Agent 클래스가 AGENT_REGISTRY에 등록
3. .venv 가상환경에 playwright, playwright_stealth 설치
4. Chromium 브라우저 설치 (playwright install chromium)
5. (선택) OCR: Tesseract 설치 또는 Upstage API Key
```

### 3.3 에이전트 타입 결정 규칙

```
crawl_sites 테이블의 agent_type 컬럼으로 결정
  └── Web UI: 카테고리에 따라 자동 매핑
        뉴스 카테고리       → news
        카페 카테고리       → cafe
        경쟁사이벤트 카테고리 → promotion
        나머지              → product
```

---

## 4. BaseAgent (core/base_agent.py)

모든 Agent의 부모 클래스. 공통 인프라를 제공한다.

### 4.1 제공 기능

| 기능 | 메서드 | 설명 |
|------|--------|------|
| DB 연결 | `self.db` (CrawlDB) | SQLite DB CRUD |
| 브라우저 | `self.browser_mgr` (BrowserManager) | Playwright Stealth 브라우저 |
| 페이지 생성 | `_create_page()` | 프록시 포함 브라우저 페이지 생성 헬퍼 |
| config 파싱 | `get_crawl_config(site)` | crawl_config JSON → dict |
| 안전 이동 | `_safe_goto(url)` | 429/503 시 적응형 백오프 + 프록시 교체 + 소프트 차단 감지 |
| 차단 감지 | `_is_blocked(resp)` | HTTP 상태(429/403/503) + 소프트 차단(빈 페이지/이미지만) 통합 감지 |
| HTTP 차단 | `_is_http_blocked(resp)` | HTTP 상태 코드만 체크 (static, _safe_goto 내부용) |
| 소프트 차단 | `_is_soft_blocked()` | DOM 분석으로 빈 페이지/이미지만 페이지 감지 |
| 프록시 활성화 | `enable_proxy()` | 무료 프록시 IP 로테이션 활성화 |
| 프록시 교체 | `_rotate_proxy()` | 차단 시 프록시 교체 + 컨텍스트 재생성 |
| 인간형 딜레이 | `_delay()`, `_human_delay()` | 정규분포 기반 가변 딜레이 (평균 3.5초) |
| 인간형 스크롤 | `_human_scroll()` | 가변 스크롤 + 중간 정지 + 역스크롤(20%) |
| 인간형 체류 | `_human_dwell()` | 페이지 로드 후 체류 + 마우스 이동 |
| 쿠키 도메인 | `_get_cookie_domain(url)` | URL에서 쿠키 영속화 도메인 추출 |

### 4.2 적응형 백오프 + 프록시 로테이션 (봇 차단 대응)

```
429/503 응답 시 (프록시 모드):
  1차 대응: 연속 2회 차단 → 프록시 IP 교체 (컨텍스트 재생성)
  2차 대응: 프록시 교체 불가 시 → 적응형 백오프 (120s~600s)

429/503 응답 시 (일반 모드):
  기본 대기: 120초
  지수 백오프: 120s → 240s → 480s (최대 600초)
  랜덤 지터: ±30%
  최대 재시도: 5회
  도메인별 이력 추적 → 연속 차단 시 대기시간 자동 증가

403 (IP 차단) 응답 시:
  프록시 모드: 즉시 프록시 교체
  일반 모드: 해당 페이지 건너뜀

HTTP 200 소프트 차단 (이미지만/빈 페이지) 시:
  프록시 모드: 즉시 프록시 교체 후 재접속
  일반 모드: 그대로 반환 (에이전트가 판단)

선제적 대기:
  최근 5분 내 429 이력 → 30~120초 쿨다운 후 요청
```

> 봇 차단 대응 기술 상세: `ANTI_BOT.md` 참조

### 4.3 로그인 계정 로테이션

```
로그인이 필요한 사이트:
  1. _get_next_credential(site_id)
     → site_credentials에서 활성 계정 조회
     → last_used_at ASC NULLS FIRST 정렬 (라운드로빈)
     → 선택된 계정의 last_used_at 갱신

  2. _do_login(page, credential, login_config)
     → login_config에 셀렉터 지정 가능:
        login_url, id_selector, pwd_selector, submit_selector, success_indicator
     → 미지정 시 범용 폼 탐지:
        input[type=password] 기준으로 ID 필드/제출 버튼 역추적
     → 인간형 입력 지연 (300~700ms)

  소프트 차단 대응 (프록시 모드):
     로그인 페이지 접속 후 소프트 차단 감지 시:
       → _is_soft_blocked(): 이미지만/빈 페이지 검사
       → 또는 로그인 폼(input[type=password]) 미발견
       → 프록시 교체 후 로그인 페이지 재접속 (최대 3회)

     판정 흐름:
       login_url 접속 → _is_soft_blocked()?
         Yes → 프록시 교체 → login_url 재접속 (최대 3회)
         No  → 폼 탐지 → input[type=password] 발견?
           Yes → 로그인 진행
           No  → 소프트 차단 추정 → 프록시 교체 후 재시도 (최대 3회)

사용 패턴 (에이전트 run_site 내부):
  credential = self._get_next_credential(site_id)
  if credential:
      login_cfg = crawl_cfg.get("login_config", {})
      self._do_login(self.page, credential, login_cfg)
```

### 4.4 추상 메서드 (서브클래스 필수 구현)

```python
@property
def agent_type(self) -> str:     # 에이전트 식별자 ("product", "news", "cafe")

def run_site(self, site_id: int) # 단일 사이트 수집 실행
```

### 4.4 _normalize_config() 패턴

모든 에이전트가 동일한 패턴으로 UI config → Agent 내부 config 변환을 수행한다.

```python
# 모든 에이전트의 run_site() 내부:
raw_cfg = self.get_crawl_config(site)     # DB에서 JSON 로드
crawl_cfg = self._normalize_config(raw_cfg) # UI → Agent 필드 변환
```

**변환 목적**:
- UI는 사용자 친화적 필드명 사용 (예: `product_limit_type='all'`)
- Agent는 내부 필드명 사용 (예: `max_detail_pages=0`)
- `_normalize_config()`이 중간에서 매핑 + 기본값 적용 + 타입 보정

---

## 5. ProductAgent v1 (삭제됨)

> **⚠️ 이 섹션은 아카이브입니다.**
> Phase 14에서 기존 ProductAgent는 삭제되었으며, 3개의 새로운 Collector 에이전트로 대체됩니다.
> 새 설계는 **섹션 15. v2 에이전트 아키텍처**를 참조하세요.

---

## 5-legacy. ProductAgent v1 수집 파이프라인 (참고용)

<details>
<summary>접기/펼치기 — 기존 ProductAgent 설계 (삭제됨)</summary>

### 수집 파이프라인

```
run_site(site_id)
  ├── _normalize_config()
  ├── crawl_mode 판별 → single / domain
  │
  [단일 매장] _ensure_platform → _crawl_store → _crawl_products → _crawl_details → _save_json
  [도메인 전체] 도메인 홈 → _discover_stores → 매장별 반복 수집 → 병합 저장
```

### _normalize_config() 변환

```
crawl_mode = 'single'/'domain'
store_limit_type = 'all' → max_stores = 0
product_limit_type = 'all' → collect_details=True, max_detail_pages=0
```

### 삭제 사유

1. **실제 수집 실패율 높음**: 플랫폼 자동 감지(RuleAnalyzer) 의존도가 너무 높아 사이트별 수집 성공률이 낮음
2. **코드 복잡도**: 플랫폼 감지 → 전략 선택 → 추출 실행의 3단계 추상화가 디버깅을 어렵게 만듦
3. **비즈니스 요구사항 불일치**: 트렌드/경쟁사/브랜드/배너 등 카테고리별로 완전히 다른 수집 로직이 필요한데, 단일 에이전트로 모든 것을 처리하려 한 설계적 한계

### 플랫폼 감지 + 추출 전략 (유지)

기존 인프라(RuleAnalyzer, strategies/, NetworkInterceptor)는 삭제하지 않음.
새 Collector 에이전트에서 필요 시 부분적으로 활용 가능.

| 전략 | 클래스 | 파일 | 설명 |
|------|--------|------|------|
| `state_var` | `StateVarStrategy` | `core/strategies/state_var.py` | window 전역 변수에서 JSON 추출 |
| `dom` | `DomParserStrategy` | `core/strategies/dom_parser.py` | CSS 셀렉터로 DOM 파싱 |
| `api` | `ApiCallerStrategy` | `core/strategies/api_caller.py` | REST API 호출 JSON 파싱 |

</details>

---

## 6. NewsAgent (agents/news/engine.py)

### 6.1 수집 파이프라인

```
run_site(site_id)
  │
  ├── _normalize_config()       기본값 적용 + 타입 보정
  ├── _resolve_keywords()       키워드 결정 (우선순위 적용)
  │
  ├── [키워드 검색 모드] ← 키워드 있음 or 네이버 검색 URL
  │     ├── 키워드별 검색 URL 접속
  │     ├── _JS_NAVER_NEWS_SEARCH_EXTRACT 실행
  │     ├── 기사 수집 (max_articles_per_keyword 제한)
  │     └── max_articles 전체 상한 적용
  │
  ├── [단일 페이지 모드] ← 키워드 없음 & 일반 URL
  │     ├── 사이트 접속
  │     ├── 기존 템플릿 또는 DOM 자동 분석
  │     └── _JS_NEWS_ARTICLE_SCAN으로 기사 링크 탐지
  │
  ├── (선택) _collect_article_bodies()
  │     각 기사 페이지 방문 → 본문 텍스트 추출
  │
  └── _save_json()              결과 저장
```

### 6.2 _normalize_config() 변환 규칙

```python
def _normalize_config(self, crawl_cfg: dict) -> dict:
    cfg = dict(crawl_cfg)

    # 기본값 적용
    cfg.setdefault("max_articles_per_keyword", 20)
    cfg.setdefault("max_articles", 100)
    cfg.setdefault("collect_body", True)

    # 타입 보정 (UI에서 문자열로 올 수 있음)
    for int_key in ("max_articles_per_keyword", "max_articles"):
        if isinstance(cfg[int_key], str):
            cfg[int_key] = int(cfg[int_key]) if cfg[int_key].isdigit() else 20

    return cfg
```

### 6.3 키워드 우선순위

```
1순위: CLI --keywords "해외여행,환율"     (override_keywords)
2순위: DB news_keywords 테이블 활성 키워드  (Web UI에서 관리)
3순위: crawl_config.search_keywords       (하위 호환)

최초 실행 시 crawl_config → DB 자동 마이그레이션 수행
```

### 6.4 crawl_config 필드

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `max_articles_per_keyword` | 20 | 키워드당 최대 기사 수 |
| `max_articles` | 100 | 전체 기사 상한 |
| `collect_body` | true | 기사 본문 수집 여부 |
| `search_keywords` | [] | 검색 키워드 (하위 호환, DB 우선) |
| `keywords` | [] | 수집 후 필터 키워드 |

---

## 7. CafeAgent (agents/cafe/engine.py)

### 7.1 수집 파이프라인

```
run_site(site_id)
  │
  ├── _normalize_config()             기본값 적용 + 빈 날짜 처리
  │
  ├── _collect_popular_list()         인기글 목록 수집
  │     ├── cafe_id 추출 (URL 파싱)
  │     ├── 인기글 iframe URL 접속
  │     ├── SPA 버튼 클릭 페이지네이션
  │     │     └── _click_page_button()
  │     ├── 날짜 필터 적용 (date_from ~ date_to)
  │     └── 종료 조건:
  │           - 새 게시글 0개
  │           - 전체가 date_from 이전
  │           - 다음 버튼 없음
  │           - max_pages 도달
  │
  ├── _collect_post_details()         게시글 상세 수집
  │     ├── 각 게시글 페이지 방문
  │     ├── _JS_CAFE_ARTICLE_EXTRACT 실행
  │     │     ├── 본문 텍스트
  │     │     ├── 가격-상품명 페어링 (텍스트 패턴)
  │     │     ├── 외부 링크 (상품 링크 분류)
  │     │     └── 이미지 URL
  │     ├── (선택) _extract_prices_from_images()
  │     │     ├── OCR: Document Parse 우선
  │     │     ├── Fallback: Tesseract
  │     │     ├── 좌표 기반 매칭 (_extract_prices_from_elements)
  │     │     └── 텍스트 기반 매칭 (_extract_prices_from_text)
  │     └── DB OCR 사용 이력 기록
  │
  └── _save_json()                    결과 저장
```

### 7.2 _normalize_config() 변환 규칙

```python
def _normalize_config(self, crawl_cfg: dict) -> dict:
    cfg = dict(crawl_cfg)

    # 기본값 적용
    cfg.setdefault("collect_body", True)
    cfg.setdefault("collect_links", True)
    cfg.setdefault("collect_images", True)
    cfg.setdefault("collect_ocr", False)
    cfg.setdefault("max_pages", 200)

    # 빈 문자열 날짜 → None
    for date_key in ("date_from", "date_to"):
        if cfg.get(date_key) == "":
            cfg[date_key] = None

    return cfg
```

### 7.3 네이버 카페 특수 처리

```
- 인기글 페이지는 iframe 내부에 있음 → iframe URL 직접 접근
- 페이지네이션이 SPA 방식 → URL 변경 불가, 버튼 클릭으로 이동
- 다음 페이지 그룹 이동 → '다음' 버튼 클릭 후 숫자 버튼 재클릭
```

### 7.4 crawl_config 필드

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `date_from` | None | 수집 시작일 (예: "2026-05-01") |
| `date_to` | None | 수집 종료일 (예: "2026-05-25") |
| `date_range_days` | - | 최근 N일 (date_from/to 자동 계산) |
| `collect_body` | true | 본문 수집 |
| `collect_links` | true | 외부 링크 수집 |
| `collect_images` | true | 이미지 URL 수집 |
| `collect_ocr` | false | 이미지 OCR 가격 추출 |
| `max_pages` | 200 | 최대 페이지 수 (무한 루프 방지) |

---

## 8. 공통 인프라

### 8.1 BrowserManager (core/browser.py)

```
Playwright Stealth Chromium 브라우저 관리

기능:
  - Stealth 모드: 자동화 탐지 방지 (playwright_stealth)
  - 한글 로케일/서울 시간대 설정
  - 커스텀 User-Agent + HTTP 헤더 (Chrome 125 위장)
  - 리소스 필터링 (font, media 차단)
  - 도메인 허용 목록 (allowed_domains)
  - 쿠키 영속화 (도메인별 JSON 파일 저장/로드)
  - 프록시 지원: context-level 프록시 설정
  - 프록시 교체: recreate_context()로 브라우저 재시작 없이 IP 교체

주요 메서드:
  - create(config, cookie_domain, headless, proxy)
      → Stealth 브라우저 시작 + 프록시 설정
  - recreate_context(proxy)
      → 기존 컨텍스트 종료 + 새 프록시로 컨텍스트 재생성
      → 쿠키 저장/로드, 리소스 필터링 재설정
  - save_cookies() / close()

브라우저 플래그:
  - --disable-blink-features=AutomationControlled
  - --no-sandbox
  - --disable-dev-shm-usage

Stealth 적용 항목:
  - navigator.languages = ["ko-KR", "ko"]
  - navigator.platform = "Win32"
  - navigator.webdriver = undefined (자동화 플래그 은닉)
  - window.chrome 객체 구조 시뮬레이션
```

### 8.5 ProxyManager (core/proxy_manager.py)

```
무료 프록시 IP 로테이션 관리

기능:
  - 8개 무료 소스에서 HTTP/SOCKS4/SOCKS5 프록시 자동 수집
  - 병렬 검증 (httpbin.org/ip 테스트, 50개 후보 중 15개 목표)
  - 캐시 파일 관리 (data/proxies/proxy_list.json, 30분 TTL)
  - 라운드로빈 / 랜덤 로테이션
  - 블랙리스트 관리 (차단된 프록시 자동 제외)
  - 모듈 레벨 싱글톤: get_proxy_manager()

주요 메서드:
  - get_next()          → 라운드로빈으로 다음 프록시 반환
  - get_random()        → 랜덤 프록시 반환
  - rotate_on_block()   → 현재 프록시 블랙리스트 + 새 프록시 반환
  - refresh()           → 프록시 목록 새로 수집 + 검증

프록시 소스:
  - ProxyScrape (HTTP, SOCKS4, SOCKS5)
  - TheSpeedX (HTTP, SOCKS5)
  - clarketm (HTTP)
  - monosans (HTTP, SOCKS5)

캐시 파일 구조:
  data/proxies/proxy_list.json
  {
    "fetched_at": 1717587600,
    "count": 15,
    "proxies": [
      {"server": "http://1.2.3.4:8080", "source": "proxyscrape_http", ...}
    ]
  }
```

### 8.2 NetworkInterceptor (core/network_interceptor.py)

```
페이지 로드 중 XHR/Fetch 요청 캡처 및 API 후보 분석

용도:
  - 상품/카테고리 관련 API 엔드포인트 자동 탐지
  - 플랫폼 자동 분석 시 네트워크 패턴 활용
  - 페이지네이션 파라미터 자동 감지

필터링:
  - 제외: analytics, tracking, ads, cdn, font, image 등 (30+ 패턴)
  - 포함: product, goods, item, catalog, shop, category 등 (12 키워드)

분석 기능:
  - _find_product_list(): JSON 응답에서 상품 배열 탐지 (재귀, 깊이 3)
  - _find_category_data(): 카테고리 배열 탐지
  - _find_store_data(): 매장 정보 탐지
  - _detect_pagination(): 페이지네이션 파라미터 탐지
  - _score_product_fields(): 상품 데이터 확률 점수화
  - _map_product_fields_deep(): 중첩 키를 표준 스키마에 자동 매핑
```

### 8.3 RuleAnalyzer (core/rule_analyzer.py)

```
LLM 없이 규칙 기반으로 사이트 구조를 분석

분석 파이프라인:
  1단계: JS 전역 변수 탐지 → 프레임워크 감지 → state_var 템플릿
  2단계: 네트워크 요청 분석 → API 엔드포인트 → api 템플릿
  3단계: DOM 반복 패턴 탐지 → dom 템플릿
  4단계: 키 이름 휴리스틱 → 표준 스키마 자동 매핑

키 이름 매핑 예시:
  channelName    → store_name
  sellingPrice   → selling_price
  productNo      → product_id
  goodsNm        → product_name
  representativeImageUrl → image_url
```

### 8.4 OCRManager (core/ocr.py)

```
이중화 OCR 구조:

  1차: Upstage Document Parse API
       - 구조 보존 (좌표 정보 포함)
       - 2D 레이아웃 매칭 가능
       - API Key 필요 (UPSTAGE_API_KEY)

  2차: Tesseract OCR (fallback)
       - 로컬 실행, 무료
       - 텍스트 기반 매칭만 가능
       - Tesseract-OCR 설치 필요

가격 추출 전략:
  - 좌표 기반: Document Parse 요소의 x/y 좌표로 같은 컬럼 매칭
  - 텍스트 기반: 가격 패턴(N,NNN원) 주변 텍스트에서 상품명 추출
    - 슬래시 구분: "상품명/가격/출처"
    - 콜론 구분: "상품명 : 가격"
    - 이전 줄 탐색: 가격 줄 위의 한글 포함 줄을 상품명으로
```

---

## 9. DB 스키마

```sql
-- 수집 대상 사이트
crawl_sites (
  id, site_name, site_url, is_active,
  platform_id,          -- 감지된 플랫폼 FK
  agent_type,           -- 'product' | 'news' | 'cafe'
  crawl_config,         -- JSON: UI 설정 + Agent 옵션
  category,             -- 카테고리 (트렌드매장, 경쟁사, 뉴스 등)
  crawl_schedule,       -- 수집 주기 ('hourly'|'daily'|'weekly'|'monthly')
  created_at, updated_at
)

-- 플랫폼 정의 (자동 감지 결과)
platforms (
  id, name, display_name,
  detection,            -- JSON: 감지 규칙 (JS 변수, meta 태그 등)
  browser,              -- JSON: 브라우저 설정 (User-Agent, 헤더 등)
  is_active, created_at
)

-- 추출 템플릿 (플랫폼별)
extraction_templates (
  id, platform_id,
  target,               -- 'store' | 'product_list' | 'product_detail' | 'category'
  strategy,             -- 'state_var' | 'dom' | 'api'
  config,               -- JSON: 전략별 추출 설정
  priority
)

-- 수집 결과
crawl_results (
  id, site_id, crawl_date, status,
  store_info,           -- JSON: 매장 정보
  products,             -- JSON: 상품/기사/게시글 리스트
  product_count, error_msg, elapsed_sec
)

-- 뉴스 키워드
news_keywords (
  id, site_id, keyword, is_active, created_at
)

-- OCR 사용 이력
ocr_usage_log (
  id, site_id, post_id, image_url,
  engine,               -- 'document-parse' | 'tesseract'
  status,               -- 'success' | 'fail' | 'rate_limit'
  text_length, price_count, elapsed_ms, error_msg,
  created_at
)

-- 사이트별 로그인 계정 (복수 계정, 로테이션 지원)
site_credentials (
  id, site_id,
  login_id,             -- 로그인 ID
  login_pwd,            -- 로그인 비밀번호
  label,                -- 계정 라벨 (예: '본계정', '테스트용')
  is_active,            -- 활성/비활성
  last_used_at,         -- 마지막 사용 시각 (로테이션 기준)
  created_at
)
```

---

## 10. 데이터 흐름

```
[사이트 등록]
  Web UI / CLI → crawl_sites 테이블에 저장

[수집 실행]
  실행 트리거 → agent_type으로 Agent 선택
    → crawl_config 로드 + _normalize_config()
    → (--proxy 시) enable_proxy() → ProxyManager 초기화
    → 브라우저 시작 (_create_page: Stealth Chromium + 프록시 + 쿠키 로드)
    → 사이트 접속 (_safe_goto: 적응형 백오프 + 프록시 교체 + 소프트 차단 감지)
    → (로그인 필요 시) _do_login() (소프트 차단 시 프록시 교체 후 재시도)
    → 플랫폼 감지 (ProductAgent만)
    → 데이터 수집 (전략별 추출)
    → 결과 저장 (DB crawl_results + JSON 파일)
    → 브라우저 종료 (쿠키 영속화)

[결과 저장 위치]
  DB: crawl_results 테이블 (products JSON)
  파일: output/{site_id}_{site_name}/
        ├── products.json         (기본 상품 목록, 상세 정보 제외)
        ├── product_details.json  (전체 상품 + description/detail_images)
        ├── crawl_result.json     (메타데이터 + 요약 통계)
        ├── articles.json         (뉴스)
        ├── posts.json            (카페)
        └── events.json           (프로모션)
  로그: logs/crawl_{site_id}_{timestamp}.log (실행 로그)
```

---

## 11. UI ↔ Agent Config 맵핑

### Product Agent

| UI 필드 | Agent 내부 필드 | 변환 |
|---------|----------------|------|
| `crawl_mode='single'` | `crawl_mode='single'` | 단일 매장 모드 (기존 동작) |
| `crawl_mode='domain'` | `crawl_mode='domain'` | 도메인 전체 모드 (매장 탐색) |
| `store_limit_type='all'` | `max_stores=0` | 전체 매장 수집 |
| `store_limit_type='n'`, `count=N` | `max_stores=N` | N개 매장 제한 |
| `product_limit_type='all'` | `collect_details=True`, `max_detail_pages=0` | 전체 상품 상세 수집 |
| `product_limit_type='n'`, `count=N` | `collect_details=True`, `max_detail_pages=N` | N건 상세 수집 |

### News Agent

| UI 필드 | Agent 필드 | 비고 |
|---------|-----------|------|
| `max_articles_per_keyword` | `max_articles_per_keyword` | 동일 (기본값 20) |
| `collect_body` | `collect_body` | 동일 (기본값 true) |
| DB `news_keywords` | Agent가 DB 직접 조회 | Web UI에서 키워드 관리 |

### Cafe Agent

| UI 필드 | Agent 필드 | 비고 |
|---------|-----------|------|
| `date_from` | `date_from` | 동일 (빈 문자열 → None) |
| `date_to` | `date_to` | 동일 (빈 문자열 → None) |
| `collect_body` | `collect_body` | 동일 (기본값 true) |
| `collect_links` | `collect_links` | 동일 (기본값 true) |
| `collect_images` | `collect_images` | 동일 (기본값 true) |
| `collect_ocr` | `collect_ocr` | 동일 (기본값 false) |

---

## 12. PromotionAgent (agents/promotion/engine.py)

### 12.1 개요

경쟁사 면세점 등의 이벤트/프로모션 정보를 수집하는 에이전트.
ProductAgent와 분리된 별도의 수집 파이프라인으로 동작한다.

**분리 사유**: 이벤트 페이지는 상품 페이지와 완전히 다른 구조:
- 상품 Agent: 매장 정보 + 상품 목록 (2단계)
- 프로모션 Agent: 이벤트 목록 → 이벤트 상세 → 이벤트 내 상품 (3단계 계층)
- 이벤트에 상품이 포함되지 않을 수 있음

### 12.2 수집 파이프라인

```
run_site(site_id)
  │
  ├── _normalize_config()             config 변환
  │
  ├── _run_event_collection()
  │     ├── 브라우저 시작 + 이벤트 페이지 접속
  │     ├── _collect_site_info()       사이트 메타 정보 수집
  │     │
  │     ├── _collect_event_list()      이벤트 목록 수집
  │     │     ├── JS DOM 분석 (범용 이벤트 카드 패턴)
  │     │     ├── 네트워크 API 인터셉트 (fallback 1)
  │     │     ├── 링크 패턴 분석 (fallback 2)
  │     │     ├── 날짜 파싱 + 상태 필터
  │     │     └── max_events 적용
  │     │
  │     ├── (선택) _collect_event_details()
  │     │     ├── 각 이벤트 상세 페이지 방문
  │     │     ├── 상세 정보 추출 (내용, 기간, 혜택, 조건)
  │     │     └── _collect_event_products()
  │     │           └── 이벤트 내 상품 추출 (있는 경우만)
  │     │
  │     └── 결과 저장 (DB + JSON)
  │
  └── _save_json()
        ├── output/{id}_{name}/store_info.json
        ├── output/{id}_{name}/events.json
        └── output/{id}_{name}/crawl_result.json
```

### 12.3 _normalize_config() 변환 규칙

```
UI 필드                           → Agent 내부 필드
────────────────────────────────────────────────────
event_limit_type = 'all'         → max_events = 0 (전체)
event_limit_type = 'n', count=N  → max_events = N
collect_details = true/false     → 이벤트 상세 페이지 방문 여부
collect_event_products = true    → 이벤트 내 상품 수집 여부
event_status_filter = 'all'      → 전체 이벤트
event_status_filter = 'active'   → 진행 중만
```

### 12.4 crawl_config 필드

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `event_limit_type` | 'all' | 수집 범위 ('all' \| 'n') |
| `event_limit_count` | 50 | n건 지정 시 이벤트 수 |
| `collect_details` | true | 이벤트 상세 페이지 방문 여부 |
| `collect_event_products` | true | 이벤트 내 상품 수집 여부 |
| `event_status_filter` | 'all' | 상태 필터 ('all' \| 'active') |

### 12.5 이벤트 데이터 구조

```json
{
  "title": "이벤트 제목",
  "event_url": "https://...",
  "image_url": "https://...",
  "date_text": "2026.05.01 ~ 2026.05.31",
  "start_date": "2026.05.01",
  "end_date": "2026.05.31",
  "status": "진행중",
  "display_order": 1,
  "detail": {
    "title": "이벤트 상세 제목",
    "content_text": "이벤트 설명 내용...",
    "period": "2026.05.01 ~ 2026.05.31",
    "benefits": "혜택 내용",
    "conditions": "참여 조건",
    "images": ["https://..."]
  },
  "products": [
    {
      "product_name": "상품명",
      "brand_name": "브랜드",
      "price": "12,000원",
      "image_url": "https://...",
      "product_url": "https://..."
    }
  ]
}
```

### 12.6 이벤트 수집 전략 (하드코딩 없이)

1. **DOM 패턴 분석**: 범용 CSS 셀렉터로 이벤트 카드 구조 탐지
   - event, promo, campaign 관련 클래스명
   - 리스트/그리드/카드 반복 패턴
   - 이벤트 상세 URL 패턴 (eventDetail, event_view 등)

2. **네트워크 인터셉트 (fallback)**: API 응답에서 이벤트 JSON 배열 탐지
   - 이벤트 관련 키워드 포함 URL 필터
   - 재귀적 JSON 배열 탐지 + 이벤트 필드 자동 매핑

3. **링크 패턴 (fallback 2)**: 페이지 내 이벤트 URL 패턴 링크 수집

### 12.7 대상 사이트

| ID | 사이트 | URL | 카테고리 |
|----|--------|-----|----------|
| 18 | 롯데면세점 이벤트 | kor.lottedfs.com/kr/eventmain/benefit | 경쟁사이벤트 |
| 19 | 신라면세점 이벤트 | shilladfs.com/estore/kr/ko/event | 경쟁사이벤트 |
| 20 | 현대면세점 이벤트 | hddfs.com/event/op/evnt/evntShop.do | 경쟁사이벤트 |

---

## 13. UI ↔ Agent Config 매핑 (Promotion Agent 추가)

### Promotion Agent

| UI 필드 | Agent 내부 필드 | 변환 |
|---------|----------------|------|
| `event_limit_type='all'` | `max_events=0` | 전체 이벤트 수집 |
| `event_limit_type='n'`, `count=N` | `max_events=N` | N건 이벤트 수집 |
| `collect_details` | `collect_details` | 동일 (기본값 true) |
| `collect_event_products` | `collect_event_products` | 동일 (기본값 true) |
| `event_status_filter` | `event_status_filter` | 동일 (기본값 'all') |

---

---

## 15. v2 에이전트 아키텍처 (Phase 14~)

> **설계 결정일**: 2026-05-27
> **배경**: 기존 ProductAgent 삭제 후, 7개 비즈니스 수집 카테고리를 3개 Collector 에이전트로 재설계

### 15.1 설계 배경 및 결정 과정

#### 왜 기존 ProductAgent를 삭제하는가?

1. **실제 수집 실패율 높음**: RuleAnalyzer 기반 자동 플랫폼 감지가 모든 사이트에서 성공하지 않음
2. **코드 복잡도**: 플랫폼 감지 → 전략 선택 → 추출 실행의 3단계 추상화가 디버깅 곤란
3. **비즈니스 요구사항 변경**: 트렌드 분석, 경쟁사 모니터링, 브랜드 공식 가격, 배너 캡처, 브랜드 목록 등 수집 목적이 다양화되어 단일 에이전트로 감당 불가

#### 아키텍처 선택지 분석

| 방안 | 장점 | 단점 | **결정** |
|------|------|------|----------|
| **사이트별 에이전트** (20+개) | 사이트별 최적화 가능 | CLAUDE.md "하드코딩 금지" 위반, 유지보수 불가 | ❌ 기각 |
| **단일 통합 에이전트** (1개) | 코드 중복 없음 | 배너 캡처와 상품 목록이 완전히 다른 패턴, 복잡도 폭발 | ❌ 기각 |
| **카테고리별 에이전트** (7개) | 비즈니스 단위 분리 | 상품 수집 카테고리 5개가 동일 패턴인데 별도 에이전트는 과잉 | ❌ 기각 |
| **수집 패턴별 에이전트** (3개) | 패턴 차이에 따른 자연스러운 분리, config 구동으로 카테고리 대응 | 카테고리별 미세 차이를 config으로 관리해야 함 | ✅ **채택** |

#### 핵심 판단 기준

7개 비즈니스 카테고리의 **실제 수집 패턴**을 분석하면 3가지로 수렴한다:

| 패턴 | 동작 | 해당 카테고리 |
|------|------|-------------|
| **상품 목록 수집** | URL 접속 → 상품 카드 탐색 → 필드 추출 | 트렌드, 경쟁사(면세점), 브랜드 공식, 네이버 스토어, 중국 경쟁사 |
| **배너/비주얼 캡처** | URL 접속 → 배너 영역 식별 → 이미지/텍스트 캡처 | 경쟁사 배너 |
| **목록/디렉토리 수집** | URL 접속 → 목록 구조 탐색 → 항목별 메타데이터 추출 | 브랜드/이벤트 목록 |

---

### 15.2 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                         실행 진입점                                   │
│                                                                     │
│   CLI (main.py)                Web UI (FastAPI /api/crawl/run)      │
│         │                             │                             │
│         └──────────┬──────────────────┘                             │
│                    ▼                                                │
│           agents/__init__.py                                        │
│           AGENT_REGISTRY → get_agent(agent_type)                    │
│                    │                                                │
│     ┌──────────────┼──────────────┬──────────────────┐              │
│     ▼              ▼              ▼                   ▼              │
│  [v2 신규]      [v2 신규]      [v2 신규]          [기존 유지]        │
│  ProductCollector BannerCollector DirectoryCollector                 │
│  (product)      (banner)       (directory)                          │
│     │              │              │                                  │
│     │         ┌────┼──────────────┼──────────────────┐              │
│     │         ▼    ▼              ▼                   ▼              │
│     │      NewsAgent  CafeAgent  PromotionAgent                     │
│     │      (news)     (cafe)     (promotion)                        │
│     │              │              │                                  │
│     └──────────────┼──────────────┘                                 │
│                    ▼                                                │
│              BaseAgent (추상 클래스)                                  │
│              ├── CrawlDB (SQLite)                                   │
│              ├── BrowserManager (Playwright Stealth)                 │
│              ├── ProxyManager (무료 프록시 IP 로테이션)                 │
│              ├── 적응형 백오프 (429/503 대응) + 프록시 교체              │
│              ├── 소프트 차단 감지 (HTTP 200 빈 페이지/이미지만)          │
│              └── 인간형 행동 시뮬레이션                                 │
└─────────────────────────────────────────────────────────────────────┘
```

### 15.3 에이전트 레지스트리 (변경 후)

```python
# agents/__init__.py (변경 예정)
AGENT_REGISTRY = {
    # v2 신규
    "product":    ProductCollector,     # 상품/랭킹 수집 (카테고리 1~5)
    "banner":     BannerCollector,      # 배너/비주얼 수집 (카테고리 6)
    "directory":  DirectoryCollector,   # 브랜드/이벤트 목록 (카테고리 7)
    # 기존 유지
    "news":       NewsAgent,
    "cafe":       CafeAgent,
    "promotion":  PromotionAgent,
}
```

> **참고**: `"product"` 키는 기존과 동일하게 유지하여 DB의 기존 `agent_type='product'` 레코드가 자연스럽게 새 에이전트로 연결된다.

---

### 15.4 에이전트 1: ProductCollector (상품/랭킹 수집)

#### 담당 카테고리

| 카테고리 | 대상 사이트 | 수집 데이터 |
|---------|-----------|-----------|
| 트렌드 분석 | W컨셉, KREAM, 올리브영, 29CM, 무신사 | 순위, 상품명, 가격, 브랜드, 이미지 |
| 경쟁사(면세점) | 롯데/신라/현대 면세점 | 상품명, 가격, 할인율, 사은품, 레퍼런스번호 |
| 브랜드 공식 | Cartier, Chanel, LV, Tiffany, Bulgari, 올리브영 | 상품명, 레퍼런스번호, 가격, 이미지, 상세 |
| 네이버 스토어 | 에스티로더, 케라스타즈 | 상품명, 가격, 브랜드 |
| 중국 경쟁사 | 중국 이커머스 | 상품정보, 가격 |

#### 통합 근거

5개 카테고리 모두 동일한 수집 패턴: **"URL 접속 → 상품 카드 탐색 → 필드 추출"**

차이점(수집 필드, 페이지네이션 방식, 정렬 기준)은 **URL별 crawl_config**으로 분기.

#### 수집 파이프라인

```
┌──────────────────────────────────────────────────────────────┐
│                    ProductCollector                            │
│                                                              │
│  run_site(site_id)                                           │
│    │                                                         │
│    ├── get_crawl_config() → _normalize_config()              │
│    │     URL별 수집 설정 로드 + 기본값 적용                      │
│    │                                                         │
│    ├── 1. 브라우저 시작 (Stealth, 쿠키 로드)                    │
│    ├── 2. _safe_goto(url) → _is_blocked() → _human_dwell()   │
│    │                                                         │
│    ├── 3. _detect_page_structure()                           │
│    │     ├── 네트워크 인터셉트: API 응답에서 상품 JSON 탐지      │
│    │     ├── JS 전역 변수: __NEXT_DATA__ 등에서 상품 데이터     │
│    │     └── DOM 분석: 상품 카드 반복 패턴 탐지                  │
│    │                                                         │
│    ├── 4. _collect_product_list()                            │
│    │     ├── pagination: 'scroll' → 무한 스크롤              │
│    │     ├── pagination: 'click'  → 버튼 클릭 페이지네이션     │
│    │     ├── pagination: 'api'    → API 페이지 파라미터       │
│    │     └── pagination: 'none'   → 현재 페이지만 수집        │
│    │                                                         │
│    ├── 5. (선택) _collect_product_details()                   │
│    │     detail_page=true 시 각 상품 상세 페이지 방문           │
│    │                                                         │
│    ├── 6. _apply_field_filter()                              │
│    │     collect_fields에 명시된 필드만 결과에 포함              │
│    │                                                         │
│    └── 7. _save_results() → DB + JSON 파일                   │
└──────────────────────────────────────────────────────────────┘
```

#### crawl_config 스키마

```json
{
    "collect_fields": ["name", "price", "brand", "image", "rank"],
    "optional_fields": ["discount_rate", "gift", "reference_no", "original_price"],
    "list_type": "ranking",
    "pagination": "scroll",
    "max_pages": 5,
    "max_items": 100,
    "detail_page": false,
    "sort_by": "rank"
}
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `collect_fields` | string[] | `["name","price","brand","image"]` | 필수 수집 필드 목록 |
| `optional_fields` | string[] | `[]` | 선택 수집 필드 (있으면 수집) |
| `list_type` | string | `"catalog"` | 목록 유형: `ranking` / `catalog` / `search` |
| `pagination` | string | `"scroll"` | 페이지네이션: `scroll` / `click` / `api` / `none` |
| `max_pages` | int | `5` | 최대 페이지/스크롤 수 |
| `max_items` | int | `100` | 최대 수집 상품 수 (0=무제한) |
| `detail_page` | bool | `false` | 상품 상세 페이지 진입 여부 |
| `sort_by` | string | `null` | 정렬 기준 (사이트 정렬 파라미터) |

#### 표준 상품 스키마

모든 카테고리의 수집 결과는 동일한 표준 스키마로 정규화:

```json
{
    "rank": 1,
    "name": "상품명",
    "brand": "브랜드명",
    "price": 129000,
    "original_price": 150000,
    "discount_rate": "14%",
    "reference_no": "REF-12345",
    "gift": "사은품 설명",
    "image_url": "https://...",
    "product_url": "https://...",
    "category": "카테고리명",
    "collected_at": "2026-05-27T10:30:00"
}
```

#### _normalize_config() 변환 규칙

```
UI 필드                              → Agent 내부 필드
──────────────────────────────────────────────────────────
collect_fields_ui = [체크박스 선택값]  → collect_fields + optional_fields 분리
list_type_ui = '랭킹'                → list_type = 'ranking'
list_type_ui = '카탈로그'             → list_type = 'catalog'
pagination_ui = '무한 스크롤'         → pagination = 'scroll'
pagination_ui = '페이지 클릭'         → pagination = 'click'
pagination_ui = 'API'               → pagination = 'api'
item_limit_type = 'all'             → max_items = 0
item_limit_type = 'n', count=N     → max_items = N
detail_page_ui = true/false         → detail_page
```

---

### 15.5 에이전트 2: BannerCollector (배너/비주얼 수집)

#### 담당 카테고리

| 카테고리 | 대상 | 수집 데이터 |
|---------|------|-----------|
| 경쟁사 배너 | 경쟁사 메인/이벤트 페이지 | 배너 이미지 URL, 텍스트, 링크, 위치(순서) |

#### 별도 에이전트 근거

상품 카드 추출이 아닌 **"영역 식별 → 이미지/텍스트 캡처"** 패턴.
슬라이더/캐러셀 처리, 이미지 다운로드, 스크린샷 캡처 등 ProductCollector와 완전히 다른 로직 필요.

#### 수집 파이프라인

```
┌──────────────────────────────────────────────────────────────┐
│                    BannerCollector                             │
│                                                              │
│  run_site(site_id)                                           │
│    │                                                         │
│    ├── get_crawl_config() → _normalize_config()              │
│    │                                                         │
│    ├── 1. 브라우저 시작 (Stealth, 쿠키 로드)                    │
│    ├── 2. _safe_goto(url) → _is_blocked() → _human_dwell()   │
│    │                                                         │
│    ├── 3. _detect_banner_areas()                             │
│    │     ├── 슬라이더/캐러셀 컴포넌트 탐지 (swiper, slick 등)   │
│    │     ├── hero/banner 섹션 CSS 셀렉터 탐지                  │
│    │     └── 대형 이미지 요소 (width > threshold) 탐지          │
│    │                                                         │
│    ├── 4. _collect_banners()                                 │
│    │     ├── 각 배너 영역별:                                   │
│    │     │   ├── 이미지 URL 추출                               │
│    │     │   ├── 오버레이 텍스트 추출                            │
│    │     │   ├── 링크(href) 추출                               │
│    │     │   └── 표시 순서(position) 기록                       │
│    │     ├── 슬라이더인 경우:                                   │
│    │     │   ├── 다음 버튼 클릭 반복                            │
│    │     │   └── 각 슬라이드별 위 정보 수집                      │
│    │     └── (선택) _capture_screenshot()                     │
│    │           배너 영역 스크린샷 캡처                           │
│    │                                                         │
│    └── 5. _save_results() → DB + JSON + 이미지 파일            │
└──────────────────────────────────────────────────────────────┘
```

#### crawl_config 스키마

```json
{
    "banner_areas": ["hero", "sub_banner", "popup"],
    "capture_screenshot": true,
    "download_images": false,
    "max_slides": 10,
    "include_text": true
}
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `banner_areas` | string[] | `["hero"]` | 수집할 배너 영역 유형 |
| `capture_screenshot` | bool | `true` | 배너 영역 스크린샷 저장 |
| `download_images` | bool | `false` | 배너 이미지 파일 다운로드 |
| `max_slides` | int | `10` | 슬라이더당 최대 슬라이드 수 |
| `include_text` | bool | `true` | 배너 내 텍스트 추출 여부 |

#### 배너 데이터 스키마

```json
{
    "area_type": "hero",
    "position": 1,
    "image_url": "https://...",
    "text": "배너 텍스트 내용",
    "link_url": "https://...",
    "width": 1200,
    "height": 400,
    "screenshot_path": "output/banners/site_1_hero_1.png",
    "collected_at": "2026-05-27T10:30:00"
}
```

---

### 15.6 에이전트 3: DirectoryCollector (브랜드/이벤트 목록 수집)

#### 담당 카테고리

| 카테고리 | 대상 | 수집 데이터 |
|---------|------|-----------|
| 브랜드/이벤트 목록 | 브랜드 디렉토리 페이지, 이벤트 리스트 | 브랜드명, 카테고리, 이벤트 제목/기간/조건 |

#### 별도 에이전트 근거

**"목록 구조 탐색 → 항목별 메타데이터 추출"** 패턴.
상품 가격/이미지가 아닌 텍스트 중심 구조화된 목록 데이터 수집.

#### 수집 파이프라인

```
┌──────────────────────────────────────────────────────────────┐
│                    DirectoryCollector                          │
│                                                              │
│  run_site(site_id)                                           │
│    │                                                         │
│    ├── get_crawl_config() → _normalize_config()              │
│    │                                                         │
│    ├── 1. 브라우저 시작 (Stealth, 쿠키 로드)                    │
│    ├── 2. _safe_goto(url) → _is_blocked() → _human_dwell()   │
│    │                                                         │
│    ├── 3. _detect_list_structure()                           │
│    │     ├── 알파벳/가나다 인덱스 탐지 (브랜드 목록)             │
│    │     ├── 카드/테이블 반복 패턴 탐지                          │
│    │     └── 카테고리 필터/탭 구조 탐지                          │
│    │                                                         │
│    ├── 4. _collect_directory_items()                          │
│    │     ├── 인덱스 페이지인 경우:                               │
│    │     │   └── 각 인덱스(A~Z, ㄱ~ㅎ) 순회하며 항목 수집        │
│    │     ├── 페이지네이션인 경우:                                │
│    │     │   └── 페이지 순회하며 항목 수집                       │
│    │     └── 단일 페이지인 경우:                                 │
│    │         └── 현재 페이지에서 전체 항목 수집                    │
│    │                                                         │
│    ├── 5. (선택) _collect_item_details()                      │
│    │     각 항목 상세 페이지 방문하여 추가 정보 수집               │
│    │                                                         │
│    └── 6. _save_results() → DB + JSON 파일                   │
└──────────────────────────────────────────────────────────────┘
```

#### crawl_config 스키마

```json
{
    "collect_fields": ["name", "category", "brand_initial"],
    "list_type": "brand_directory",
    "collect_details": false,
    "max_items": 0,
    "index_navigation": true
}
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `collect_fields` | string[] | `["name","category"]` | 수집 필드 |
| `list_type` | string | `"brand_directory"` | 목록 유형: `brand_directory` / `event_list` |
| `collect_details` | bool | `false` | 항목 상세 페이지 진입 여부 |
| `max_items` | int | `0` | 최대 항목 수 (0=무제한) |
| `index_navigation` | bool | `false` | 인덱스(A~Z) 탐색 여부 |

#### 디렉토리 항목 스키마

```json
{
    "name": "브랜드명 또는 이벤트 제목",
    "category": "카테고리",
    "brand_initial": "A",
    "detail_url": "https://...",
    "description": "설명",
    "period": "2026.05.01 ~ 2026.05.31",
    "status": "진행중",
    "collected_at": "2026-05-27T10:30:00"
}
```

---

### 15.7 카테고리 → 에이전트 매핑 (변경 후)

```javascript
// SiteSettings.jsx - agentTypeFromCategory()
const agentTypeFromCategory = (cat) => {
    if (cat === '뉴스') return 'news'
    if (cat === '카페') return 'cafe'
    if (cat === '경쟁사이벤트') return 'promotion'
    if (cat === '경쟁사배너') return 'banner'
    if (cat === '브랜드목록') return 'directory'
    // 트렌드매장, 경쟁사, 브랜드공식, 네이버스토어, 중국경쟁사, 당사온라인몰 등
    return 'product'
}
```

| 카테고리 | 에이전트 | 수집 패턴 |
|---------|---------|----------|
| 트렌드매장 | `product` (ProductCollector) | 상품 랭킹/목록 |
| 경쟁사 | `product` (ProductCollector) | 상품 가격/할인/사은품 |
| 브랜드공식 | `product` (ProductCollector) | 상품 레퍼런스/가격 |
| 네이버스토어 | `product` (ProductCollector) | 상품 목록 |
| 중국경쟁사 | `product` (ProductCollector) | 상품 정보 |
| 경쟁사배너 | `banner` (BannerCollector) | 배너 이미지/텍스트 |
| 브랜드목록 | `directory` (DirectoryCollector) | 브랜드/이벤트 목록 |
| 뉴스 | `news` (NewsAgent) | 뉴스 기사 |
| 카페 | `cafe` (CafeAgent) | 카페 인기글 |
| 경쟁사이벤트 | `promotion` (PromotionAgent) | 이벤트/프로모션 |

---

### 15.8 Config 구동 설계 (핵심 원칙)

#### 하드코딩 없이 카테고리별 차이를 처리하는 방법

사이트별 수집 로직을 코드에 하드코딩하지 않고, **URL별 crawl_config**에 수집 필드/방식을 설정하여 동일 에이전트가 다양한 사이트를 처리한다.

```
[카테고리 기본 템플릿]
  사이트 등록 시 카테고리 선택 → 해당 카테고리의 기본 config 자동 적용

[URL별 커스터마이징]
  기본 config 적용 후, 사용자가 UI에서 수집 필드/방식을 URL별로 수정 가능

[에이전트 실행 시]
  crawl_config 로드 → _normalize_config() → 설정에 따라 동작 분기
```

#### 카테고리별 기본 config 템플릿

```python
CATEGORY_DEFAULT_CONFIGS = {
    "트렌드매장": {
        "collect_fields": ["rank", "name", "price", "brand", "image"],
        "list_type": "ranking",
        "pagination": "scroll",
        "max_pages": 3,
        "detail_page": False,
    },
    "경쟁사": {
        "collect_fields": ["name", "price", "brand", "image"],
        "optional_fields": ["discount_rate", "gift", "reference_no", "original_price"],
        "list_type": "catalog",
        "pagination": "click",
        "max_pages": 5,
        "detail_page": True,
    },
    "브랜드공식": {
        "collect_fields": ["name", "reference_no", "price", "image"],
        "optional_fields": ["original_price", "category"],
        "list_type": "catalog",
        "pagination": "scroll",
        "max_pages": 10,
        "detail_page": True,
    },
    "네이버스토어": {
        "collect_fields": ["name", "price", "brand", "image"],
        "list_type": "catalog",
        "pagination": "scroll",
        "max_pages": 5,
        "detail_page": False,
    },
    "중국경쟁사": {
        "collect_fields": ["name", "price", "brand", "image"],
        "list_type": "catalog",
        "pagination": "click",
        "max_pages": 3,
        "detail_page": False,
    },
    "경쟁사배너": {
        "banner_areas": ["hero", "sub_banner"],
        "capture_screenshot": True,
        "download_images": False,
        "max_slides": 10,
    },
    "브랜드목록": {
        "collect_fields": ["name", "category"],
        "list_type": "brand_directory",
        "index_navigation": True,
        "collect_details": False,
    },
}
```

---

### 15.9 UI 변경 방향

#### 사이트 등록 시

1. 카테고리 선택 → 에이전트 자동 매핑 (기존과 동일 패턴)
2. 카테고리 기본 config 자동 생성 → crawl_config에 저장
3. 사용자가 필요 시 수집 설정 커스터마이징

#### URL별 수집 설정 모달 (신규)

| 에이전트 | 설정 UI |
|---------|---------|
| ProductCollector | 수집 필드 체크박스, 페이지네이션 방식, 상세 페이지 진입 토글, 최대 수집 건수 |
| BannerCollector | 배너 영역 선택, 스크린샷 저장 토글, 이미지 다운로드 토글 |
| DirectoryCollector | 수집 필드 선택, 인덱스 탐색 토글, 상세 진입 토글 |

#### 결과 상세 뷰

| 에이전트 | 상세 뷰 |
|---------|---------|
| ProductCollector | 상품 테이블 (기존 ProductDetail 개선) |
| BannerCollector | 이미지 그리드 + 텍스트 오버레이 표시 |
| DirectoryCollector | 항목 목록 테이블 |

---

### 15.10 DB 변경 사항

#### crawl_sites 테이블

기존 스키마 유지. `agent_type` 컬럼에 `'banner'`, `'directory'` 값 추가.

```sql
-- 기존 agent_type 값: 'product', 'news', 'cafe', 'promotion'
-- 추가 agent_type 값: 'banner', 'directory'
```

#### crawl_results 테이블

기존 스키마 유지. `products` JSON 컬럼에 에이전트별 다른 데이터 구조 저장:

| agent_type | products 컬럼 내용 |
|-----------|-------------------|
| `product` | `[{rank, name, price, brand, ...}]` 상품 배열 |
| `banner` | `[{area_type, position, image_url, text, ...}]` 배너 배열 |
| `directory` | `[{name, category, brand_initial, ...}]` 디렉토리 항목 배열 |

---

### 15.11 기존 에이전트와의 관계

| 에이전트 | 상태 | 비고 |
|---------|------|------|
| ProductAgent (v1) | **삭제** | `agents/product/engine.py` 삭제 후 ProductCollector로 대체 |
| NewsAgent | **유지** | 변경 없음 |
| CafeAgent | **유지** | 변경 없음 |
| PromotionAgent | **유지** | DirectoryCollector와 역할 중복 검토 필요 (이벤트 목록 vs 이벤트 상세) |
| ProductCollector | **신규** | `agents/product/engine.py` |
| BannerCollector | **신규** | `agents/banner/engine.py` |
| DirectoryCollector | **신규** | `agents/directory/engine.py` |

#### PromotionAgent와 DirectoryCollector의 역할 경계

- **PromotionAgent**: 이벤트 목록 → **상세 페이지 진입** → 이벤트 내 상품 수집 (3단계 깊이)
- **DirectoryCollector**: 브랜드/이벤트 **목록만** 수집, 상세 진입은 선택적이며 상품 수집 없음

둘은 목적이 다르므로 병합하지 않는다.

---

### 15.12 공통 인프라 활용

v2 에이전트도 기존 공통 인프라를 그대로 활용:

| 인프라 | 활용 | 비고 |
|--------|------|------|
| BaseAgent | 모든 v2 에이전트가 상속 | 봇 차단 대응, 적응형 백오프, 프록시 로테이션, 소프트 차단 감지 |
| BrowserManager | 그대로 사용 | Stealth Chromium, 쿠키 영속화, 프록시 context 지원 |
| ProxyManager | --proxy 옵션 시 활성화 | 무료 프록시 수집/검증/로테이션 |
| RuleAnalyzer | ProductCollector에서 선택적 활용 | 자동 플랫폼 감지 (필수가 아닌 보조) |
| NetworkInterceptor | ProductCollector에서 API 탐지 시 | 네트워크 기반 상품 데이터 탐지 |
| strategies/ | ProductCollector에서 선택적 활용 | state_var, dom, api 추출 |

---

### 15.13 구현 순서 (계획)

```
1단계: 기존 ProductAgent 삭제 + ProductCollector 기본 구현
       → 트렌드 사이트 1개로 수집 테스트

2단계: ProductCollector config 구동 완성
       → 5개 카테고리 전체 대상 사이트 수집 테스트

3단계: BannerCollector 구현
       → 경쟁사 배너 수집 테스트

4단계: DirectoryCollector 구현
       → 브랜드 목록 수집 테스트

5단계: UI 변경 (설정 모달 + 결과 상세 뷰)
       → 전체 통합 테스트

6단계: 카테고리 기본 config 템플릿 + UI 연동
       → 사이트 등록 시 자동 config 생성 테스트
```

---

## 16. OrderAgent (agents/order/engine.py)

### 16.1 개요

면세점 주문서 페이지에서 결제 요약(정상가/할인/혜택/결제금액)과 장바구니 상품 정보를 수집한다.
로그인 필수 → 주문서 페이지 접속 → 결제정보/상품 추출.

**별도 에이전트 근거**: 상품 목록 수집과 완전히 다른 패턴 — 로그인 필수, 주문서 고유 DOM 구조, 결제 요약 데이터.

### 16.2 수집 파이프라인

```
run_site(site_id)
  │
  ├── _normalize_config()
  ├── 브라우저 시작
  │
  ├── _get_next_credential()     계정 로테이션 (라운드로빈)
  ├── _safe_goto(login_url)      로그인 페이지 이동
  ├── _do_login()                범용 로그인 (자동 폼 탐지)
  │
  ├── _safe_goto(order_url)      주문서 페이지 이동 (도메인 다를 수 있음)
  ├── _human_dwell + _human_scroll
  │
  ├── _JS_EXTRACT_ORDER_PAYMENT  결제정보 + 장바구니 추출
  │     ├── 장바구니 상품: 상품명/수량/정상가/판매가/브랜드
  │     └── 결제 요약: 정상가/회원할인/혜택/결제금액/면세한도/적립
  │
  └── _save_json()               order_payment.json + crawl_result.json
```

### 16.3 crawl_config 필드

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `login_url` | '' | 로그인 페이지 URL (비워두면 site_url) |
| `order_url` | '' | 주문서 페이지 URL (비워두면 site_url) |
| `collect_items` | true | 장바구니 상품 수집 여부 |
| `collect_payment` | true | 결제 요약 수집 여부 |
| `login_config` | {} | 로그인 폼 셀렉터 (비워두면 자동 탐지) |

### 16.4 결제정보 라벨 매핑

| 한국어 라벨 | 영문 키 |
|------------|---------|
| 정상가/상품금액 | `regular_price` |
| 회원할인 | `member_discount` |
| 혜택/할인혜택 | `benefits` |
| 쿠폰할인 | `coupon_discount` |
| 결제금액 | `payment_amount` |
| 최종결제금액 | `final_payment` |
| 면세한도적용금액 | `duty_free_limit` |
| 과세포인트 | `tax_point` |
| 적립/L.POINT | `reward_points` |
| 배송비 | `shipping_fee` |
| 할인율 | `discount_rate` |

### 16.5 대상 사이트

| ID | 사이트 | 로그인 URL | 주문서 URL |
|----|--------|-----------|-----------|
| 54 | 롯데면세점 주문서 | kor.lottedfs.com/kr/login | kor.lps.lottedfs.com/kr/newOrder |
| (예정) | 신라면세점 주문서 | shilladfs.com 로그인 | 신라 주문서 URL |
| (예정) | 현대면세점 주문서 | hddfs.com 로그인 | 현대 주문서 URL |

---

## 17. 관련 문서

| 문서 | 경로 | 내용 |
|------|------|------|
| UI 설계 문서 | `web/UI_DESIGN.md` | 웹 대시보드 UI/페이지/API/스타일 설계 |
| 봇 차단 대응 | `web/ANTI_BOT.md` | 6계층 봇 차단 우회 기술 (프록시 로테이션 + 소프트 차단 감지 포함) |
| 진행사항 | `web/PROGRESS.md` | 전체 개발 이력 (Phase 1~16) |
