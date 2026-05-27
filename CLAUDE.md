# 크롤링 관리 플랫폼 — AI 개발 가이드

> 이 파일은 AI(Claude, Cursor 등)가 매 세션 시작 시 읽는 프로젝트 컨텍스트입니다.
> 바이브코딩으로 협업할 때 **설계 일관성을 유지**하기 위해 반드시 이 가이드를 따라주세요.
> 변경 시 팀원과 합의 후 수정하고, git commit에 변경 사유를 남겨주세요.

---

## 1. 프로젝트 개요

멀티 사이트 웹 크롤링 플랫폼. CLI + React 웹 대시보드에서 사이트 등록/설정/실행/결과 확인을 관리한다.

**핵심 구조**: 6개 에이전트(product, news, cafe, promotion, banner, directory)가 Stealth 브라우저로 사이트를 수집하고, 결과를 SQLite DB에 저장한다.

**현재 버전**: Phase 17 (2026-05-27 기준)
- ProductAgent v2: 3단계 페이지 구조 분석(API → JS전역변수 → DOM) + 배지 필터링 + 카드 클릭 상세 수집
- 상세 수집: description(4단계 fallback + 노이즈 필터링) + spec(테이블/dl 추출) + detail_images(썸네일 필터링)
- 웹 대시보드: 크롤링 실행/중지/로그 뷰어 + 에이전트별 설정 모달 + URL 분석

---

## 2. 반드시 지킬 설계 원칙

### 2.1 절대 규칙 (위반 금지)

| 규칙 | 이유 |
|------|------|
| **LLM/AI API 호출 금지** | ANTHROPIC_API_KEY 없음. 모든 분석/추출은 규칙 기반(RuleAnalyzer) |
| **사이트별 하드코딩 금지** | 크롤링 대상은 동적으로 변경됨. 플랫폼 감지 + 템플릿으로 동적 대응 |
| **UI-Agent 분리 유지** | UI는 사용자 친화적 필드, Agent는 내부 필드. `_normalize_config()`으로 변환 |
| **모든 작업 내역 .md 기록** | 작업 완료 후 반드시 `web/PROGRESS.md`에 Phase N으로 추가 |

### 2.2 아키텍처 규칙

| 규칙 | 설명 |
|------|------|
| **에이전트 추가 시** | BaseAgent 상속 + `AGENT_REGISTRY`에 등록 + `_normalize_config()` 구현 |
| **추출 전략 추가 시** | `core/strategies/` 에 클래스 생성 + `STRATEGY_MAP`에 등록 |
| **API 추가 시** | `web/backend/routes/` 에 라우터 생성 + `app.py`에 `include_router` 등록 |
| **페이지 추가 시** | `web/frontend/src/pages/` 에 컴포넌트 + `App.jsx`에 Route 추가 |
| **설정 변경 UI 추가 시** | 반드시 ConfirmModal 적용 (`showConfirm()` 패턴) |

---

## 3. 기술 스택 (변경 전 합의 필요)

| 영역 | 기술 | 비고 |
|------|------|------|
| Backend | FastAPI + uvicorn | port 8000 |
| Frontend | React 18 + Vite | port 5173, proxy → 8000 |
| DB | SQLite (`data/crawling.db`) | `core.db.CrawlDB` 클래스 |
| 브라우저 | Playwright + playwright_stealth | Stealth Chromium |
| 차트 | recharts | OCR 통계 시각화 |
| 스타일 | CSS Variables (`App.css`) | 외부 CSS 프레임워크 사용 금지 |
| Python | `.venv` 가상환경 | `D:\crawling\.venv\Scripts\python.exe` |

---

## 4. 디렉토리 구조 (파일 위치 규칙)

```
D:\crawling\
├── agents/                     # 에이전트 (도메인별 수집 로직)
│   ├── __init__.py             # AGENT_REGISTRY (6개 에이전트 등록)
│   ├── product/engine.py       # ProductAgent (v2) — 상품/랭킹 수집
│   ├── news/engine.py          # NewsAgent — 뉴스 기사 수집
│   ├── cafe/engine.py          # CafeAgent — 카페 인기글 수집
│   ├── promotion/engine.py     # PromotionAgent — 이벤트/프로모션 수집
│   ├── banner/engine.py        # BannerAgent (v2) — 배너/비주얼 캡처
│   └── directory/engine.py     # DirectoryAgent (v2) — 브랜드/이벤트 목록
├── core/                       # 공통 인프라
│   ├── base_agent.py           # BaseAgent 추상 클래스
│   ├── browser.py              # BrowserManager (Stealth)
│   ├── db.py                   # CrawlDB (SQLite)
│   ├── network_interceptor.py  # 네트워크 요청 캡처
│   ├── rule_analyzer.py        # 규칙 기반 사이트 분석
│   ├── ocr.py                  # OCR 이중화 (Document Parse + Tesseract)
│   └── strategies/             # 추출 전략 (state_var, dom, api)
├── web/
│   ├── backend/                # FastAPI REST API
│   │   ├── app.py
│   │   └── routes/             # sites.py, results.py, ocr.py
│   ├── frontend/               # React SPA
│   │   └── src/
│   │       ├── App.jsx         # 라우터
│   │       ├── App.css         # 전역 스타일 (CSS Variables)
│   │       ├── pages/          # Dashboard, SiteSettings, CrawlResults, OcrUsage
│   │       └── components/     # Layout, StatCard
│   ├── PROGRESS.md             # 작업 이력 (Phase 1~16)
│   ├── UI_DESIGN.md            # UI 설계 문서
│   ├── AGENT_DESIGN.md         # Agent 설계 문서
│   └── ANTI_BOT.md             # 봇 차단 대응 기술 문서
├── main.py                     # CLI 진입점 (python main.py run --id N)
├── data/                       # DB + 쿠키 (data/cookies/)
├── logs/                       # 크롤링 실행 로그 (crawl_{id}_{timestamp}.log)
└── output/                     # 수집 결과 JSON (products.json, product_details.json, crawl_result.json)
```

---

## 5. 코딩 컨벤션

### 5.1 Python (Backend / Agent)

```python
# 클래스: PascalCase
class ProductAgent(BaseAgent):

# 메서드: snake_case, private은 _ 접두사
def _normalize_config(self, crawl_cfg: dict) -> dict:

# 상수: UPPER_SNAKE_CASE
ADAPTIVE_BACKOFF = { "base_wait_secs": 120 }

# docstring: 한국어, 첫 줄에 요약
def _safe_goto(self, url):
    """page.goto() 래퍼: 429/503 응답 시 적응형 지수 백오프 재시도."""
```

### 5.2 React (Frontend)

```jsx
// 컴포넌트: PascalCase, 함수형
function ProductConfig({ site, onSaved, showConfirm, closeConfirm }) {

// 상수: UPPER_SNAKE_CASE
const SCHEDULE_OPTIONS = [...]
const CATEGORY_LABELS = {...}

// 상태: camelCase
const [configEdit, setConfigEdit] = useState(null)

// API 호출: fetch + /api/ 접두사
fetch('/api/sites').then(r => r.json())

// 설정 변경 시 반드시 ConfirmModal 사용
showConfirm({
  title: '변경 확인',
  message: `"${name}" 을 변경하시겠습니까?`,
  confirmLabel: '변경',
  onConfirm: async () => { closeConfirm(); /* ... */ },
})
```

### 5.3 CSS 규칙

```css
/* 반드시 CSS Variables 사용 — 하드코딩 색상 금지 */
color: var(--primary);        /* O */
color: #3b82f6;               /* X — 직접 색상 사용 금지 */

/* 새 컴포넌트 스타일은 App.css에 섹션 주석과 함께 추가 */
/* ─── New Component Name ─── */
.new-component { ... }
```

---

## 6. 에이전트 개발 패턴

### 6.1 새 에이전트 추가 시 체크리스트

```
1. agents/{type}/engine.py 생성
   - BaseAgent 상속
   - agent_type 프로퍼티 구현
   - _normalize_config() 구현 (UI → Agent 필드 변환)
   - run_site(site_id) 구현

2. agents/__init__.py 에 등록
   - AGENT_REGISTRY에 추가

3. 카테고리-에이전트 매핑 추가
   - SiteSettings.jsx의 agentTypeFromCategory() 수정

4. 설정 모달 추가
   - SiteSettings.jsx에 {Type}Config 컴포넌트 추가
   - ConfigModal에 분기 추가

5. 결과 상세 뷰 추가
   - CrawlResults.jsx에 {Type}Detail 컴포넌트 추가
   - ExpandedDetail에 분기 추가

6. 문서 업데이트
   - AGENT_DESIGN.md에 파이프라인/config 추가
   - UI_DESIGN.md에 설정 모달/상세 뷰 추가
   - PROGRESS.md에 Phase N 기록
```

### 6.2 봇 차단 대응 필수 패턴

모든 페이지 접속은 이 패턴을 따라야 한다:

```python
resp = self._safe_goto(url)         # 적응형 백오프
if self._is_blocked(resp):          # 차단 감지
    return                          # 건너뜀
self._human_dwell()                 # 체류 시뮬레이션
self._human_scroll()                # 스크롤 시뮬레이션
# ... 데이터 수집 ...
self._delay()                       # 다음 페이지 전 딜레이
```

---

## 7. UI 개발 패턴

### 7.1 설정 변경 시 반드시 ConfirmModal 사용

```javascript
// 직접 실행 금지
await fetch(`/api/sites/${id}/toggle`, { method: 'PUT' })  // X

// ConfirmModal을 통해 실행
showConfirm({
  title: '상태 변경',
  message: `사이트를 변경하시겠습니까?`,
  onConfirm: async () => {
    closeConfirm()
    await fetch(`/api/sites/${id}/toggle`, { method: 'PUT' })  // O
    loadSites()
  },
})
```

### 7.2 카테고리-에이전트 자동 매핑

사용자는 에이전트 유형을 모른다. 카테고리 선택 시 자동 결정:

```javascript
const agentTypeFromCategory = (cat) => {
  if (cat === '뉴스') return 'news'
  if (cat === '카페') return 'cafe'
  if (cat === '경쟁사이벤트') return 'promotion'
  if (cat === '경쟁사배너') return 'banner'
  if (cat === '브랜드목록') return 'directory'
  return 'product'
}
```

### 7.3 에이전트별 설정 모달 분기

```jsx
// ConfigModal 내부
{agentType === 'product'   && <ProductConfig   ... />}
{agentType === 'news'      && <NewsConfig      ... />}
{agentType === 'cafe'      && <CafeConfig      ... />}
{agentType === 'promotion' && <PromotionConfig ... />}
{agentType === 'banner'    && <BannerConfig    ... />}
{agentType === 'directory' && <DirectoryConfig ... />}
```

---

## 8. API 규칙

| 규칙 | 설명 |
|------|------|
| 접두사 | 모든 API는 `/api/` 접두사 |
| 라우트 순서 | batch/고정 경로를 parameterized 경로 앞에 배치 |
| DB 관리 | 매 요청마다 `_db()` 생성 → try/finally로 `db.close()` |
| 크롤링 실행 | `subprocess.Popen`으로 별도 프로세스, `PYTHONIOENCODING=utf-8` 필수 |
| CLI 명령어 | `python main.py run --id {N}` (NOT `--site-id`) |

### 8.1 주요 API 엔드포인트

```
사이트: GET/POST /api/sites, PUT /api/sites/{id}/config, /toggle, /schedule
키워드: GET/POST /api/sites/{id}/keywords, DELETE .../keywords/{kw}
크롤링: POST /api/crawl/run, GET /api/crawl/status, POST /api/crawl/stop
로그:   GET /api/crawl/logs/{site_id}, GET /api/crawl/logs/{site_id}/raw
URL분석: POST /api/sites/analyze-url
결과:   GET /api/results, GET /api/results/{id}, GET /api/dashboard/stats
OCR:    GET /api/ocr/summary, GET /api/ocr/detail, GET /api/ocr/sites
```

---

## 9. 설계 문서 위치

작업 전 반드시 관련 문서를 읽고 시작하세요:

| 문서 | 용도 | 읽어야 할 때 |
|------|------|------------|
| `web/UI_DESIGN.md` | 페이지/컴포넌트/API/스타일 설계 | UI 작업 시 |
| `web/AGENT_DESIGN.md` | 에이전트 파이프라인/config/인프라 설계 | Agent 작업 시 |
| `web/ANTI_BOT.md` | 봇 차단 대응 5계층 기술 | 크롤링 로직 수정 시 |
| `web/PROGRESS.md` | 전체 작업 이력 (Phase 1~16) | 작업 시작 전 현황 파악 |

---

## 10. 작업 완료 후 체크리스트

```
[ ] 코드가 기존 패턴과 일관성 있는가?
[ ] CSS Variables를 사용했는가? (하드코딩 색상 없음)
[ ] 설정 변경에 ConfirmModal을 적용했는가?
[ ] _normalize_config()으로 UI-Agent 필드를 분리했는가?
[ ] 봇 차단 대응 패턴을 따랐는가? (_safe_goto → _is_blocked → _human_dwell)
[ ] web/PROGRESS.md에 작업 내역을 기록했는가?
[ ] 관련 설계 문서(.md)를 업데이트했는가?
```

---

## 11. 현재 시스템 상태 요약 (2026-05-27 기준)

### 11.1 에이전트 레지스트리

```python
AGENT_REGISTRY = {
    "product":   ProductAgent,    # v2 — 3단계 페이지 구조 분석
    "news":      NewsAgent,       # 뉴스 키워드 검색/수집
    "cafe":      CafeAgent,       # 네이버 카페 인기글 + OCR
    "promotion": PromotionAgent,  # 이벤트/프로모션 3단계 수집
    "banner":    BannerAgent,     # v2 — 배너 이미지/텍스트 캡처
    "directory": DirectoryAgent,  # v2 — 브랜드/이벤트 목록
}
```

### 11.2 ProductAgent v2 핵심 구조 (agents/product/engine.py)

```
수집 파이프라인:
  1. config 로드 + _normalize_config()
  2. 브라우저 시작 + NetworkInterceptor + 페이지 접속
  3. _detect_page_structure(): API → JS전역변수 → DOM (3단계 fallback)
  4. _collect_products(): scroll / click / api / none 페이지네이션
  5. _collect_details(): URL 이동 또는 카드 클릭 기반 상세 수집
  6. _normalize_products(): _FIELD_ALIASES(12필드×80+별칭) 기반 정규화
  7. _save_json(): products.json + product_details.json + crawl_result.json

DOM 탐지 (_JS_FIND_DOM_PRODUCTS) 핵심 로직:
  - Pass 1: 빈도 분석 — 카드 간 반복되는 짧은 텍스트(≤10자, 30%+)를 배지로 자동 필터링
  - Pass 2: 클래스 기반 시멘틱 추출 → 배지 클래스 필터링 → 가장 긴 텍스트=상품명
  - 가격: <del>/<s> 태그 + 클래스 컨텍스트로 원가/판매가 분류
  - javascript: URL → product_id 추출 + 카드 클릭 기반 상세 수집

상세 수집 (_collect_details) 두 가지 모드:
  - URL 기반: product_url이 있으면 직접 이동
  - 클릭 기반: URL 없을 때 _JS_CLICK_CARD로 product_id/image 기준 카드 클릭 → go_back() 복귀

상세 추출 (_JS_EXTRACT_DETAIL) 3가지 데이터:
  - description: OG → meta → DOM 셀렉터 → 최대 텍스트 (4단계 fallback, 노이즈 필터링)
  - spec: 테이블 th-td / dl dt-dd 기반 제품 스펙 추출 (제품명/성분/용량 등)
  - detail_images: 상세 영역 이미지 + 썸네일 필터링 (resize/NxN 패턴 제외)
```

### 11.3 웹 UI 주요 컴포넌트 (SiteSettings.jsx ~2500줄)

```
주요 컴포넌트:
  - SiteSettings: 메인 페이지 (카테고리별 그룹 테이블)
  - AddSiteModal: 사이트 추가 (카테고리→에이전트 자동 매핑 + URL 분석)
  - ConfigModal: 에이전트별 설정 분기 (6종)
  - ProductConfig: 수집 필드 체크박스 + URL 분석 + extra_fields
  - NewsConfig: 키워드 관리 + 수집 설정
  - CafeConfig: 날짜 범위 + 수집 항목 토글
  - PromotionConfig: 이벤트 수집 설정
  - BannerConfig: 배너 영역 + 스크린샷 설정
  - DirectoryConfig: 목록 수집 설정
  - UrlAnalyzePanel: URL 분석 → 추가 수집 필드 발견 (savedExtraFields 지원)
  - LogViewerModal: 2초 자동 갱신 터미널 스타일 로그 뷰어
  - ConfirmModal: 모든 변경/실행에 확인 절차 (danger/run/default 타입)

크롤링 실행/중지:
  - ▶ 실행 버튼 → POST /api/crawl/run → subprocess.Popen
  - ■ 중지 버튼 → POST /api/crawl/stop → taskkill (Windows) / kill (Linux)
  - 📋 로그 버튼 → LogViewerModal (GET /api/crawl/logs/{site_id})
  - 5초 폴링으로 실행 상태 추적 (GET /api/crawl/status)
```

### 11.4 출력 파일 구조

```
output/{site_id}_{site_name}/
  ├── products.json         # 기본 상품 목록 (description/detail_images 제외)
  ├── product_details.json  # 전체 상품 + 상세 정보 (description, detail_images)
  └── crawl_result.json     # 메타데이터 + 요약 통계 (total_products, detail_collected)

logs/
  └── crawl_{site_id}_{timestamp}.log  # 크롤링 실행 로그 (stdout+stderr)
```

### 11.5 알려진 이슈/주의사항

- Windows에서 subprocess 실행 시 `PYTHONIOENCODING=utf-8` 환경변수 필수 (cp949 인코딩 문제)
- `_log()` 함수는 UnicodeEncodeError 안전 처리 포함 (utf-8 fallback)
- CLI 명령어: `python main.py run --id {N}` (NOT `--site-id`)
- 봇 차단 대응: 단시간 반복 접속 시 사이트별 IP 차단 가능 (30분~1시간 쿨다운)
