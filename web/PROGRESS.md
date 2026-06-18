# 크롤링 관리 웹 대시보드 - 진행사항

## 변경 이력 (시간순)

### Phase 1. 웹 대시보드 기본 구축
> 설계 → 백엔드 API → 프론트엔드 4개 페이지 → 통합 실행

**사용자 요청**: 크롤링 플랫폼을 CLI에서 React 기반 웹 UI로 전환

**작업 내역**:
1. `web/backend/app.py` - FastAPI 메인 앱 (CORS, 정적파일 서빙)
2. `web/backend/routes/sites.py` - 사이트 CRUD API
3. `web/backend/routes/results.py` - 수집 결과 조회 + 대시보드 통계 API
4. `web/backend/routes/ocr.py` - OCR 사용 이력 API
5. `web/frontend/` - React 18 + Vite 프로젝트 생성
6. `src/components/Layout.jsx` - 사이드바 + 컨텐츠 레이아웃
7. `src/components/StatCard.jsx` - 통계 카드 컴포넌트
8. `src/pages/Dashboard.jsx` - 대시보드 (통계 카드 + 최근 크롤링)
9. `src/pages/SiteSettings.jsx` - 수집 대상 설정 (사이트 목록, 카테고리별 그룹)
10. `src/pages/CrawlResults.jsx` - 수집 결과 조회
11. `src/pages/OcrUsage.jsx` - OCR 사용 이력/통계
12. `web/start_web.py` - 원클릭 실행 (FastAPI + Vite dev server 동시 실행)

**수정된 파일**: `web/backend/app.py`, `web/backend/routes/sites.py`, `web/backend/routes/results.py`, `web/backend/routes/ocr.py`, `web/frontend/*` (전체 프론트엔드)

---

### Phase 2. 수집 주기 + 실행 기능 추가
> SiteSettings 페이지에 스케줄/실행 UI 추가

**사용자 요청**: 수집주기 선택기(시간/일간/주간/월간)와 실행 버튼(개별/카테고리 일괄/주기별 일괄) 추가

**작업 내역**:
1. `sites.py` - 스케줄 API 추가 (`PUT /sites/{id}/schedule`, `PUT /sites/batch/schedule`)
2. `sites.py` - 크롤링 실행 API 추가 (`POST /crawl/run`, `GET /crawl/status`)
3. `sites.py` - 라우트 순서 수정 (batch 라우트를 parameterized 라우트 앞으로)
4. `SiteSettings.jsx` - 각 사이트 행에 수집주기 드롭다운 추가
5. `SiteSettings.jsx` - 카테고리 헤더에 일괄 실행 버튼 추가
6. `SiteSettings.jsx` - 상단에 전체 실행 / 주기별 실행 바 추가
7. `SiteSettings.jsx` - 실행 상태 실시간 폴링 (5초 간격)
8. `App.css` - `.schedule-select`, `.btn-run`, `.row-running`, `.running-status-bar` 스타일

**수정된 파일**: `web/backend/routes/sites.py`, `web/frontend/src/pages/SiteSettings.jsx`, `web/frontend/src/App.css`

**에러 수정**:
- Port 8000 충돌 (`[Errno 10048]`) → 이전 프로세스 kill 후 재시작
- 라우트 매칭 버그 (`PUT /sites/batch/schedule`이 `{site_id}`로 매칭) → 라우트 순서 수정
- JSX Unicode escape 에러 (`\u{1F504}` → 실제 이모지 문자로 교체)

---

### Phase 3. 확인 다이얼로그 추가
> 모든 설정 변경에 ConfirmModal 적용

**사용자 요청**: 설정 변경 시 확인 과정을 거치도록 confirm 창 스타일 추가

**작업 내역**:
1. `SiteSettings.jsx` - `ConfirmModal` 컴포넌트 신규 추가
2. `SiteSettings.jsx` - `showConfirm()` / `closeConfirm()` 상태 관리
3. 적용 대상: 활성/비활성 토글, 수집주기 변경, 크롤링 실행, 설정 저장, 키워드 추가/삭제, 사이트 추가
4. `App.css` - `.confirm-dialog`, `.confirm-icon`, `.confirm-title`, `@keyframes confirmAppear` 스타일

**수정된 파일**: `web/frontend/src/pages/SiteSettings.jsx`, `web/frontend/src/App.css`

---

### Phase 4. 배치 스케줄 일괄 변경
> 전체 사이트 수집주기 일괄 업데이트

**사용자 요청**: 수집주기를 모두 일간으로 변경해서 반영

**작업 내역**:
1. 전체 29개 사이트의 `crawl_schedule`을 `daily`로 일괄 업데이트
2. 백엔드 `PUT /sites/batch/schedule` API 활용

---

### Phase 5. Product 수집 설정 구조 변경
> 매장/상품을 독립 섹션으로 분리

**사용자 요청**: 상품 설정에서 매장/상품을 분리하고, 각각 전체/건수를 독립 등록할 수 있어야 함. 둘 다 항상 활성 (on/off 토글 없음)

**작업 내역**:
1. `SiteSettings.jsx` - `ProductConfig` 컴포넌트를 두 섹션(매장 수집 / 상품 수집)으로 분리
2. config 필드: `store_limit_type`, `store_limit_count`, `product_limit_type`, `product_limit_count`
3. 체크박스 제거 → 양 섹션 모두 항상 `.active` 클래스 적용
4. `App.css` - `.product-config-section`, `.config-section-title`, `.config-sub`, `.config-sub-label` 스타일

**수정된 파일**: `web/frontend/src/pages/SiteSettings.jsx`, `web/frontend/src/App.css`

---

### Phase 6. UI ↔ Agent 맵핑 분석
> UI 설정 필드와 Agent crawl_config 필드 간 차이 분석

**사용자 요청**: UI 설정 항목과 구현된 agent 유형 맵핑을 할 수 있는지 확인

**작업 내역**:
1. `agents/product/engine.py` 분석 → UI 필드명과 Agent 필드명 완전 불일치 확인
2. `agents/news/engine.py` 분석 → 핵심 필드 일치, `max_articles`만 UI에 없음
3. `agents/cafe/engine.py` 분석 → 대부분 1:1 일치, `max_pages`/`date_range_days`만 UI에 없음
4. 맵핑 테이블 제공 및 Product Agent 해결 방안(UI 저장시 변환 vs Agent 수정) 제시

**결론**: 맵핑 가능하나 Product Agent에서 필드명 변환 레이어가 필요

---

### Phase 7. 수집 모드 UI 추가 + Agent 전면 수정
> Product에 단일 매장/도메인 전체 모드 추가, 3개 Agent 모두 config 정규화

**사용자 요청**:
- URL이 특정 매장이면 해당 매장만, 도메인 홈이면 전체 매장 수집
- 추천 UI 변경안으로 UI 변경 + Agent 변경 모두 진행

**작업 내역 (UI)**:
1. `SiteSettings.jsx` - `ProductConfig`에 수집 모드 선택기 추가
   - 단일 매장 (🏪): 등록된 URL의 특정 매장만 수집
   - 도메인 전체 (🌐): 도메인 내 여러 매장을 탐색하여 수집
2. 모드별 조건부 섹션 표시:
   - 단일 매장: "상품 상세 수집" 섹션만 표시
   - 도메인 전체: "매장 수집" + "상품 상세 수집" 양쪽 표시
3. 라벨 개선: "수집 건수" → "수집 범위", "상품 수집" → "상품 상세 수집"
4. 각 섹션에 설명 문구 추가 (`.config-section-desc`)
5. `App.css` - `.crawl-mode-selector`, `.crawl-mode-option`, `.crawl-mode-content` 등 카드 선택 스타일

**작업 내역 (Agent)**:
1. `agents/product/engine.py`:
   - `_normalize_config()` 추가: UI 필드 → Agent 내부 필드 변환
     - `crawl_mode` → single/domain 분기
     - `store_limit_type/count` → `max_stores`
     - `product_limit_type/count` → `collect_details`, `max_detail_pages`
   - `run_site()` 리팩토링 → `_run_single_mode()` / `_run_domain_mode()` 분기
   - `_run_domain_mode()` 신규: 도메인 홈 → 매장 탐색 → 매장별 반복 수집
   - `_discover_stores()` 신규: 규칙 기반 매장 링크 탐색 (JavaScript)
   - `_crawl_details()` 수정: `max_detail_pages=0` 이면 전체 수집

2. `agents/news/engine.py`:
   - `_normalize_config()` 추가: 기본값 적용 + 타입 보정 (문자열→정수)

3. `agents/cafe/engine.py`:
   - `_normalize_config()` 추가: 기본값 적용 + 빈 문자열 날짜 → None 변환

4. `core/base_agent.py`:
   - `get_crawl_config()` docstring 업데이트 (UI 변환 설명 추가)

**수정된 파일**: `web/frontend/src/pages/SiteSettings.jsx`, `web/frontend/src/App.css`, `agents/product/engine.py`, `agents/news/engine.py`, `agents/cafe/engine.py`, `core/base_agent.py`

**검증**: 3개 Agent 모두 import 성공, `_normalize_config()` 변환 테스트 통과

---

### Phase 8. 사이트 추가 시 카테고리-에이전트 자동 매핑
> 사용자가 에이전트 유형을 몰라도 카테고리만 선택하면 자동 결정

**사용자 요청**: 새 URL 추가할 때 카테고리와 에이전트 유형을 맞춰줘 (사용자는 어떤 Agent를 실행할지 모르기 때문에)

**작업 내역**:
1. `SiteSettings.jsx` - `AddSiteModal` 수정:
   - `agentTypeFromCategory()` 함수 추가: 카테고리명 → 에이전트 유형 자동 결정
     - `뉴스` → `news`
     - `카페` → `cafe`
     - 나머지 → `product`
   - 카테고리 변경 시 에이전트 유형 자동 반영 (`handleCategoryChange`)
   - 직접 입력 시에도 자동 반영 (`handleCustomCatChange`)
   - 에이전트 유형 드롭다운 제거 → 읽기 전용 badge 표시 + "카테고리에 따라 자동 설정됩니다" 안내
   - 확인 다이얼로그에 수집 유형 표시 추가
2. `App.css` - `.agent-type-badge-row` 스타일 추가
3. 미사용 `AGENT_TYPES` 상수 제거

**수정된 파일**: `web/frontend/src/pages/SiteSettings.jsx`, `web/frontend/src/App.css`

**카테고리 → 에이전트 매핑 규칙**:
| 카테고리 | 에이전트 유형 | 수집 대상 |
|---------|-------------|----------|
| 뉴스 | news | 뉴스 기사 |
| 카페 | cafe | 카페 게시글 |
| 트렌드매장, 경쟁사, 브랜드공식, 네이버스토어, 당사온라인몰 등 | product | 상품 정보 |

---

## UI ↔ Agent Config 맵핑

### Product Agent
| UI 필드 | Agent 내부 필드 | 변환 |
|---------|----------------|------|
| `crawl_mode='single'` | `crawl_mode='single'` | 단일 매장 모드 (기존 동작) |
| `crawl_mode='domain'` | `crawl_mode='domain'` | 도메인 전체 모드 (매장 탐색) |
| `store_limit_type='all'` | `max_stores=0` | 전체 매장 수집 |
| `store_limit_type='n'`, `store_limit_count=N` | `max_stores=N` | N개 매장 제한 |
| `product_limit_type='all'` | `collect_details=True`, `max_detail_pages=0` | 전체 상품 상세 수집 |
| `product_limit_type='n'`, `product_limit_count=N` | `collect_details=True`, `max_detail_pages=N` | N건 상세 수집 |

### News Agent
| UI 필드 | Agent 필드 | 비고 |
|---------|-----------|------|
| `max_articles_per_keyword` | `max_articles_per_keyword` | 동일 |
| `collect_body` | `collect_body` | 동일 |
| DB `news_keywords` | Agent가 DB 직접 조회 | 동일 |

### Cafe Agent
| UI 필드 | Agent 필드 | 비고 |
|---------|-----------|------|
| `date_from` | `date_from` | 동일 |
| `date_to` | `date_to` | 동일 |
| `collect_body` | `collect_body` | 동일 |
| `collect_links` | `collect_links` | 동일 |
| `collect_images` | `collect_images` | 동일 |
| `collect_ocr` | `collect_ocr` | 동일 |

## 기술 스택
- Backend: FastAPI + uvicorn (port 8000)
- Frontend: React 18 + Vite (port 5173, proxy → 8000)
- DB: SQLite (`data/crawling.db`) via `core.db.CrawlDB`
- Python venv: `D:\crawling\.venv\Scripts\python.exe`

## 실행 방법
```bash
python web/start_web.py
# 브라우저: http://localhost:5173
```

## 수정된 파일 전체 목록

### 백엔드
| 파일 | 설명 |
|------|------|
| `web/backend/app.py` | FastAPI 메인 앱, CORS, 라우터 등록 |
| `web/backend/routes/sites.py` | 사이트 CRUD, 키워드, 스케줄, 크롤링 실행 API |
| `web/backend/routes/results.py` | 수집 결과 조회, 대시보드 통계 API |
| `web/backend/routes/ocr.py` | OCR 사용 이력 API |

### 프론트엔드
| 파일 | 설명 |
|------|------|
| `web/frontend/src/App.jsx` | 라우터 설정 |
| `web/frontend/src/App.css` | 전역 스타일 (CSS Variables) |
| `web/frontend/src/pages/Dashboard.jsx` | 대시보드 페이지 |
| `web/frontend/src/pages/SiteSettings.jsx` | 수집 대상 설정 (메인 관리 페이지) |
| `web/frontend/src/pages/CrawlResults.jsx` | 수집 결과 조회 페이지 |
| `web/frontend/src/pages/OcrUsage.jsx` | OCR 사용 이력 페이지 |
| `web/frontend/src/components/Layout.jsx` | 사이드바 + 컨텐츠 레이아웃 |
| `web/frontend/src/components/StatCard.jsx` | 통계 카드 컴포넌트 |

### Agent
| 파일 | 설명 |
|------|------|
| `core/base_agent.py` | BaseAgent 추상 클래스 (docstring 업데이트) |
| `agents/product/engine.py` | ProductAgent (`_normalize_config`, 단일/도메인 모드 분기, 매장 탐색) |
| `agents/news/engine.py` | NewsAgent (`_normalize_config` 추가) |
| `agents/cafe/engine.py` | CafeAgent (`_normalize_config` 추가) |

### 문서
| 파일 | 설명 |
|------|------|
| `CLAUDE.md` | AI 개발 가이드 (바이브코딩 협업용, 프로젝트 루트) |
| `web/PROGRESS.md` | 프로젝트 진행사항 기록 |
| `web/UI_DESIGN.md` | 웹 대시보드 UI 설계 문서 |
| `web/AGENT_DESIGN.md` | Agent 아키텍처 설계 문서 |
| `web/ANTI_BOT.md` | 봇 차단 대응 기술 문서 |

---

### Phase 9. 봇 차단 대응 기술 문서화
> 봇 차단 우회 기술 5계층 구조를 문서로 정리

**사용자 요청**: bot 차단 기술을 적용한 사항들도 .md 파일에 남겨줘

**작업 내역**:
1. `web/ANTI_BOT.md` - 봇 차단 대응 기술 문서 신규 작성
   - **Layer 1: Stealth 브라우저** — `playwright_stealth` 기반 자동화 탐지 우회
     - WebDriver 속성 은닉, Chrome DevTools Protocol 감지 우회
     - `--disable-blink-features=AutomationControlled` 플래그
     - navigator.languages/platform 한국어 환경 설정
   - **Layer 2: HTTP 헤더 위장** — 실제 Chrome 125와 동일한 헤더 구성
     - User-Agent, Client Hints (Sec-Ch-Ua), Fetch Metadata (Sec-Fetch-*)
     - Accept-Language 한국어 설정, 로케일/시간대 (ko-KR, Asia/Seoul)
   - **Layer 3: 인간형 행동 시뮬레이션** — 정규분포 기반 가변 딜레이
     - `_human_delay()`: 평균 3.5초 정규분포 (1.5~8초)
     - `_human_scroll()`: 3단계 점진적 스크롤 + 20% 역스크롤 + 가변 정지
     - `_human_dwell()`: 2~5초 체류 + 마우스 이동 시뮬레이션
   - **Layer 4: 적응형 백오프** — 429/503 대응 지수 백오프
     - 기본 120초 → 지수 증가 (최대 600초) + ±30% 지터
     - 도메인별 레이트 리밋 상태 추적 (연속 429 카운터)
     - 선제적 대기: 최근 429 이력 도메인 접속 시 30~120초 쿨다운
   - **Layer 5: 쿠키 영속화 + 네트워크 최적화**
     - 도메인별 쿠키 파일 저장/로드 (재방문 사용자 인식)
     - Referer 체인 (자연스러운 내비게이션 경로 시뮬레이션)
     - 불필요 리소스(font, media) 차단, 트래킹 서비스 필터링

**생성된 파일**: `web/ANTI_BOT.md`

---

### Phase 10. UI 설계 문서 + Agent 설계 문서 정리
> 프로젝트 전체 설계 문서를 체계적으로 정리

**사용자 요청**: 크롤링 관리 웹 대시보드 설계 시 진행한 사항을 UI설계문서로, agent 설계 시 진행한 설계 내용을 agent 설계 문서로 .md 파일로 만들어줘

**작업 내역**:

1. `web/UI_DESIGN.md` - **UI 설계 문서 신규 작성**
   - 시스템 구성도 (React + FastAPI + SQLite)
   - 기술 스택 선정 이유
   - 디렉토리 구조 (backend/frontend 전체)
   - 라우팅 구조 (4개 페이지)
   - 레이아웃 설계 (사이드바 + 메인 컨텐츠)
   - 페이지별 UI 설계 (6개 섹션):
     - 대시보드: 통계 카드 + 카테고리별 현황 + 최근 이력
     - 수집 대상 설정: 실행 바 + 카테고리 필터 + 그룹 테이블
     - 설정 모달: Product(수집 모드 카드), News(키워드 칩), Cafe(날짜+토글)
     - 사이트 추가: 카테고리→에이전트 자동 매핑
     - 수집 결과: 에이전트별 상세 뷰 (Product/News/Cafe)
     - OCR 사용 이력: 통계 카드 + 차트(PieChart/BarChart) + 상세 테이블
   - 공통 컴포넌트 (ConfirmModal, StatCard, Badge, Toggle)
   - 카테고리 시스템 (10개 카테고리, 아이콘/색상/에이전트 매핑)
   - API 엔드포인트 전체 목록 (5개 그룹, 20+ 엔드포인트)
   - 스타일 설계 (CSS Variables, 30+ CSS 클래스)
   - 설계 원칙 (7개)

2. `web/AGENT_DESIGN.md` - **Agent 설계 문서 전면 재작성**
   - 기존 내용 유지 + 누락 내용 보강
   - 에이전트 레지스트리 코드 추가
   - 실행 흐름 (CLI / Web UI) 상세화
   - 설계 원칙 6개 테이블로 정리
   - _normalize_config() 패턴 설명 추가
   - ProductAgent 수집 모드 상세 (단일/도메인 각각 설명)
   - 플랫폼 감지 프레임워크별 테이블
   - 추출 전략 선택 흐름 추가
   - 상품 목록 수집 방식 3가지 비교
   - NewsAgent/CafeAgent _normalize_config() 코드 포함
   - 관련 문서 링크 (UI_DESIGN.md, ANTI_BOT.md, PROGRESS.md)

**생성/수정된 파일**:
- `web/UI_DESIGN.md` (신규)
- `web/AGENT_DESIGN.md` (전면 재작성)

---

### Phase 11. 바이브코딩 협업 체계 구축
> CLAUDE.md + .gitignore 생성으로 2인 협업 시 설계 일관성 유지

**사용자 요청**: 2명이 git으로 바이브코딩 협업 시, 서로 다른 prompt로 개발해도 설계 사상이 유지되려면 어떻게 해야 하는가?

**문제 분석**:
- AI는 매 세션마다 기억이 초기화됨
- 개발자마다 다른 프롬프트 → AI가 기존 설계를 모르고 새 방식으로 구현
- 결과: 스타일 불일치, 패턴 불일치, 구조 파괴

**해결 방안**:
- `CLAUDE.md` — 프로젝트 루트에 AI 개발 가이드 배치
- Claude Code는 세션 시작 시 이 파일을 자동으로 읽음
- 팀원 모두 동일한 컨텍스트에서 AI와 작업하게 됨

**작업 내역**:
1. `CLAUDE.md` - AI 개발 가이드 신규 작성
   - 설계 원칙 (절대 규칙 4개 + 아키텍처 규칙 5개)
   - 기술 스택 (변경 전 합의 필요 항목)
   - 디렉토리 구조 (파일 위치 규칙)
   - 코딩 컨벤션 (Python/React/CSS)
   - 에이전트 개발 패턴 (체크리스트 + 봇 차단 필수 패턴)
   - UI 개발 패턴 (ConfirmModal, 카테고리 매핑, 모달 분기)
   - API 규칙 (접두사, 라우트 순서, DB 관리)
   - 설계 문서 위치 안내
   - 작업 완료 후 체크리스트
2. `.gitignore` - Git 관리 제외 파일 설정
   - Python (.venv, __pycache__, *.pyc)
   - Node (node_modules, dist)
   - 데이터 (data/, output/, *.db)
   - IDE (.idea, .vscode)
   - 환경 변수 (.env)

**생성된 파일**:
- `CLAUDE.md` (프로젝트 루트)
- `.gitignore` (프로젝트 루트)

---

### Phase 12. 수집 결과 UI 개선 + 전체 사이트 일괄 실행
> CrawlResults 상세 뷰 개선 + run_all_10.py 일괄 실행

**사용자 요청**: 전체 29개 사이트 일괄 실행 + 수집 결과 UI에서 매장정보/상품정보 확인

**작업 내역**:
1. `run_all_10.py` - 전체 사이트 10건 제한 일괄 실행 스크립트
   - 스레딩 기반 병렬 실행 (독립 DB 연결)
   - Per-site 타임아웃 (product:300s, news:180s, cafe:600s)
   - Config 백업/복원 (crash recovery)
   - 실행 결과: 22 성공, 4 타임아웃, 3 이벤트(구조 불일치)

2. `web/frontend/src/pages/CrawlResults.jsx` - 상세 뷰 개선
   - ProductDetail: store_info 카드 (로고+이름+설명+메타) 추가
   - 상품 필드 매핑 헬퍼: getName/getBrand/getPrice/getOrigPrice/getImage/getUrl
   - 다중 필드명 지원 (product_name|name|title, selling_price|price|sale_price 등)
   - 이미지 썸네일(40x40) + 상품 URL 링크 추가
   - 가격 40자 초과 시 DOM 오염으로 판단 → '-' 표시

3. `web/frontend/src/App.css` - store-info-card 스타일 추가

**생성/수정된 파일**:
- `run_all_10.py` (신규)
- `web/frontend/src/pages/CrawlResults.jsx` (수정)
- `web/frontend/src/App.css` (수정)

---

### Phase 13. Promotion Agent 신규 구현
> 경쟁사 이벤트 수집용 독립 에이전트 타입 분리

**사용자 요청**: 경쟁사 이벤트(롯데/신라/현대 면세점)는 상품 수집과 완전히 다른 구조.
이벤트 목록 → 이벤트 상세 → 이벤트 내 상품(선택)의 3단계 계층 수집 필요.
ProductAgent에서 PromotionAgent를 분리해야 함.

**설계 분석**:
- 상품 Agent: 매장 → 상품 목록 (2단계)
- 프로모션 Agent: 이벤트 목록 → 이벤트 상세 → 이벤트 내 상품 (3단계)
- 이벤트에 상품이 포함되지 않을 수 있음 (선택 데이터)
- 범용 DOM 분석 + 네트워크 인터셉트 + 링크 패턴 3단계 fallback 전략

**작업 내역**:
1. `agents/promotion/__init__.py` - 패키지 초기화
2. `agents/promotion/engine.py` - PromotionAgent 구현
   - BaseAgent 상속, agent_type = 'promotion'
   - _normalize_config(): UI→Agent 필드 변환 (event_limit, collect_details, etc.)
   - _run_event_collection(): 이벤트 수집 파이프라인
   - _collect_event_list(): 범용 DOM 분석으로 이벤트 카드 탐지
   - _try_network_event_extraction(): API 응답에서 이벤트 JSON 탐지 (fallback)
   - _try_link_pattern_extraction(): 이벤트 URL 패턴 링크 수집 (fallback 2)
   - _collect_event_details(): 이벤트 상세 페이지 방문
   - _collect_event_products(): 이벤트 내 상품 수집 (선택)
   - _parse_event_dates(): 날짜 텍스트 파싱
   - _is_event_active(): 이벤트 상태 판별
   - _save_json(): events.json + crawl_result.json 저장

3. `agents/__init__.py` - AGENT_REGISTRY에 promotion 등록
   - PromotionAgent import + 'promotion' 키 추가

4. DB 업데이트: 이벤트 사이트 3개의 agent_type 변경
   - [18] 롯데면세점 이벤트: product → promotion
   - [19] 신라면세점 이벤트: product → promotion
   - [20] 현대면세점 이벤트: product → promotion

5. `web/frontend/src/pages/SiteSettings.jsx` - 프로모션 UI 추가
   - agentTypeFromCategory(): '경쟁사이벤트' → 'promotion' 매핑
   - AGENT_TYPE_LABELS에 'promotion: 이벤트 수집' 추가
   - ConfigModal: promotion 분기 추가
   - PromotionConfig 컴포넌트 신규 구현
     - 이벤트 수집 범위 (전체/건수 지정)
     - 이벤트 상태 필터 (전체/진행 중)
     - 상세 수집/상품 수집 토글
   - 에이전트 배지 스타일 분기 (promo)

6. `web/frontend/src/pages/CrawlResults.jsx` - 이벤트 결과 뷰 추가
   - AGENT_LABELS에 promotion 추가
   - ExpandedDetail에 promotion 분기 추가
   - PromotionDetail 컴포넌트 신규 구현
     - 사이트 정보 카드
     - 요약 통계 (이벤트 수, 상세 수집, 상품 포함, 총 상품)
     - 이벤트 목록 테이블 (이미지, 이벤트명, 기간, 상태, 상품 수)
     - 이벤트 클릭 시 상세 확장 (내용, 혜택, 이벤트 내 상품 테이블)

7. `web/frontend/src/App.css` - .badge.promo 스타일 추가

8. `web/AGENT_DESIGN.md` - Promotion Agent 설계 문서 추가
   - 수집 파이프라인 다이어그램
   - _normalize_config() 변환 규칙
   - crawl_config 필드 정의
   - 이벤트 데이터 구조 (JSON 스키마)
   - 이벤트 수집 전략 3단계 설명
   - 대상 사이트 목록

**생성된 파일**:
- `agents/promotion/__init__.py`
- `agents/promotion/engine.py`

**수정된 파일**:
- `agents/__init__.py`
- `web/frontend/src/pages/SiteSettings.jsx`
- `web/frontend/src/pages/CrawlResults.jsx`
- `web/frontend/src/App.css`
- `web/AGENT_DESIGN.md`
- `data/crawling.db` (agent_type 변경)

---

### Phase 14. v2 에이전트 아키텍처 재설계
> 기존 ProductAgent 삭제 → 수집 패턴 기반 3개 Collector 에이전트로 재설계

**사용자 요청**:
- 기존 ProductAgent 삭제하고 새로 설계
- 7개 비즈니스 카테고리(트렌드, 경쟁사면세점, 브랜드공식, 네이버스토어, 중국경쟁사, 경쟁사배너, 브랜드목록)에 대한 수집 에이전트 아키텍처 설계
- 사이트별 에이전트 vs 통합 에이전트 결정
- UI에서 URL별 수집항목 설정 기능 필요

**설계 분석 및 결정**:

아키텍처 선택지 4가지 비교 후, **수집 패턴 기반 3-에이전트** 구조 채택:
- 사이트별(20+개) → CLAUDE.md "하드코딩 금지" 위반 → 기각
- 단일 통합(1개) → 배너 캡처와 상품 수집은 완전히 다른 패턴 → 기각
- 카테고리별(7개) → 상품 수집 5개가 동일 패턴인데 과잉 분리 → 기각
- **수집 패턴별(3개)** → 자연스러운 분리 + config 구동으로 카테고리 대응 → **채택**

**새 에이전트 구조**:

| 에이전트 | 파일 | 담당 카테고리 | 수집 패턴 |
|---------|------|-------------|----------|
| ProductCollector | `agents/product/engine.py` | 트렌드, 경쟁사, 브랜드공식, 네이버스토어, 중국경쟁사 | URL → 상품 카드 탐색 → 필드 추출 |
| BannerCollector | `agents/banner/engine.py` | 경쟁사배너 | URL → 배너 영역 식별 → 이미지/텍스트 캡처 |
| DirectoryCollector | `agents/directory/engine.py` | 브랜드목록 | URL → 목록 구조 탐색 → 항목 메타데이터 추출 |

**핵심 설계 사상**:
1. **Config 구동**: 사이트별 차이를 코드가 아닌 URL별 crawl_config으로 관리
2. **카테고리 기본 템플릿**: 사이트 등록 시 카테고리에 따라 기본 config 자동 적용
3. **기존 인프라 재활용**: BaseAgent, BrowserManager, RuleAnalyzer 등 공통 인프라 유지
4. **기존 에이전트 유지**: NewsAgent, CafeAgent, PromotionAgent는 변경 없음

**작업 내역**:
1. `web/AGENT_DESIGN.md` - v2 아키텍처 설계 추가
   - 섹션 15: 설계 배경, 아키텍처 선택지 분석, 3개 에이전트 상세 설계
   - 각 에이전트별: 수집 파이프라인, crawl_config 스키마, 데이터 스키마
   - Config 구동 설계: 카테고리 기본 템플릿, URL별 커스터마이징
   - UI 변경 방향, DB 변경 사항, 구현 순서 계획
   - 기존 ProductAgent v1 섹션은 아카이브 처리

**수정된 파일**:
- `web/AGENT_DESIGN.md` (v2 아키텍처 설계 추가 + ProductAgent v1 아카이브)
- `web/PROGRESS.md` (Phase 14 기록)

**다음 단계**: 설계 확정 후 1단계(기존 ProductAgent 삭제 + ProductCollector 기본 구현)부터 착수

---

### Phase 14-1. v2 에이전트 UI 설정 모달 구현
> ProductConfig 개편 + BannerConfig/DirectoryConfig 신규 추가

**사용자 요청**: UI에서 목적에 맞는 수집 설정을 추가 — 매장정보, 매장건수, 상품 상세정보, 수집건수, 배너 정보, 프로모션 정보 등 기존 ProductAgent에서 진행했던 수집 항목 설정

**작업 내역**:

1. `SiteSettings.jsx` - **ProductConfig v2로 전면 교체**
   - 수집 필드 체크박스: 기본(상품명/가격/브랜드/이미지) + 추가(순위/원가/할인율/사은품/레퍼런스번호/카테고리)
   - 목록 유형 카드 선택: 랭킹 / 카탈로그 / 검색
   - 페이지네이션 방식: 무한 스크롤 / 페이지 클릭 / API / 단일 페이지
   - 수집 범위: 최대 수집 건수(전체/건수), 최대 페이지 수
   - 상품 상세 수집 토글 (상세 페이지 진입)

2. `SiteSettings.jsx` - **BannerConfig 컴포넌트 신규 추가**
   - 배너 영역 선택: 히어로 배너 / 서브 배너 / 팝업
   - 수집 옵션: 스크린샷 캡처, 이미지 다운로드, 배너 텍스트 수집 토글
   - 슬라이더 설정: 최대 슬라이드 수

3. `SiteSettings.jsx` - **DirectoryConfig 컴포넌트 신규 추가**
   - 목록 유형 카드: 브랜드 디렉토리 / 이벤트 목록
   - 수집 필드 체크박스: 이름, 카테고리, 설명, 기간, 상태, 상세 URL
   - 수집 옵션: 인덱스 탐색(A~Z) 토글, 상세 진입 토글
   - 수집 범위: 최대 항목 수(전체/건수)

4. `SiteSettings.jsx` - **에이전트 매핑 확장**
   - `CATEGORY_LABELS`에 '경쟁사배너', '브랜드목록' 추가
   - `agentTypeFromCategory()`에 banner/directory 매핑 추가
   - `AGENT_TYPE_LABELS`에 '배너 수집', '목록 수집' 추가
   - `AGENT_BADGE_CLASS` 통합 매핑 객체로 배지 스타일 관리
   - ConfigModal에 banner/directory 분기 추가

5. `App.css` - **새 UI 스타일 추가**
   - `.badge.banner-badge`, `.badge.dir-badge` 배지 스타일
   - `.field-checkbox-grid`, `.field-checkbox`, `.field-group-label` 수집 필드 체크박스 그리드
   - `.list-type-options`, `.list-type-option`, `.list-type-icon` 목록 유형 카드 선택

**수정된 파일**:
- `web/frontend/src/pages/SiteSettings.jsx`
- `web/frontend/src/App.css`

---

### Phase 14-2. ProductAgent v2 구현
> 기존 ProductAgent 전면 교체 — Config 구동 + 3단계 페이지 분석

**사용자 요청**: 위에 설계된 v2 아키텍처 내용으로 product agent 코드를 수정

**설계 변경점 (v1 → v2)**:
- v1: 플랫폼 감지(Cafe24/Shopify/...) → 추출 전략 선택(state_var/dom/api) — 2단계
- v2: 페이지 구조 직접 분석(API → JS전역변수 → DOM) — 1단계, 플랫폼 무관
- v1: 수집 모드(단일/도메인) 기반 분기
- v2: UI crawl_config(collect_fields/pagination/max_items) 구동

**작업 내역**:

1. `agents/product/engine.py` - **전면 재작성 (~815 lines)**
   - `_FIELD_ALIASES`: 12개 표준 필드 × 80+ 별칭 이름 매핑
     - name, price, brand, image (기본), rank, original_price, discount_rate, gift, reference_no, category, product_url, product_id
   - `_normalize_config()`: UI→Agent 필드 변환
     - collect_fields, optional_fields, list_type, pagination, max_pages, max_items, detail_page
     - item_limit_type='all' → max_items=0 변환
   - `run_site()`: 6단계 파이프라인
     1. 브라우저 시작 + NetworkInterceptor 캡처 + _safe_goto
     2. 페이지 구조 분석 (_detect_page_structure)
     3. 상품 목록 수집 (_collect_products)
     4. 상품 상세 수집 (_collect_details, 선택)
     5. 필드 정규화 + 필터링 (_normalize_products)
     6. DB 저장 + JSON 파일 저장
   - `_detect_page_structure()`: 3단계 폴백 탐지
     - `_try_api_detection()`: NetworkInterceptor 캡처 데이터에서 상품 JSON 배열 탐색
     - `_try_state_var_detection()`: __NEXT_DATA__, __PRELOADED_STATE__ 등 JS 전역변수
     - `_try_dom_detection()`: 가격 패턴 요소 → 카드 조상 → 그리드 부모 역추적
   - `_collect_products()`: 페이지네이션 방식별 분기
     - `_paginate_scroll()`: 무한 스크롤 (scrollTo + 재추출 + 중복 제거)
     - `_paginate_click()`: 다음 버튼 탐색 (7개 selector 패턴) + 클릭
     - `_paginate_api()`: API URL 페이지 파라미터 증분 + fetch
     - `none`: 초기 탐지 결과만 반환
   - `_collect_details()`: 상품 URL 접속 → description + detail_images 추출
   - `_normalize_products()`: _FIELD_ALIASES 기반 필드명 정규화 + collect_fields 필터링 + rank/collected_at 부여
   - `_save_json()`: products.json + crawl_result.json (agent_version="v2")

2. JS 스니펫 3개
   - `_JS_FIND_STATE_PRODUCTS`: 전역변수 재귀 탐색, isProductLike 판별, 최다 배열 반환
   - `_JS_FIND_DOM_PRODUCTS`: 가격 정규식 → 가격 요소 수집 → 카드 조상 역추적 → TreeWalker 텍스트 추출
   - `_JS_EXTRACT_DETAIL`: meta description + detail 영역 이미지 수집

3. 유틸리티 함수 7개
   - `_find_product_array()`: JSON 재귀 탐색으로 상품 배열 찾기
   - `_looks_like_product()`: 객체 키에 name+price 패턴 확인
   - `_product_key()`: 상품 중복 판별 키 생성 (product_id 우선)
   - `_build_seen_set()`: 중복 방지 set 구축
   - `_resolve_product_url()`: 상대/절대 URL 통합 처리
   - `_increment_page_param()`: API URL 페이지 파라미터 증분 (offset 계산 포함)
   - `_js_escape()`: JS 문자열 이스케이프

**v1에서 제거된 것**:
- 플랫폼 감지 로직 (Cafe24, Shopify 등)
- strategies/ 연동 코드
- 수집 모드(단일/도메인) 분기

**유지된 것**:
- BaseAgent 상속 + AGENT_REGISTRY 등록 (클래스명 ProductAgent 유지)
- agent_type = "product" 
- 봇 차단 대응 패턴 (_safe_goto → _is_blocked → _human_dwell → _human_scroll)
- NetworkInterceptor 활용

**수정된 파일**:
- `agents/product/engine.py` (전면 재작성)

---

### Phase 14-3. BannerCollector + DirectoryCollector 구현
> v2 아키텍처의 나머지 2개 에이전트 구현 + 결과 상세 뷰 추가

**사용자 요청**: 설계된 v2 아키텍처대로 전체 개발 진행

**작업 내역**:

1. `agents/banner/__init__.py` - 패키지 초기화
2. `agents/banner/engine.py` - **BannerAgent 구현 (~340 lines)**
   - BaseAgent 상속, agent_type = 'banner'
   - `_normalize_config()`: banner_areas, capture_screenshot, download_images, include_text, max_slides
   - `run_site()`: 6단계 파이프라인
     1. 브라우저 시작 + _safe_goto
     2. 팝업 닫기 (_close_popups)
     3. 배너 영역 탐지 + 수집 (_collect_banners)
     4. 스크린샷 캡처 (_capture_banner_screenshots)
     5. 이미지 다운로드 (_download_banner_images)
     6. DB + JSON 저장
   - `_collect_banners()`: JS로 배너 영역 탐지 후 area_type별 수집
   - `_collect_slider_banners()`: 슬라이더 다음 버튼 클릭으로 슬라이드 순회, 이미지 중복 제거
   - `_extract_current_slide()`: 활성 슬라이드에서 이미지/텍스트/링크 추출
   - JS 스니펫 2개:
     - `_JS_DETECT_BANNER_AREAS`: 슬라이더(swiper/slick) + 히어로 + 서브 배너 탐지
     - `_JS_EXTRACT_SLIDE`: 현재 활성 슬라이드 데이터 추출 (배경 이미지 폴백 포함)

3. `agents/directory/__init__.py` - 패키지 초기화
4. `agents/directory/engine.py` - **DirectoryAgent 구현 (~430 lines)**
   - BaseAgent 상속, agent_type = 'directory'
   - `_normalize_config()`: collect_fields, list_type, collect_details, index_navigation, max_items
   - `run_site()`: 6단계 파이프라인
     1. 브라우저 시작 + NetworkInterceptor 캡처 + _safe_goto
     2. 인덱스 순회 or 단일 페이지 수집 분기
     3. (선택) 상세 수집
     4. max_items 제한 + 타임스탬프
     5. DB + JSON 저장
   - `_collect_by_index()`: A~Z/ㄱ~ㅎ 인덱스 탭 순회 수집
   - `_collect_single_page()`: API 우선 → DOM 폴백
   - `_try_api_extraction()`: 네트워크 캡처에서 목록 JSON 탐색
   - `_extract_list_items()`: DOM에서 브랜드/이벤트 목록 추출
   - `_collect_item_details()`: 항목별 상세 페이지 방문
   - JS 스니펫 3개:
     - `_JS_DETECT_INDEX_TABS`: 알파벳/가나다 인덱스 탭 탐지 (CSS 셀렉터 빌더 포함)
     - `_JS_EXTRACT_LIST_ITEMS`: 브랜드 목록 / 이벤트 목록 분기 추출
     - `_JS_EXTRACT_ITEM_DETAIL`: 상세 페이지 description/period/status 추출

5. `agents/__init__.py` - **AGENT_REGISTRY 업데이트**
   - banner → BannerAgent, directory → DirectoryAgent 추가
   - 총 6개 에이전트 등록: product, news, cafe, promotion, banner, directory

6. `web/frontend/src/pages/CrawlResults.jsx` - **결과 상세 뷰 추가**
   - AGENT_LABELS에 banner:'배너 수집', directory:'목록 수집' 추가
   - ExpandedDetail에 banner/directory 분기 추가
   - BannerDetail 컴포넌트: 영역별 요약 통계 + 배너 카드 그리드 (이미지/텍스트/링크/크기)
   - DirectoryDetail 컴포넌트: 항목 테이블 (인덱스/이름/카테고리/기간/상태/상세)

7. `web/frontend/src/App.css` - **배너 결과 카드 스타일 추가**
   - `.banner-grid` (auto-fill 그리드), `.banner-card`, `.banner-card-header/image/text/meta`

**생성된 파일**:
- `agents/banner/__init__.py`
- `agents/banner/engine.py`
- `agents/directory/__init__.py`
- `agents/directory/engine.py`

**수정된 파일**:
- `agents/__init__.py`
- `web/frontend/src/pages/CrawlResults.jsx`
- `web/frontend/src/App.css`

---

### Phase 14-4. 사이트 등록 UI 개선 — 수집 항목 선택
> AddSiteModal에 카테고리별 수집 항목 체크박스 추가

**사용자 요청**: 사이트 등록 시 수집 가능한 정보를 표시하고, 사용자가 수집하고자 하는 항목을 선택하게끔 UI 변경. 기존 등록 정보는 체크된 상태 유지.

**작업 내역**:

1. `SiteSettings.jsx` - **AddSiteModal 전면 개편**
   - `CATEGORY_DEFAULT_CONFIGS`: 카테고리별 기본 crawl_config 템플릿 (9개 카테고리)
     - 트렌드매장, 경쟁사, 브랜드공식, 네이버스토어, 경쟁사중국, 트렌드Global매장, 당사온라인몰, 경쟁사배너, 브랜드목록
   - `COLLECT_ITEMS_BY_AGENT`: 에이전트별 수집 가능 항목 정의
     - product: 10개 필드 (기본4+추가6) + 목록 유형 + 페이지네이션 + 옵션
     - banner: 3개 영역 + 3개 옵션
     - directory: 6개 필드 + 목록 유형 + 2개 옵션
   - `buildCheckedState()`: 카테고리 기본 config → 체크 상태 변환
   - `buildCrawlConfig()`: 체크 상태 → crawl_config 변환
   - AddSiteModal 동작 변경:
     - 카테고리 선택 시 → 에이전트 유형 자동 결정 + 기본 항목 체크
     - 수집 필드 체크박스 (기본/추가 구분, "기본" 배지 표시)
     - 목록 유형 칩 선택 (ranking/catalog/search 또는 brand_directory/event_list)
     - 페이지네이션 칩 선택 (scroll/click/api/none)
     - 수집 옵션 체크박스 (상세 수집, 스크린샷 등)
     - 저장 시 crawl_config을 form에 포함하여 API 전송

2. `App.css` - **수집 항목 선택 UI 스타일**
   - `.field-badge-basic`: 기본 필드 배지
   - `.add-site-chip`, `.add-site-chip.selected`: 선택 칩 (목록 유형/페이지네이션)
   - `.add-site-option-row`: 수집 옵션 체크박스 행

3. `data/crawling.db` - **사이트 데이터 마이그레이션**
   - 기존 product 사이트 23개 삭제
   - v2 카테고리 체계로 24개 사이트 재등록 (7개 카테고리, 각 crawl_config 포함)
   - 뉴스/카페/프로모션 6개 사이트 유지
   - 총 30개 사이트

**수정된 파일**:
- `web/frontend/src/pages/SiteSettings.jsx`
- `web/frontend/src/App.css`
- `data/crawling.db` (사이트 재등록)

---

### Phase 14-5. URL 자동 분석 기능
> 사이트 등록 시 URL을 방문하여 수집 가능한 데이터를 자동 탐지

**사용자 요청**: 사이트 등록 시 URL을 입력하면 해당 URL 기반으로 수집 가능한 정보를 먼저 가져오게 해달라. 지정한 정보 외에 어떤 정보들을 수집할 수 있는지 보고 사용자가 선택하고 싶다.

**작업 내역**:

1. `core/url_analyzer.py` - **URL 자동 분석 엔진** (신규)
   - `analyze_url(url, timeout_sec=30)`: 메인 분석 함수
   - Playwright Stealth 브라우저로 URL 방문
   - 3단계 상품 탐지: 네트워크 API → JS 전역변수 → DOM 패턴
   - 배너/슬라이더 영역 탐지 (`_detect_banners`)
   - 브랜드/이벤트 목록 구조 탐지 (`_detect_directory`)
   - `_extract_fields()`: 샘플 객체에서 필드 추출 (raw_key, label, standard_key, value_preview)
   - `_FIELD_LABELS`: 60+ 필드명 → 한국어 레이블 매핑
   - `_STANDARD_MAP`: 한국어 레이블 → 표준 키 매핑
   - 반환: status, page_title, products, banners, directory, discovered_fields, elapsed

2. `web/backend/routes/sites.py` - **분석 API 엔드포인트**
   - `POST /api/sites/analyze-url` 추가
   - `UrlAnalyzeRequest` Pydantic 모델
   - parameterized 경로 앞에 배치 (라우트 순서 규칙 준수)

3. `web/frontend/src/pages/SiteSettings.jsx` - **AddSiteModal URL 분석 통합**
   - URL 입력 옆 "URL 분석" 버튼 추가
   - `analyzing`, `analyzeResult`, `discoveredFields`, `discoveredChecked` 상태 추가
   - 분석 진행 중 프로그레스 바 + 안내 텍스트 표시
   - 분석 완료 시 결과 요약 (상품/배너/목록 탐지 수, 소요 시간)
   - 발견된 추가 필드를 "발견" 배지와 함께 체크박스로 표시
   - 기존 카테고리 기본 필드 중 분석 결과에 매칭되면 자동 체크
   - 발견된 추가 필드를 `extra_fields`로 crawl_config에 포함하여 저장
   - Enter 키로 URL 분석 트리거 지원

4. `web/frontend/src/App.css` - **URL 분석 UI 스타일**
   - `.url-analyze-row`, `.url-analyze-btn`: URL 입력 + 분석 버튼 레이아웃
   - `.url-analyze-spinner`: 로딩 스피너 애니메이션
   - `.url-analyze-progress`, `.url-analyze-progress-bar`, `.url-analyze-progress-fill`: 진행 바
   - `.url-analyze-result`, `.url-analyze-result.success`, `.url-analyze-result.error`: 결과 표시
   - `.url-analyze-tag.products/banners/directory`: 탐지 결과 태그
   - `.field-checkbox.discovered`, `.field-badge-discovered`: 발견 필드 스타일 (점선 테두리, 녹색 배지)

5. `web/frontend/src/pages/SiteSettings.jsx` - **기존 사이트 설정에도 URL 분석 적용**
   - `UrlAnalyzePanel` 공용 컴포넌트 추출: 분석 버튼 + 진행 바 + 결과 요약 + 발견 필드를 재사용 가능한 단일 컴포넌트로 통합
   - `openConfig()`에 `url: site.site_url` 추가: 설정 모달에서 URL 접근 가능
   - `ProductConfig`: UrlAnalyzePanel 통합 — 발견 필드 자동 체크 (basic/extra 구분) + extra_fields 저장
   - `BannerConfig`: UrlAnalyzePanel 통합 — 탐지된 배너 영역 자동 체크 + extra_fields 저장
   - `DirectoryConfig`: UrlAnalyzePanel 통합 — 탐지된 수집 필드 자동 체크 + 인덱스 탐색 자동 활성화 + extra_fields 저장

6. `agents/product/engine.py` - **ProductAgent UI 정합성 수정**
   - `_normalize_config()`: `collect_fields`/`optional_fields` 문자열→리스트 자동 변환, `extra_fields` 필드 지원
   - `_normalize_products()`: `extra_fields`의 `raw_key→standard_key` 매핑으로 추가 필드 추출, 중첩 키(`parent.child`) 지원

7. `agents/banner/engine.py` - **BannerAgent UI 정합성 수정**
   - `_normalize_config()`: `banner_areas` 문자열→리스트 자동 변환, `extra_fields` 필드 지원

8. `agents/directory/engine.py` - **DirectoryAgent UI 정합성 수정**
   - `_normalize_config()`: `collect_fields` 문자열→리스트 자동 변환, `extra_fields` 필드 지원
   - `_try_api_extraction()`: API 응답에서 `extra_fields`의 `raw_key`로 추가 필드 추출
   - `_filter_items()`: `collect_fields` + `extra_fields` 기준으로 항목 필드 필터링 (신규)
   - `run_site()`: 저장 전 `_filter_items()` 호출 추가

**수정된 파일**:
- `core/url_analyzer.py` (신규)
- `web/backend/routes/sites.py`
- `web/frontend/src/pages/SiteSettings.jsx`
- `web/frontend/src/App.css`
- `agents/product/engine.py`
- `agents/banner/engine.py`
- `agents/directory/engine.py`

---

### Phase 14-6. 설정 저장 버그 수정 + 에러 핸들링 강화
> URL 분석 후 저장한 추가 필드가 모달 재오픈 시 표시되지 않던 버그 수정

**사용자 요청**: 기존 등록한 URL에 대해서 URL 분석하여 수집 가능한 항목 조회를 했고, 수집 필드 변경 사항을 저장했으나 저장이 되지 않습니다.

**원인 분석**:
1. **표시 버그 (핵심)**: 저장은 실제로 DB에 정상 반영되고 있었으나, 모달을 다시 열면 `UrlAnalyzePanel`의 `discoveredFields` 상태가 빈 배열(`[]`)로 초기화되어 저장된 추가 필드(extra_fields)가 화면에 보이지 않음 → 사용자에게 저장 안 된 것처럼 보임
2. **초기화 버그**: `BannerConfig`/`DirectoryConfig`의 `extraFields` 상태가 `useState([])` 으로 하드코딩되어 있어, 이전에 저장된 `extra_fields`를 로드하지 않음
3. **에러 핸들링 부재**: 모든 설정 저장 함수에서 `fetch` 응답을 검사하지 않아, 서버 에러 시 사용자에게 아무런 피드백 없이 모달이 닫힘

**수정 내역**:

1. `SiteSettings.jsx` - `UrlAnalyzePanel` 컴포넌트
   - `savedExtraFields` prop 추가: 기존에 저장된 extra_fields를 전달받아 초기화
   - `discoveredFields` 초기값: `savedExtraFields`가 있으면 해당 데이터로 초기화
   - `discoveredChecked` 초기값: `savedExtraFields`의 항목을 모두 체크된 상태로 초기화
   - 라벨 분기: 분석 전이면 "📌 저장된 추가 수집 필드", 분석 후면 "🔍 URL 분석으로 발견된 추가 필드"
   - 배지 분기: 분석 전 "저장됨", 분석 후 "발견"

2. `SiteSettings.jsx` - `ProductConfig`, `BannerConfig`, `DirectoryConfig`
   - `UrlAnalyzePanel`에 `savedExtraFields` prop 전달
   - `BannerConfig`: `extraFields` 초기값을 `site.config.extra_fields || []`로 변경
   - `DirectoryConfig`: `extraFields` 초기값을 `site.config.extra_fields || []`로 변경

3. `SiteSettings.jsx` - 모든 설정 저장 함수 (6곳)
   - `ProductConfig.handleSave`: try/catch + res.ok 검사 + alert 피드백
   - `NewsConfig.handleSaveConfig`: 동일
   - `CafeConfig.handleSave`: 동일
   - `PromotionConfig.handleSave`: 동일
   - `BannerConfig.handleSave`: 동일
   - `DirectoryConfig.handleSave`: 동일
   - `AddSiteModal.handleSave`: 동일

**수정된 파일**:
- `web/frontend/src/pages/SiteSettings.jsx`

---

### Phase 15. 크롤링 로그 뷰어
> 크롤링 실행 로그를 파일에 저장하고, 웹에서 실시간 확인 가능하게 구현

**사용자 요청**: 크롤링 실행 후 진행 사항을 웹에서 확인하고 싶다. 로그를 볼 수 있나?

**문제 분석**:
- 크롤링 프로세스가 `stdout=subprocess.DEVNULL`로 실행되어 모든 출력이 버려지고 있음
- Agent의 `_log()` 함수가 `print()`만 호출하므로 로그 파일도 생성되지 않음
- 웹 UI에서는 실행 중/종료 여부만 확인 가능, 진행 상황 확인 불가

**작업 내역**:

1. `web/backend/routes/sites.py` - **로그 파일 저장 + 조회 API**
   - `_LOGS_DIR = logs/` 디렉토리 사용
   - `run_crawl()`: subprocess stdout을 `logs/crawl_{site_id}_{timestamp}.log` 파일로 리다이렉트
     - `python -u` 옵션으로 unbuffered stdout 보장
     - line-buffered 파일 쓰기로 실시간 로그 확인 가능
   - `crawl_status()`: 로그 파일 정보 포함, 종료 시 로그 핸들 자동 닫기
   - `GET /api/crawl/logs/{site_id}`: JSON 로그 조회 (tail 파라미터로 줄 수 제한)
   - `GET /api/crawl/logs/{site_id}/raw`: plain text 로그 (브라우저 직접 확인용)

2. `web/frontend/src/pages/SiteSettings.jsx` - **로그 뷰어 모달**
   - `LogViewerModal` 컴포넌트: 2초 간격 자동 새로고침, 터미널 스타일 다크 테마
   - 사이트 행에 📋 로그 보기 버튼 추가

3. `web/frontend/src/App.css` - **로그 뷰어 스타일**

**수정된 파일**:
- `web/backend/routes/sites.py`
- `web/frontend/src/pages/SiteSettings.jsx`
- `web/frontend/src/App.css`

---

### Phase 15-1. 크롤링 종료 기능
> 실행 중인 크롤링 프로세스를 웹에서 개별 중지

**사용자 요청**: agent 개별 실행 기능과 동일 영역에 agent 종료 기능 생성

**작업 내역**:

1. `web/backend/routes/sites.py` - **크롤링 종료 API**
   - `POST /api/crawl/stop` 엔드포인트 추가
   - Windows: `taskkill /F /T /PID` (자식 프로세스 포함 강제 종료)
   - 종료 시 로그에 중지 메시지 기록 + 핸들 닫기

2. `web/frontend/src/pages/SiteSettings.jsx` - **종료 버튼 UI**
   - `requestStopCrawl()`: ConfirmModal (danger 타입) → API 호출
   - 실행 버튼 영역 조건부 렌더링: 미실행=▶ 초록 / 실행 중=■ 빨강
   - 📋 로그 버튼은 항상 표시 유지

3. `web/frontend/src/App.css` - `.btn-stop` 스타일

**수정된 파일**:
- `web/backend/routes/sites.py`
- `web/frontend/src/pages/SiteSettings.jsx`
- `web/frontend/src/App.css`

---

### Phase 16. DOM 탐지 데이터 품질 개선
> 프로모션 배지가 상품명으로 잘못 추출되는 문제 수정

**사용자 요청**: 롯데면세점 수집 결과에서 상품명이 "세일", "핫세일", "사은품" 등 프로모션 태그로 표시되고, 브랜드·가격도 맞지 않는 문제 수정

**원인 분석**:
- `_JS_FIND_DOM_PRODUCTS`의 TreeWalker가 DOM 순서대로 `texts[0]`=name, `texts[1]`=brand로 매핑
- 이커머스 사이트는 카드 상단에 프로모션 배지("세일", "핫세일" 등)가 위치하여 실제 상품명보다 먼저 DOM에 등장
- 가격도 원가/판매가 구분 없이 순서대로 할당되어 뒤바뀜

**작업 내역**:

1. `agents/product/engine.py` - **`_JS_FIND_DOM_PRODUCTS` 전면 개선**
   - **Pass 1 빈도 분석**: 짧은 텍스트(≤10자)의 카드 간 출현 빈도 측정, 30%+ 반복 = 배지 자동 필터링
   - **클래스 기반 시멘틱 추출**: `NAME_CLS`/`BRAND_CLS` 정규식으로 클래스명 기반 필드 우선 탐색
   - **배지 클래스 필터링**: `BADGE_CLS` 정규식으로 배지 요소 텍스트 제외
   - **길이 우선 이름 선택**: 첫번째 텍스트 대신 가장 긴 텍스트를 상품명으로
   - **가격 원가/판매가 분류**: `<del>`/`<s>` 태그 + `ORIG_CLS` 클래스 컨텍스트, 미판별 시 숫자 크기 비교
   - **javascript: URL 처리**: 8자리+ 숫자 추출 → `product_id`, URL 정리

**수정 결과** (롯데면세점 ID=35):
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| name | "세일", "핫세일" | "발렌타인 30년 700ml", "키엘 울트라 훼이셜 크림" |
| brand | "사은품", "베스트" | "발렌타인", "키엘", "설화수" |
| price | 원가/판매가 뒤바뀜 | 올바르게 분류 |
| product_id | 없음 | "20000842408" 등 추출 |

**수정된 파일**:
- `agents/product/engine.py` (`_JS_FIND_DOM_PRODUCTS` JS 스니펫)

---

### Phase 16-1. 상품 상세 수집 + product_details.json
> javascript: 링크 대응 카드 클릭 상세 수집 + 출력 파일 분리

**사용자 요청**: 롯데면세점 상품 상세 정보 수집이 안 되고, `product_details.json` 파일 필요

**원인 분석**:
- `_collect_details()`가 `product_url`로 상세 페이지 이동하는데, DOM 추출 시 `javascript:` 링크만 있어서 URL이 빈 문자열 → 모든 상품 skip
- `_save_json()`이 `products.json`과 `crawl_result.json`만 저장 (사실상 동일 데이터)

**작업 내역**:

1. `agents/product/engine.py` - **카드 클릭 기반 상세 수집**
   - `_JS_CLICK_CARD` JS 스니펫 추가: `product_id` 또는 `image URL`로 카드를 찾아 클릭
   - `_collect_details()` 개선: URL이 없을 때 카드 클릭 → 페이지 전환 대기 → 상세 추출 → `go_back()` 복귀
   - `_apply_detail()` 메서드 분리: URL/클릭 양쪽에서 공용 상세 추출
   - 클릭 후 실제 URL을 `product_url`에 저장 (상세 페이지 URL 확보)
   - 예외 시 목록 페이지 복구 로직 추가

2. `agents/product/engine.py` - **URL 추출 개선**
   - `_JS_FIND_DOM_PRODUCTS`: `a[href]` 탐색 시 `javascript:` 제외 → 실제 URL 우선
   - `data-url`, `data-href`, `data-link`, `data-detail-url` 속성 탐색 추가
   - `javascript:` 링크 → `product_id` 추출 (기존 유지)

3. `agents/product/engine.py` - **출력 파일 3분할**
   - `products.json`: 기본 상품 목록 (description/detail_images 제외)
   - `product_details.json`: 전체 상품 + 상세 정보
   - `crawl_result.json`: 메타데이터 + 요약 통계 (total_products, detail_collected)

4. `agents/product/engine.py` - **`_log()` 인코딩 안전 처리**
   - Windows cp949 콘솔에서 유니코드 문자(em dash 등) 출력 시 `UnicodeEncodeError` → `utf-8 fallback` 처리

**수정된 파일**:
- `agents/product/engine.py` (`_collect_details`, `_apply_detail`, `_save_json`, `_JS_CLICK_CARD`, `_JS_FIND_DOM_PRODUCTS`, `_log`)

---

### Phase 17. 상세 수집 품질 개선 — _JS_EXTRACT_DETAIL 전면 재작성
> 상품 상세 정보(description/spec/detail_images)가 실제로 수집되지 않던 문제 수정

**사용자 요청**: 롯데면세점 크롤링에서 products.json과 product_details.json 내용이 동일해 보인다. 상세 정보가 크롤링 안 된 것 아닌가?

**원인 분석**:
1. **meta description 함정**: `_JS_EXTRACT_DETAIL`이 `meta[name="description"]`을 먼저 가져오는데, 롯데면세점은 이 값이 사이트 공통 문구("인터넷 쇼핑몰, 롯데포인트/쿠폰 이벤트 정보...")
2. **길이 체크 우회**: 공통 문구가 20자 이상이라 DOM fallback이 작동하지 않음
3. **상세 이미지 미탐지**: 상세 이미지 영역 셀렉터가 롯데면세점 DOM 구조와 불일치
4. **제품 스펙 미수집**: 제품정보 테이블(제품명/성분/용량 등)을 추출하는 로직이 없음

**작업 내역**:

1. `agents/product/engine.py` - **`_JS_EXTRACT_DETAIL` 전면 재작성**
   - **description 추출 4단계 fallback**:
     - OG description → meta description → DOM 셀렉터 → 최대 텍스트 영역
     - 사이트 공통 문구 자동 감지: 페이지 title과 동일하거나 "쇼핑몰|면세점" 패턴이면 DOM 탐색
     - 노이즈 필터링: 적립/할부 혜택, 주문취소/반품안내, 인도안내 등 비상품 텍스트 제외
   - **spec(제품 스펙) 추출 신규 추가**:
     - 테이블 기반: `.tabBody.infoBox table`, `.cmpsPrdInfo_pkg table` 등에서 th-td 쌍 추출
     - dl 기반: dt-dd 쌍에서 키-값 추출
     - description이 빈 경우 spec에서 자동 생성
   - **detail_images 개선**:
     - 셀렉터 우선순위 재정렬 (상세 설명 영역 우선)
     - 썸네일 필터링: `resize/NxN` 패턴의 작은 이미지 제외 (90x90 등)
     - fallback: `#detailZoom`, `og:image` 이미지 수집

2. `agents/product/engine.py` - **`_apply_detail()` 개선**
   - `spec` 필드 저장 추가
   - description 빈 경우 spec 기반으로 자동 생성

3. `agents/product/engine.py` - **`_save_json()` 개선**
   - products.json에서 `spec` 필드도 제외 (상세 전용)
   - detail_collected 카운트에 `spec` 존재 여부도 포함

**수정 결과** (롯데면세점 ID=35, 10건):

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| description | 사이트 공통 문구 (동일 텍스트) | 실제 상품 설명 ("24시간 촉촉한 대한민국 No.1 수분 크림...") |
| spec | 없음 | 13항목 (제품명, 제조업소, 성분, 용량 등) |
| detail_images | 빈 배열 | 최대 19개 원본 이미지 |
| products.json vs product_details.json | 거의 동일 | 명확히 구분됨 |

**수정된 파일**:
- `agents/product/engine.py` (`_JS_EXTRACT_DETAIL`, `_apply_detail`, `_save_json`)

---

### Phase 18. 크롤링 완료 후 실행 버튼 미전환 수정 + GitHub 연동
> 크롤링 종료 감지 정확도 개선 (Popen.poll()) + 프로젝트 GitHub 연동

**사용자 요청**: 수집 대상 설정에서 수집 agent 수행 완료 후 종료 버튼(■)이 사라지지 않고 실행 버튼(▶)이 노출되지 않는 문제

**원인 분석**:
1. **Windows `os.kill(pid, 0)` 한계**: `Popen` 객체의 프로세스 핸들이 열려있으면 프로세스 종료 후에도 `os.kill(pid, 0)`이 성공 반환
2. **Popen 객체 미보관**: `subprocess.Popen`으로 프로세스를 시작하지만 반환된 객체를 저장하지 않아 `poll()` 사용 불가

**작업 내역**:

1. `web/backend/routes/sites.py` — **프로세스 종료 감지 리팩토링**
   - `_is_process_alive(pid)` 헬퍼 함수 추가: `Popen.poll()` 우선 → `os.kill` fallback
   - `_cleanup_finished(pid)` 헬퍼 함수 추가: 로그 핸들 닫기 + `_running_processes` 제거
   - `run_crawl()`: `_running_processes`에 `"proc"` (Popen 객체) 저장
   - `crawl_status()`: `_is_process_alive()` + `_cleanup_finished()` 사용으로 교체
   - `stop_crawl()`: 동일 패턴 적용
   - `get_crawl_logs()`: 동일 패턴 적용
   - 기존 `os.kill(pid, 0)` 직접 호출 5곳 → `_is_process_alive()` 통합

2. GitHub 연동
   - `.gitignore` 업데이트: `logs/`, `*.traineddata`, `/_*.py`, `.claude/` 추가
   - Git 초기화 + 초기 커밋 (183파일, 43,176줄)
   - `gh` CLI 설치 (v2.92.0)
   - Remote: `https://github.com/scm-git-einz/WebCrawlingMngTool.git` (Private)

**수정된 파일**:
- `web/backend/routes/sites.py` (`_is_process_alive`, `_cleanup_finished`, `run_crawl`, `crawl_status`, `stop_crawl`, `get_crawl_logs`)
- `.gitignore`

---

### Phase 18-1. 수집 결과 페이지 — 카테고리/날짜/사이트 계층 뷰
> 수집 결과를 카테고리별 → 날짜별 → 사이트별 계층 구조로 재구성

**사용자 요청**: 크롤링 결과를 카테고리별-날짜별-사이트별로 보여주세요. 날짜는 일자별로 보여주고 상세 시간을 표시.

**작업 내역**:

1. `web/frontend/src/pages/CrawlResults.jsx` — **메인 레이아웃 전면 재구성**
   - 기존: 플랫 테이블 (ID/사이트/유형/날짜/상태/건수/소요시간/상세)
   - 변경: **카테고리 → 날짜 → 사이트** 3단계 아코디언 구조
   - `groupResults()`: API 결과를 `{ category → dateKey → siteKey → items[] }` 트리로 변환
   - 카테고리 헤더: 컬러 배경 + 접기/펼치기 + 결과 건수
   - 날짜 헤더: 일자별 그룹 + "오늘/어제/요일" 표시 + 사이트 수/건수 요약
   - 사이트 그룹: 에이전트 유형 뱃지 + 사이트명 + 수집 횟수
   - 결과 테이블: 시간(HH:MM:SS) + 상태 + 수집 건수 + 소요시간 + 상세 보기
   - 상단 요약 칩: 전체 N건 / 성공 N / 수집 N건

2. `web/frontend/src/App.css` — **계층 뷰 스타일 추가**
   - `.result-category-section`: 카테고리 블록
   - `.result-cat-header`: primary 색상 배경 아코디언 헤더
   - `.result-date-section` / `.result-date-header`: 날짜 그룹 (왼쪽 보더 라인)
   - `.result-site-group` / `.result-site-header`: 사이트 카드
   - `.result-site-table`: 컴팩트 결과 테이블
   - `.result-summary-chips`: 상단 요약 칩

**수정된 파일**:
- `web/frontend/src/pages/CrawlResults.jsx` (메인 레이아웃 + ResultRow 컴포넌트)
- `web/frontend/src/App.css` (계층 뷰 스타일)

---

### Phase 19. 상세 수집 확장 필드 14종 + UI 설정
> 상품 상세 페이지에서 가격/코드/혜택/프로모션 등 14종 필드를 수집하고, UI에서 수집 항목을 선택할 수 있도록 구현

**사용자 요청**: 롯데면세점 상세 페이지에서 정상가(할인 전), 할인율, 판매가(할인 후), 최대혜택가 프로모션 정보를 수집. 상품 상세정보 수집 항목을 UI에서 체크박스로 선택 가능하게 수정.

**작업 내역**:

1. `agents/product/engine.py` — **Agent 확장 필드 구현**
   - `DETAIL_FIELD_DEFS`: 상세 페이지 수집 가능 필드 14종 정의
     - 기본 3종: description, detail_images, spec
     - 코드 2종: product_code, reference_code
     - 가격 5종: regular_price_usd/krw (할인 전 정상가), discount_rate, sale_price_usd/krw (할인 후 판매가)
     - 프로모션: max_benefit_info (최대혜택가 영역 전체 구조화 텍스트 + 쿠폰 정보)
     - 기타: category_breadcrumb, benefits, related_products
   - `_DETAIL_ONLY_KEYS`: products.json 제외 대용량 필드 6종
   - `_normalize_config()`: `detail_fields` 설정 항목 추가
   - `_apply_detail()`: `detail_fields` 기반 동적 수집으로 리팩토링 (미설정 시 기존 3종 fallback)
   - `_normalize_products()`: 확장 필드 14종 전달
   - `_save_json()`: `_DETAIL_ONLY_KEYS` 상수 사용, detail_count 판정 확장

2. `agents/product/engine.py` — **`_JS_EXTRACT_DETAIL` 확장** (기존 3종 → 14종 반환)
   - 섹션 4: 카테고리 breadcrumb — breadcrumb 셀렉터 10종, a태그 우선 파싱, 매장안내 노이즈 필터링
   - 섹션 5: 상품코드/레퍼런스코드 — dt-dd/th-td 패턴 + 합쳐진 코드 분리 (`_extractCodes` 헬퍼)
   - 섹션 6: 가격 4단계 fallback
     - 6-a: 롯데 특화 (`li.regular_price`, `#grdDscntRt`, `#grdSrpDscntAmt`)
     - 6-b: 범용 라벨 매칭 (dt/th 텍스트 기반)
     - 6-c: 가격 래퍼 fallback (`.cmpsPrice_pkg` 등)
     - 6-d: del/s 태그 기반 fallback
   - 섹션 6-e: 최대혜택가 (`dl[data-ganame="maxBenefit"]`) — dl 구조 파싱 + 쿠폰 정보
   - 섹션 7: 구매혜택 — benefit/coupon/point 셀렉터
   - 섹션 8: 관련상품 — together/related/recommend 셀렉터 + 노이즈 필터

3. `web/frontend/src/pages/SiteSettings.jsx` — **UI 수집 항목 선택**
   - `DETAIL_FIELD_DEFS` 상수 (14개 필드 key+label)
   - ProductConfig: "상세 페이지 진입" 체크 시 detail_fields 체크박스 그리드 노출
   - 전체 선택 / 전체 해제 버튼
   - `detail_page` true + `detail_fields` 비어있으면 자동 전체 선택
   - `handleSave`에 `detail_fields` payload 포함

4. `web/frontend/src/App.css` — **스타일 추가**
   - `.detail-fields-grid`: 반응형 그리드 (auto-fill, minmax 160px)
   - `.detail-field-item`: 체크박스 카드 (checked 시 파란 하이라이트)
   - `.btn-xs`, `.btn-outline`: 유틸리티 버튼

5. `web/LOTTE_DETAIL_ANALYSIS.md` — **분석 문서** (신규)
   - 롯데면세점 가격 영역 DOM 구조 상세 분석 (정상가/할인율/판매가/최대혜택가)
   - 셀렉터 우선순위 + 범용 추출 전략 설계
   - 할인/비할인 상품 테스트 결과

**테스트 결과** (롯데면세점):
- 할인 상품: 정상가 $35/52,776원, 할인율 30%, 판매가 $24.5/36,943원, 최대혜택가 전체 추출 — 모두 정상
- 비할인 상품: 정상가 $200/301,580원, 할인/판매가 빈값 — 정상

**수정된 파일**:
- `agents/product/engine.py` (DETAIL_FIELD_DEFS + _JS_EXTRACT_DETAIL 확장 + _apply_detail 리팩토링)
- `web/frontend/src/pages/SiteSettings.jsx` (detail_fields 체크박스 UI)
- `web/frontend/src/App.css` (detail-fields-grid 스타일)
- `web/LOTTE_DETAIL_ANALYSIS.md` (신규 — 가격 DOM 분석)

---

### Phase 19-1. detail_fields 미설정 시 전체 필드 수집 기본값 수정
> detail_page=true인데 detail_fields가 비어 있으면 기존 3종 대신 전체 14종 수집하도록 수정

**사용자 요청**: 롯데면세점 크롤링 실행 시 새로운 가격/코드 필드가 수집되지 않는 문제 확인 요청

**원인 분석**:
- `_JS_EXTRACT_DETAIL`은 14개 필드를 모두 추출하도록 구현 완료 상태
- `_apply_detail()`에서 `detail_fields` 설정이 비어 있으면 기본 3종(description, detail_images, spec)만 수집
- 사이트 DB 설정에 `detail_fields`가 저장되지 않아 항상 기본 3종 fallback 발생

**수정 내역**:
1. `agents/product/engine.py` — `_normalize_config()`
   - `detail_page=true` + `detail_fields` 비어 있으면 `DETAIL_FIELD_DEFS` 전체 14종을 자동 설정
   - UI에서 체크박스 전체 선택 기본값과 동일한 동작
2. `agents/product/engine.py` — `_apply_detail()` fallback
   - 기본 3종 → `DETAIL_FIELD_DEFS` 전체 14종으로 변경 (일관성)

3. `web/frontend/src/pages/CrawlResults.jsx` — **수집 결과 상세 테이블 확장**
   - ProductDetail 테이블 컬럼: `#, 이미지, 상품코드, 상품명, 브랜드, 정상가($), 정상가(원), 판매가($), 판매가(원), 할인율`
   - `hasDetailPrices` 자동 감지: 상세 가격 데이터가 있으면 확장 컬럼, 없으면 기존 2컬럼(판매가/정가)
   - "상세 가격 수집됨" 표시 라벨 추가
   - 할인율 빨간색 강조 표시
4. `web/frontend/src/App.css` — `.product-table-scroll` 가로 스크롤 래퍼 추가

**수정된 파일**: `agents/product/engine.py`, `web/frontend/src/pages/CrawlResults.jsx`, `web/frontend/src/App.css`

---

### Phase 19-2. 면세점 3사 URL 변경 + 수집 결과 가격 표시 개선
> 메인 홈페이지 → 랭킹/베스트 페이지로 URL 변경, 정상가/판매가 표시 로직 개선

**사용자 요청**: 신라면세점 수집 데이터가 상품이 아닌 프로모션 배너 — URL 변경 필요. 정상가에 취소선, 판매가 없으면 정상가를 판매가에 표시.

**원인 분석**: 3사 모두 메인 홈페이지 URL이 등록되어 있어 배너/기획전 카드를 상품으로 인식

**수정 내역**:
1. **면세점 3사 URL 변경** (DB 직접 수정)
   - 롯데면세점(35): `/kr/shopmain/home` → `/kr/shopmain/rankingTrending/main`
   - 신라면세점(36): `/estore/kr/ko/` → `/estore/kr/ko/ranking?XAREA=GNB`
   - 현대면세점(37): `/shop/dm/main.do` → `/shop/dm/best/monthly.do`
2. **수집 결과 가격 표시 개선** (`CrawlResults.jsx`)
   - 판매가 있을 때: 정상가에 취소선 + 연한 색상, 판매가 굵게 표시
   - 판매가 없을 때: 정상가를 판매가 컬럼에 표시 (정상가 컬럼은 취소선 없이 유지)

**수정된 파일**: `web/frontend/src/pages/CrawlResults.jsx`, DB(crawl_sites.site_url)

---

### Phase 19-3. 신라면세점 상세 추출 셀렉터 추가
> 신라면세점 전용 HTML 구조에 맞는 코드/가격 추출 로직 추가

**사용자 요청**: 신라면세점의 상세 페이지 HTML 구조가 롯데면세점과 다름. 레퍼런스코드, 상품코드, 정상가/할인가(USD/KRW)에 대한 전용 셀렉터 필요.

**원인 분석**: 기존 `_JS_EXTRACT_DETAIL`은 롯데면세점 특화(6-a)만 있고, 신라면세점은 완전히 다른 ID/클래스 구조 사용
- 코드: `.product_number > ul > li` 안에 `.number_title`(REF.NO/SKU.NO) + `.number_text`
- 정상가: `#salePrice`(USD), `#salePriceWon`(KRW) — 신라는 salePrice가 실제 정상가
- 할인율: `span.rate`
- 할인가: `#mileageDcPrice`(USD), `#mileageDcPriceWon`(KRW)

**수정 내역**:
1. **섹션 5-a 추가** — 신라면세점 코드 추출 (`agents/product/engine.py`)
   - `.product_number` 내 `li` 순회 → `.number_title`로 REF.NO/SKU.NO 구분
   - REF.NO → `reference_code`, SKU.NO → `product_code`
2. **섹션 6-a2 추가** — 신라면세점 가격 추출 (`agents/product/engine.py`)
   - `#salePrice` / `#salePriceWon` → `regular_price_usd` / `regular_price_krw`
   - `span.rate` → `discount_rate`
   - `#mileageDcPrice` / `#mileageDcPriceWon` → `sale_price_usd` / `sale_price_krw`
   - `data-value` 속성 우선, innerText fallback

**수정된 파일**: `agents/product/engine.py` (_JS_EXTRACT_DETAIL 섹션 5-a, 6-a2)

---

### Phase 19-4. 현대면세점 상세 추출 셀렉터 추가
> 현대면세점 전용 HTML 구조에 맞는 코드/할인율 추출 로직 추가

**사용자 요청**: 현대면세점(37) 상세 수집 시 할인율, 레퍼런스코드, 상품코드가 수집되지 않음

**원인 분석**: 현대면세점은 고유한 HTML 클래스 사용
- 할인율: `<span class="sale_percent"><em>30</em></span>` (숫자만, % 없음)
- 레퍼런스: `<li class="ref">REF NO. : <span>값</span></li>`
- 상품코드: `<li class="sku">SKU NO. : <span>값</span></li>`

**수정 내역**:
1. **섹션 5-a2 추가** — 현대면세점 코드 추출 (`agents/product/engine.py`)
   - `li.ref > span` → `reference_code`
   - `li.sku > span` → `product_code`
   - span이 없을 경우 텍스트 정규식 fallback
2. **섹션 6-a 할인율 확장** — 현대면세점 할인율 (`agents/product/engine.py`)
   - `span.sale_percent em` → 숫자만 있으면 `%` 자동 추가
   - 기존 롯데(`#grdDscntRt`) / 신라(`span.rate`) 이후 fallback으로 동작

**수정된 파일**: `agents/product/engine.py` (_JS_EXTRACT_DETAIL 섹션 5-a2, 6-a 할인율)

---

### Phase 19-5. 롯데면세점 URL 재변경 (추천 랭킹 → 베스트 상품)
> rankingTrending/main은 추천 테마 카드 표시 — best로 재변경

**사용자 요청**: 롯데면세점(35) 수집 결과가 프로모션 테마("청소를 하자! 봄 청소템" 등)로 수집됨

**원인 분석**: `rankingTrending/main` URL은 "추천 랭킹" 탭이 기본 — 테마 카드(이미지+제목)를 상품으로 오인. 실제 상품 베스트셀러는 `rankingTrending/best` 경로

**증상**:
- 상품명이 프로모션 테마명 ("뷰티 빅 세일 ~66%", "꿀잠 부르는 꿀템")
- "$20이하 갓성비 육아템"이 `$` 시작으로 price 필드로 오분류
- 가격/브랜드 없음, description은 저작권 안내문
- 데이터 중복 (rank 1-6 = rank 7-10 반복)

**수정 내역**:
- 롯데면세점(35) URL: `rankingTrending/main` → `rankingTrending/best` (DB 직접 수정)

**수정된 파일**: DB(crawl_sites.site_url)

---

### Phase 20. 사이트별 로그인 계정 관리
> 로그인이 필요한 사이트의 계정 등록/관리 + 크롤링 시 계정 로테이션

**사용자 요청**: 로그인 ID/PWD를 입력하고 관리할 수 있도록. 사이트별 계정 여러 개 등록 가능. 크롤링 시 계정 순환 사용.

**작업 내역**:

1. `core/db.py` — **site_credentials 테이블 + CRUD 메서드**
   - `site_credentials` 테이블: site_id, login_id, login_pwd, label, is_active, last_used_at
   - `add_credential()`, `get_credentials()`, `get_active_credentials()`: 생성/조회
   - `update_credential()`, `delete_credential()`, `toggle_credential()`: 수정/삭제/토글
   - `mark_credential_used()`: 사용 시각 갱신 (로테이션 기준)
   - `get_active_credentials()`: last_used_at ASC NULLS FIRST 정렬 (라운드로빈)

2. `web/backend/routes/sites.py` — **Credential REST API**
   - `GET /api/sites/{id}/credentials`: 사이트 계정 목록
   - `POST /api/sites/{id}/credentials`: 계정 추가
   - `PUT /api/sites/credentials/{cred_id}`: 계정 수정
   - `DELETE /api/sites/credentials/{cred_id}`: 계정 삭제
   - `PUT /api/sites/credentials/{cred_id}/toggle`: 활성/비활성 토글
   - `GET /api/sites/{id}` 응답에 `credentials` 배열 추가

3. `web/frontend/src/pages/SiteSettings.jsx` — **CredentialManager 컴포넌트**
   - 모든 에이전트 유형 공통으로 ConfigModal 하단에 표시
   - 계정 테이블: 라벨, ID, 비밀번호(마스킹/보기 토글), 활성 상태, 최근 사용 시각
   - 추가/수정 폼: 라벨(선택), ID(필수), 비밀번호(필수) 3열 그리드
   - 삭제 시 ConfirmModal(danger) 적용
   - 활성/비활성 배지 클릭으로 토글

4. `web/frontend/src/App.css` — **Credential 스타일**
   - `.credential-section`, `.credential-header`: 섹션 레이아웃
   - `.credential-table`: 계정 목록 테이블 (비활성 행 투명도)
   - `.pwd-cell`, `.btn-icon`: 비밀번호 보기/숨기기
   - `.credential-form`, `.credential-form-grid`: 추가/수정 폼 (3열 그리드)

5. `core/base_agent.py` — **로그인 계정 로테이션 + 범용 로그인**
   - `_get_next_credential(site_id)`: 라운드로빈 로테이션 (last_used_at 기준)
   - `_do_login(page, credential, login_config)`: 범용 로그인 수행
     - login_config로 셀렉터 지정 가능 (login_url, id_selector, pwd_selector, submit_selector, success_indicator)
     - config 미지정 시 자동 폼 탐지: input type=password 기준으로 ID 필드/제출 버튼 역추적
     - 인간형 입력 지연 (300~700ms)

**수정된 파일**:
- `core/db.py` (site_credentials 테이블 + 7개 CRUD 메서드)
- `core/base_agent.py` (_get_next_credential, _do_login)
- `web/backend/routes/sites.py` (5개 API 엔드포인트 + 상세 응답 확장)
- `web/frontend/src/pages/SiteSettings.jsx` (CredentialManager 컴포넌트 + ConfigModal 통합)
- `web/frontend/src/App.css` (credential 스타일)

---

### Phase 21. 주문서 결제정보 수집 에이전트 (OrderAgent)
> 면세점 주문서 페이지에서 결제 요약 + 장바구니 상품 정보를 수집

**사용자 요청**: 롯데면세점 주문서의 최종결제금액 정보를 수집하려고 합니다. 기존 상품 수집과 별도로 주문서 수집 Agent가 필요. 롯데/신라/현대면세점 공통.

**설계 결정**:
- 기존 ProductAgent와 완전히 다른 수집 패턴: 로그인 필수 → 주문서 페이지 → 결제정보 추출
- 별도 에이전트 타입 `order` 신설
- 카테고리 `주문서` 추가, `💳` 아이콘, 녹색(#059669) 배경

**작업 내역**:

1. `agents/order/__init__.py` — 패키지 초기화
2. `agents/order/engine.py` — **OrderAgent 구현**
   - BaseAgent 상속, agent_type = 'order'
   - `_normalize_config()`: login_url, order_url, collect_items, collect_payment, login_config
   - `run_site()` 파이프라인:
     1. 브라우저 시작
     2. `_get_next_credential()` → `_do_login()` 로그인
     3. 주문서 페이지 이동 (order_url, 도메인이 다를 수 있음)
     4. `_JS_EXTRACT_ORDER_PAYMENT` 실행 → 결제정보 + 장바구니 추출
     5. DB + JSON 저장
   - `_JS_EXTRACT_ORDER_PAYMENT` JS 스니펫:
     - 장바구니 상품: 범용 셀렉터로 상품명/수량/정상가/판매가/브랜드/이미지 추출
     - 결제정보 요약: dl/dt-dd, table th-td, 범용 라벨-값 구조 탐색
     - `LABEL_MAP`: 정상가/회원할인/혜택/결제금액/면세한도/과세포인트/적립 등 12개 한국어 라벨→영문키 매핑
   - `_save_json()`: `order_payment.json` + `crawl_result.json`

3. `agents/__init__.py` — AGENT_REGISTRY에 `order: OrderAgent` 등록 (총 7개)

4. `web/frontend/src/pages/SiteSettings.jsx` — **UI 추가**
   - `CATEGORY_LABELS`에 `주문서: { icon: 💳, color: #059669 }` 추가
   - `agentTypeFromCategory()`에 `주문서 → order` 매핑
   - `AGENT_TYPE_LABELS`에 `order: 주문서 수집` 추가
   - `AGENT_BADGE_CLASS`에 `order: order-badge` 추가
   - ConfigModal에 `order → OrderConfig` 분기 추가
   - `OrderConfig` 컴포넌트 신규:
     - 페이지 URL 섹션: 로그인 URL + 주문서 URL (선택, 비워두면 사이트 URL 사용)
     - 수집 항목: 결제정보 수집 / 장바구니 상품 수집 토글
     - 로그인 폼 셀렉터 (선택): ID/PWD/버튼/성공지표 4개 입력 (자동 탐지 가능)

5. `web/frontend/src/pages/CrawlResults.jsx` — **결과 뷰 추가**
   - `AGENT_LABELS`에 `order: 주문서 수집` 추가
   - `ExpandedDetail`에 `order → OrderDetail` 분기 추가
   - `OrderDetail` 컴포넌트: 결제정보 요약 테이블 + 장바구니 상품 테이블
   - `PAYMENT_LABELS`: 12개 결제 필드 한국어 표시 매핑

6. `web/frontend/src/App.css` — **스타일 추가**
   - `.badge.order-badge`: 녹색 배지
   - `.order-toggle-row`: 수집 항목 체크박스 카드
   - `.order-selector-grid`: 셀렉터 입력 2열 그리드
   - `.order-payment-card`, `.order-total-row`: 결제정보 결과 카드

7. **DB: 롯데면세점 주문서 사이트 등록**
   - site_id=54, agent_type='order', category='주문서'
   - login_url: `https://kor.lottedfs.com/kr/login`
   - order_url: `https://kor.lps.lottedfs.com/kr/newOrder`
   - 로그인 계정: ehdsp (site 35에서 복사)

**생성된 파일**:
- `agents/order/__init__.py`
- `agents/order/engine.py`

**수정된 파일**:
- `agents/__init__.py` (AGENT_REGISTRY에 order 추가)
- `web/frontend/src/pages/SiteSettings.jsx` (OrderConfig + 카테고리 매핑)
- `web/frontend/src/pages/CrawlResults.jsx` (OrderDetail 결과 뷰)
- `web/frontend/src/App.css` (order 스타일)

---

### Phase 22. 프록시 IP 로테이션 시스템

> 무료 프록시를 자동 수집/검증하여 IP 로테이션으로 봇 차단 우회

**사용자 요청**: 무료 프록시 IP를 사용하여 자동 로테이션하면서 데이터 수집

**작업 내역**:

1. `core/proxy_manager.py` — **ProxyManager 신규 구현**
   - 8개 무료 프록시 소스에서 HTTP/SOCKS4/SOCKS5 프록시 수집
   - 병렬 검증 (httpbin.org/ip 테스트, 최대 50개 후보 중 15개 목표)
   - 캐시 파일 관리 (data/proxies/proxy_list.json, 30분 TTL)
   - 라운드로빈/랜덤 로테이션 + 블랙리스트 관리
   - 모듈 레벨 싱글톤 `get_proxy_manager()`

2. `core/browser.py` — **프록시 지원 추가**
   - `create()` 메서드에 `proxy` 파라미터 추가
   - `recreate_context()` 메서드 신규: 프록시 교체 시 컨텍스트만 재생성 (브라우저 재시작 불필요)
   - Playwright context-level 프록시 설정

3. `core/base_agent.py` — **프록시 로테이션 통합**
   - `enable_proxy()`: 프록시 모드 활성화
   - `_create_page()`: 프록시 포함 브라우저 페이지 생성 헬퍼
   - `_rotate_proxy()`: 프록시 교체 + 컨텍스트 재생성
   - `_safe_goto()` 수정: 429/503 연속 2회 시 프록시 교체 우선, 403 시 즉시 교체
   - `_is_soft_blocked()`: HTTP 200 소프트 차단 감지 (이미지만/빈 페이지/폼 없음)
   - `_is_blocked()`: @staticmethod → 인스턴스 메서드로 변경, HTTP 상태 + 소프트 차단 통합 감지
     → 모든 에이전트의 15+ 호출 지점에서 코드 변경 없이 소프트 차단 자동 감지
   - `_is_http_blocked()`: HTTP 상태만 체크하는 static 메서드 분리 (_safe_goto 내부용)
   - `_safe_goto()` 수정: 프록시 유무와 관계없이 항상 소프트 차단 감지, 캐시로 중복 DOM 검사 방지
   - `_do_login()` 수정: page.goto → _safe_goto 사용, 로그인 폼 미발견 시 프록시 교체 후 재시도 (최대 3회)

4. **7개 에이전트 모두 수정**: `browser_mgr.create()` → `self._create_page()` 변경
   - product, news, cafe, promotion, banner, directory, order

5. `main.py` — CLI `--proxy` 옵션 추가
   - `python main.py run --id N --proxy`

6. `web/backend/routes/proxy.py` — **프록시 관리 API 신규**
   - `GET /api/proxy/status`: 프록시 풀 상태 조회
   - `POST /api/proxy/refresh`: 프록시 목록 갱신
   - `GET /api/proxy/list`: 프록시 목록 상세 조회

7. `web/backend/routes/sites.py` — 크롤링 실행 API에 `use_proxy` 파라미터 추가
8. `web/backend/app.py` — proxy 라우터 등록
9. `web/ANTI_BOT.md` — Layer 6: 프록시 IP 로테이션 문서 추가

**생성된 파일**:
- `core/proxy_manager.py`
- `web/backend/routes/proxy.py`

**수정된 파일**:
- `core/browser.py` (proxy 파라미터 + recreate_context)
- `core/base_agent.py` (프록시 로테이션 + _create_page)
- `agents/product/engine.py` (_create_page 사용)
- `agents/news/engine.py` (_create_page 사용)
- `agents/cafe/engine.py` (_create_page 사용)
- `agents/promotion/engine.py` (_create_page 사용)
- `agents/banner/engine.py` (_create_page 사용)
- `agents/directory/engine.py` (_create_page 사용)
- `agents/order/engine.py` (_create_page 사용)
- `main.py` (--proxy CLI 옵션)
- `web/backend/app.py` (proxy 라우터 등록)
- `web/backend/routes/sites.py` (use_proxy 파라미터)
- `web/ANTI_BOT.md` (Layer 6 문서)

---

### Phase 23. 브랜드 지점 목록 수집 기능 (DirectoryAgent brand_branch 모드)

> 면세점 브랜드 매장 정보(브랜드명, 지점, 위치/층, 카테고리, 전화번호)를 카테고리별/지점별 전체 수집

**사용자 요청**: 롯데면세점 브랜드 지점 페이지에서 카테고리별 전체 브랜드, 위치, 전화번호를 수집. 다른 면세점에도 유사 구조로 적용 가능해야 함.

**페이지 분석 결과**:
- API: `POST /kr/customer/brndBrchListAjax` (HTML 응답)
- 카테고리 탭(01~12) + 지점별 그룹 + "더보기" 페이지네이션
- 데이터 구조: `dl > dt` (브랜드명), `dd > ul > li` (위치, 카테고리), `dd.tel` (전화번호)
- 17개 지점 (국내 7 + 해외 10), 총 3,667개 브랜드 항목

**작업 내역**:

1. `agents/directory/engine.py` — **brand_branch 수집 모드 추가**
   - `_collect_brand_branch(cfg)`: 카테고리 탭 탐지 → 지점별 "더보기" 전체 로드 → dl/dt/dd 파싱
   - `_load_all_more(cfg)`: 모든 지점의 더보기 버튼 순차 클릭 (max_rounds=200)
   - `_JS_DETECT_CATEGORY_TABS`: 카테고리 탭 탐지 (catChange 함수 기반)
   - `_JS_EXTRACT_BRAND_BRANCH`: 롯데면세점 #brchBrndInfo 전용 dl/dt/dd 추출
   - `_JS_EXTRACT_BRAND_BRANCH_FALLBACK`: 범용 fallback (table/dl 구조)
   - `_JS_CLICK_NEXT_MORE`: 지점별 더보기 버튼 자동 클릭
   - `_normalize_config()`: categories, load_all_pages 필드 추가
   - `_filter_items()`: location, phone, branch 메타 필드 추가

2. `web/frontend/src/pages/SiteSettings.jsx` — **UI 변경**
   - ConfigModal: 사이트명/URL 인라인 편집 기능 추가 (PUT /api/sites/{id})
   - DirectoryConfig: `brand_branch` 목록 유형 추가 (🏬 브랜드 지점)
   - DIR_FIELD_OPTIONS: branch(지점명), location(위치/층), phone(전화번호) 필드 추가
   - brand_branch 선택 시 기본 필드 자동 설정 + index_navigation 비활성화
   - CATEGORY_DEFAULT_CONFIGS['브랜드목록']: brand_branch 기본 설정

3. `web/frontend/src/pages/CrawlResults.jsx` — **결과 뷰 변경**
   - DirectoryDetail: 지점/위치/전화번호 조건부 컬럼 추가
   - 지점 수 통계 표시

---

### Phase 24. 로그 모니터링 페이지 (관리자 영역)

> 에이전트별 크롤링 로그를 단계별로 파싱하여 실시간 모니터링 + 이력 조회

**사용자 요청**: 관리자 영역에 로그 모니터링 전용 메뉴 추가. 에이전트별/단계별 로그 확인 기능.

**핵심 설계**:
- 서버사이드 로그 파싱: 기존 텍스트 로그의 패턴(`수집 시작:`, `탐지 결과:`, `[N/M]` 등)을 자동 감지하여 단계별 섹션으로 분리
- 병합 규칙: 연속된 스크롤/더보기/진행 라인은 하나의 섹션으로 병합
- 실시간 탭: 실행 중 크롤링 2초 폴링 자동갱신
- 이력 탭: 좌측 파일 목록 + 우측 파싱된 로그 뷰어 (split panel)

**작업 내역**:

1. `web/backend/routes/logs.py` — **신규 생성**
   - `GET /api/logs/files`: 로그 파일 목록 (사이트 메타데이터 조인, 에이전트 필터)
   - `GET /api/logs/files/{filename}`: 파싱된 로그 내용 (단계별 섹션)
   - `GET /api/logs/running`: 실행 중 크롤링 + 최근 10줄 미리보기
   - `parse_log_sections()`: 11개 phase 패턴 감지 + 병합 규칙 적용

2. `web/frontend/src/pages/LogMonitoring.jsx` — **신규 생성**
   - `LogSectionViewer`: 접기/펼치기 섹션 뷰어 (phase 아이콘 + 에이전트 배지 + 줄 수)
   - `LiveTab`: 실행 중 크롤링 카드 그리드 + 2초 자동갱신 로그 뷰어
   - `HistoryTab`: split panel (파일 목록 + 섹션 뷰어)
   - 에이전트 필터 드롭다운 + 텍스트 검색 (하이라이트)
   - 모두 펼치기/모두 접기 버튼

3. `web/backend/app.py` — logs 라우터 등록 + dotenv 로드 추가
4. `web/frontend/src/App.jsx` — `/admin/logs` Route 추가
5. `web/frontend/src/components/Layout.jsx` — adminNav에 로그 모니터링 메뉴 추가
6. `web/frontend/src/App.css` — `.log-monitor-*`, `.log-section-*`, `.badge-*` 스타일 (~200줄)

**수정된 파일**: `web/backend/app.py`, `web/frontend/src/App.jsx`, `web/frontend/src/components/Layout.jsx`, `web/frontend/src/App.css`
**신규 파일**: `web/backend/routes/logs.py`, `web/frontend/src/pages/LogMonitoring.jsx`

4. **DB 업데이트** (site_id=51)
   - 사이트명: 롯데면세점 랭킹 → 롯데면세점 브랜드지점
   - URL: rankingTrending/main → /kr/customer/brndBrch
   - crawl_config: list_type=brand_branch, collect_fields=[name,category,location,phone,branch]

**수집 결과 스키마** (모든 면세점 공통):
```json
{
  "name": "브랜드명 (한글+영문)",
  "branch": "지점명",
  "location": "위치 (층)",
  "category": "카테고리",
  "phone": "전화번호",
  "collected_at": "2026-06-08T14:30:00"
}
```

**수정된 파일**:
- `agents/directory/engine.py` (brand_branch 모드 + JS 4개 + 메서드 2개)
- `web/frontend/src/pages/SiteSettings.jsx` (ConfigModal 편집 + DirectoryConfig + 기본 설정)
- `web/frontend/src/pages/CrawlResults.jsx` (DirectoryDetail 컬럼 확장)

**검증**: CLI 실행 (`python main.py run --id 51`) → 17개 지점, 3,667개 브랜드 항목 수집 성공

---

### Phase 24. OrderAgent Headless 전환 + 쿠폰 다운로드 통합 + UI 플로우 시각화

> 주문서 수집을 headless 모드로 전환하여 AWS 서버 배포 가능하도록 하고, 쿠폰 다운로드를 OrderAgent 내부에 통합

**사용자 요청**: 
- OrderAgent를 headless=True로 전환 (AWS 서버에 디스플레이 없음)
- CouponAgent는 이벤트 URL 쿠폰 다운로드 전담 (단독 실행도 가능)
- OrderAgent가 CouponAgent를 내부 호출하여 이벤트 쿠폰 다운로드 관리
- 상품상세 쿠폰 + 주문서 쿠폰은 OrderAgent가 직접 처리
- 로그인 1회, 같은 브라우저 세션으로 전체 플로우 원자적 실행
- UI에서 전체 플로우 시각화

**아키텍처 결정 근거**:
- 쿠폰 미적용 결제금액 수집 방지 → 쿠폰+주문서 원자적 실행 필수
- 로그인 1회로 봇 차단 위험 최소화
- CouponAgent는 `run_event_coupons(page, event_coupons)` 메서드로 page 전달받아 종속 실행

**수집 파이프라인**:
```
OrderAgent.run_site():
  1. 브라우저 시작 (headless)
  2. 메인+LPS 도메인 로그인 (1회)
  3. CouponAgent.run_event_coupons() → 이벤트 URL 쿠폰 다운로드 (같은 page)
  4. 상품코드별 반복:
     a. 상품상세 이동
     b. 상품상세 쿠폰 다운로드 (detail_coupon_selector)
     c. 바로구매 클릭
     d. 주문서 쿠폰 다운로드 (order_coupon_selector)
     e. 출입국정보 확인
     f. 결제정보 수집
  5. 로그아웃 + 결과 저장
```

**작업 내역**:

1. `agents/order/engine.py` — **OrderAgent headless 전환 + 쿠폰 통합**
   - `headless=False` → `headless=True` 전환
   - LPS 서브도메인 사전 로그인 (메인 로그인 후 lps 도메인 로그인)
   - CouponAgent import + `run_event_coupons()` 내부 호출 (page 공유)
   - 상품상세 쿠폰 다운로드 단계 추가 (`detail_coupon_selector`)
   - 주문서 쿠폰 다운로드 단계 (`order_coupon_selector`)
   - `JS_CLICK_COUPON` 공유 (CouponAgent에서 import)
   - `_normalize_config()`: event_coupons, detail_coupon_selector, order_coupon_selector 추가
   - `_JS_CLICK_ORDER_BUTTON`: img alt="바로구매" 매칭 추가
   - 출입국정보 미등록 감지 + 성인인증 처리

2. `agents/coupon/engine.py` — **CouponAgent (이벤트 쿠폰 전담)**
   - BaseAgent 상속, `agent_type = "coupon"`
   - `JS_CLICK_COUPON`: 텍스트 매칭 + CSS 셀렉터 지원 (public 상수)
   - `run_event_coupons(page, event_coupons)`: OrderAgent가 호출하는 종속 메서드
   - `run_site(site_id)`: 단독 실행 모드 (자체 로그인 + 이벤트 쿠폰)
   - `_click_coupon(selector_text)`: 쿠폰 버튼 클릭 + 결과 반환
   - 결과: `output/{site_id}_{name}/coupons.json`

3. `agents/coupon/__init__.py` — 빈 패키지 파일

4. `agents/__init__.py` — CouponAgent 등록
   - `AGENT_REGISTRY`에 `"coupon": CouponAgent` 추가

5. `web/frontend/src/pages/SiteSettings.jsx` — **UI 변경**
   - CATEGORY_LABELS: `'쿠폰'` 카테고리 추가
   - AGENT_BADGE_CLASS: `coupon: 'coupon-badge'` 추가
   - ConfigModal: CouponConfig 분기 추가
   - **CouponConfig 컴포넌트** (단독 실행용): 이벤트 쿠폰 URL/셀렉터 관리
   - **OrderConfig 확장**:
     - 통합 워크플로우: 로그인→이벤트쿠폰→상품상세→상세쿠폰→바로구매→주문서쿠폰→출입국→결제→로그아웃
     - 이벤트 쿠폰 URL+셀렉터 리스트 관리 (추가/삭제) 🎁
     - 상품상세 쿠폰 셀렉터 입력 🎫
     - 주문서 쿠폰 셀렉터 입력 🏷️
     - 쿠폰 단계는 노란 배경으로 시각 구분

6. `web/frontend/src/pages/CrawlResults.jsx` — CouponDetail 컴포넌트 추가

7. `web/frontend/src/App.css` — CSS 추가
   - `.badge.coupon-badge`: 쿠폰 배지 (amber)
   - `.order-workflow-node.coupon`: 쿠폰 단계 스타일 (노란 배경)
   - `.order-workflow-coupon-tag`: 쿠폰 레이블 배지

**수정된 파일**:
- `agents/order/engine.py` (headless + CouponAgent 종속 호출 + 3단계 쿠폰)
- `agents/coupon/engine.py` (이벤트 쿠폰 전담 + 종속/단독 실행 지원)
- `agents/coupon/__init__.py` (신규)
- `agents/__init__.py` (CouponAgent 등록)
- `web/frontend/src/pages/SiteSettings.jsx` (CouponConfig + OrderConfig 쿠폰 통합)
- `web/frontend/src/pages/CrawlResults.jsx` (CouponDetail 추가)
- `web/frontend/src/App.css` (쿠폰 워크플로우 스타일)

---

### Phase 25. BannerAgent v2.1 수정 + OrderAgent 결제 필드 확장 (15종)

> BannerAgent 배너 탐지 72개 멈춤 버그 수정 + OrderAgent 결제정보 수집 4→15 필드 확장

**사용자 요청**:
- 롯데면세점 배너 수집 시 72개 영역 탐지 후 멈추는 문제 해결
- 주문서 결제정보를 브랜드, 정상가(달러/원화), 회원할인(달러/원화/사유), 혜택(달러/원화/사유), 할인율, 최종결제금액(달러/원화), 면세한도적용금액, 과세포인트, 적립 L.POINT 총 15종으로 확장
- 결제정보 미수집 시 에러 메시지를 "출입국정보미등록"으로 통일

**작업 내역**:

1. `agents/banner/engine.py` — **BannerAgent v2.1 전면 수정**
   - `_log()` 모듈 함수 → `self._log()` BaseAgent 메서드로 전환 (UI 로그 뷰어 표시)
   - `MAX_DETECTED_AREAS = 20` 상수 추가 (과도한 영역 탐지 방지)
   - `_JS_DETECT_BANNER_AREAS` 재작성: `addArea()` + `seenEls` Set으로 부모-자식 중복 제거
   - 영역 정렬: 면적 기준 내림차순 → MAX_AREAS 슬라이싱 → top 위치 재정렬
   - 과도하게 넓은 셀렉터 제거 (`[class*="slider"]`, `[class*="Slider"]`, `[class*="slick"]`, `[class*="swiper"]`)
   - `_collect_banners()`: type_counts 요약 로그, 필터 결과 로그, 영역별 진행 로그 추가

2. `agents/order/engine.py` — **결제정보 15종 수집 확장**
   - `_JS_EXTRACT_ORDER_PAYMENT` 전면 재작성:
     - Section 1: 브랜드(`div.brand`) + 상품명(`div.product`) 추출
     - Section 2: `ul.totPaymentAmt1` — 정상가, 회원할인(사유 포함), 혜택(사유 포함)
     - Section 3: `dl.expected_payment` → 최종결제금액 + 할인율; `.duty_free_limit` → 면세한도, 과세포인트, L.POINT
     - Section 4: Fallback `.tit + .price` 패턴 매칭
     - Section 5: 결제정보 미수집 시 debug raw_texts 출력
   - `run_site()` 결과 처리: 15종 필드 전체 로깅 + 결과 dict 확장
   - `_empty_result()` 정적 헬퍼: 4가지 에러 경로에서 일관된 빈 결과 구조 반환
   - 결제정보 미수집 에러: "출입국정보미등록 - 출입국정보 등록 후 수집 가능"으로 통일

3. `web/frontend/src/pages/CrawlResults.jsx` — **OrderDetail 테이블 확장**
   - `orderRowFields()`: 5→17 필드 (brand, regular_price_usd/krw, member_discount_usd/krw/reason, benefit_usd/krw/reason, duty_free_limit, tax_point, l_point)
   - OrderDetail `<thead>`/`<tbody>`: 6컬럼 → 18컬럼 테이블 렌더링
   - 필드별 색상 구분: 회원할인=primary, 혜택=success, 할인율=danger

4. `web/frontend/src/pages/SiteSettings.jsx` — **AddSiteModal 주문서 설정 통합**
   - 카테고리 "주문서" 선택 시 전체 OrderConfig 필드 인라인 표시
   - 이벤트 쿠폰 리스트, 상세/주문 쿠폰 셀렉터, 상품코드, URL, 로그인 셀렉터, 워크플로우 시각화

**수정된 파일**:
- `agents/banner/engine.py` (v2.1 — 로그 수정 + 탐지 제한 + 중복 제거)
- `agents/order/engine.py` (결제정보 4→15 필드 + _empty_result + 에러 통일)
- `web/frontend/src/pages/CrawlResults.jsx` (OrderDetail 18컬럼 테이블)
- `web/frontend/src/pages/SiteSettings.jsx` (AddSiteModal 주문서 설정)

---

### Phase 26. 공통 로그 시스템 통일 — BaseAgent._log() 타임스탬프 포맷

> 모든 에이전트 로그를 `[날짜 시간] [agent_type] 메시지` 공통 포맷으로 통일

**사용자 요청**: Agent 실행 시 로그에 날짜/시간 정보 포함

**아키텍처 결정**:
- BaseAgent에 `_log()` 메서드를 정의하여 모든 에이전트가 상속받아 사용
- 로그 포맷: `[2026-06-11 17:06:26] [product] 메시지`
- UnicodeEncodeError 안전 처리 (Windows cp949 콘솔 대응)
- BrowserManager는 BaseAgent를 상속하지 않으므로 별도 `_log()` 정적 메서드 추가

**기존 3가지 로그 패턴 → 1가지로 통일**:

| 기존 패턴 | 에이전트 | 변경 |
|-----------|---------|------|
| `self._log()` 자체 정의 | OrderAgent | 삭제 → BaseAgent 상속 |
| 모듈 레벨 `_log()` 함수 | ProductAgent, DirectoryAgent | 삭제 → `self._log()` |
| 직접 `print(f"[tag] ...")` | NewsAgent, CafeAgent, PromotionAgent, BaseAgent | `self._log()` 변환 |

**작업 내역**:

1. `core/base_agent.py` — **BaseAgent._log() 공통 로그 메서드 추가**
   - `import sys, datetime` 추가
   - `_log(self, msg)` 메서드: `[날짜시간] [agent_type] 메시지` 포맷 출력
   - UnicodeEncodeError 시 `sys.stdout.buffer` fallback
   - `run_all()` 내 `print()` → `self._log()` 변환
   - `_safe_goto()`, `_is_blocked()`, `_is_soft_blocked()` 내 print → `self._log()` 변환
   - `enable_proxy()`, `_rotate_proxy()` 등 프록시 관련 print → `self._log()` 변환
   - `_do_login()` 내 print → `self._log()` 변환

2. `core/browser.py` — **BrowserManager._log() 정적 메서드 추가**
   - `import sys, datetime` 추가
   - `_log(msg)` 정적 메서드: `[날짜시간] [browser] 메시지` 포맷
   - 모든 `print(f"[browser] ...")` → `self._log(f"...")` 변환

3. `agents/product/engine.py` — 모듈 레벨 `_log()` + `_TAG` 제거 → `self._log()` 전환
4. `agents/directory/engine.py` — 모듈 레벨 `_log()` + `_TAG` 제거 → `self._log()` 전환
5. `agents/order/engine.py` — 자체 `_log()` 메서드 + `_TAG` 제거 → BaseAgent 상속
6. `agents/coupon/engine.py` — 미사용 `_TAG` 제거
7. `agents/banner/engine.py` — 미사용 `_TAG` 확인 (이미 self._log 사용)
8. `agents/news/engine.py` — 모든 `print(f"[news] ...")` → `self._log(f"...")` 변환
9. `agents/cafe/engine.py` — 모든 `print(f"[cafe] ...")` → `self._log(f"...")` 변환
10. `agents/promotion/engine.py` — 모든 `print(f"[promotion] ...")` → `self._log(f"...")` 변환

**수정된 파일**:
- `core/base_agent.py` (공통 _log 메서드 + 모든 print 변환)
- `core/browser.py` (정적 _log 메서드 + 모든 print 변환)
- `agents/product/engine.py` (모듈 _log 제거 → self._log)
- `agents/directory/engine.py` (모듈 _log 제거 → self._log)
- `agents/order/engine.py` (자체 _log 제거 → BaseAgent 상속)
- `agents/coupon/engine.py` (_TAG 제거)
- `agents/news/engine.py` (print → self._log)
- `agents/cafe/engine.py` (print → self._log)
- `agents/promotion/engine.py` (print → self._log)

---

### Phase 27. 크롤링 강제종료 상태(stopped) 관리

> 크롤링 강제 종료 시 DB 상태를 running→stopped로 전환 + 서버 시작 시 잔여 running 정리

**사용자 요청**: 크롤링 실행 후 강제 종료 시 수집 결과 상태가 running으로 남는 문제 해결

**문제 원인**:
- `create_result()` → status='running' INSERT
- 정상 완료 시 `update_result(status='success')` 호출
- 강제 종료(taskkill/kill) 시 → `update_result()` 호출 기회 없이 프로세스 종료 → running 영구 잔존

**해결 방안**:
1. `stopped` 상태 신규 추가 (강제종료 전용)
2. 강제 종료 API에서 taskkill 후 해당 사이트의 running → stopped 전환
3. 서버 시작 시 잔여 running 상태 일괄 stopped 정리

**작업 내역**:

1. `core/db.py` — **mark_running_as_stopped() 메서드 추가**
   - `site_id` 지정 시: 해당 사이트의 running → stopped + "사용자에 의해 강제 종료됨"
   - `site_id` 미지정 시: 전체 running → stopped + "서버 재시작으로 인한 강제 종료"
   - 변경된 레코드 수 반환

2. `web/backend/routes/sites.py` — **stop_crawl() API에서 DB 상태 업데이트**
   - taskkill/kill 성공 후 `db.mark_running_as_stopped(site_id)` 호출
   - try/except로 DB 오류가 중지 응답에 영향 주지 않도록 처리

3. `web/backend/app.py` — **서버 시작 시 잔여 running 정리**
   - `@app.on_event("startup")` 핸들러 추가
   - 전체 running → stopped 일괄 전환
   - 변경 건수 콘솔 출력

4. `web/frontend/src/pages/CrawlResults.jsx` — **stopped 상태 UI 표시**
   - `STATUS_CLASS`에 `stopped: 'stopped'` 추가
   - `STATUS_LABEL` 매핑 추가 (success→성공, running→실행중, failed→실패, stopped→강제종료)
   - 결과 테이블에서 한글 라벨 표시

5. `web/frontend/src/App.css` — **stopped 뱃지 스타일**
   - `.badge.stopped { background: #f1f5f9; color: #ea580c; }` (회색 배경 + 주황 텍스트)

**상태 체계 (최종)**:

| 상태 | 의미 | 뱃지 색상 |
|------|------|----------|
| `running` | 수집 실행 중 | 파랑 |
| `success` | 수집 성공 | 초록 |
| `failed` | 수집 실패 (에러) | 빨강 |
| `stopped` | 강제 종료됨 | 주황 |

**수정된 파일**:
- `core/db.py` (mark_running_as_stopped 메서드)
- `web/backend/routes/sites.py` (stop_crawl에서 DB 상태 변경)
- `web/backend/app.py` (startup 이벤트에서 잔여 running 정리)
- `web/frontend/src/pages/CrawlResults.jsx` (stopped 상태 + 한글 라벨)
- `web/frontend/src/App.css` (stopped 뱃지 스타일)

---

### Phase 28. 주문서 수집항목 체크박스 선택 UI + Agent 필드 필터링

> 주문서 결제정보 16종 필드를 체크박스로 개별 선택 가능하게 하고, Agent가 선택된 항목만 수집

**사용자 요청**: 주문서 수집 Agent의 수집항목을 설정 UI에서 체크박스로 열거하여 사용자가 선택한 항목만 수집하도록 변경

**작업 내역**:

1. `web/frontend/src/pages/SiteSettings.jsx` — **수집항목 체크박스 UI**
   - `ORDER_COLLECT_FIELDS` 상수: 16종 필드 정의 (key, label, group)
     - 기본정보: 브랜드, 상품명
     - 가격: 정상가(달러/원화)
     - 할인: 회원할인(달러/원화/사유)
     - 혜택: 혜택(달러/원화/사유)
     - 결제: 결제금액(달러/원화), 할인율
     - 부가: 면세한도적용금액, 과세포인트, 적립 L.POINT
   - `ALL_ORDER_FIELD_KEYS`: 전체 필드 키 배열
   - **ConfigModal OrderConfig**: `collect_fields` 상태 추가, 기존 단일 토글 → 16개 체크박스 그리드
   - **AddSiteModal**: `orderConfig`에 `collect_fields` 추가, 동일한 체크박스 그리드
   - 전체선택/전체해제 버튼 추가
   - 기존 `field-checkbox-grid` CSS 클래스 재사용

2. `agents/order/engine.py` — **collect_fields 기반 필드 필터링**
   - `_normalize_config()`: `collect_fields` 기본값 `[]` (빈 배열 = 전체 수집)
   - `_filter_fields()` 정적 메서드: 선택된 필드만 남기고 제거
     - `product_code`, `product_name`, `detail_url`, `order_url`, `error`는 항상 유지
   - `run_site()`: 결과 저장 직전에 `_filter_fields()` 적용

**수정된 파일**:
- `web/frontend/src/pages/SiteSettings.jsx` (OrderConfig + AddSiteModal 체크박스 UI)
- `agents/order/engine.py` (_normalize_config + _filter_fields + run_site 필터 적용)

### Phase 29. 수집 설정 매트릭스 대시보드

> 전체 사이트의 수집항목 설정 현황을 에이전트별 매트릭스 테이블로 한눈에 확인

**사용자 요청**: 카테고리, 사이트명, URL 기준으로 Agent, 수집항목들 나열, 수집주기, 설정일을 표현하고 수집항목에 포함될 경우 'O'로 마킹하는 매트릭스 대시보드 페이지 추가

**작업 내역**:

1. `web/frontend/src/pages/Matrix.jsx` — **매트릭스 대시보드 페이지 신규 생성**
   - `AGENT_FIELD_DEFS`: 8개 에이전트별 수집 가능 필드 정의 (product 11, news 6, cafe 5, promotion 5, banner 6, directory 7, order 16, coupon 1)
   - `isFieldCollected()`: 사이트 crawl_config에서 필드별 수집 여부 판정 (에이전트별 분기 로직)
   - 요약 카드: 전체 사이트 수, 활성 사이트 수, 에이전트별 사이트 수
   - 필터 바: 에이전트 / 카테고리 드롭다운 필터
   - 에이전트별 섹션: 해당 에이전트 사이트들을 매트릭스 테이블로 표시
   - 테이블 컬럼: #, 카테고리, 사이트명, URL, 수집주기, 설정일, 최근수집일, [에이전트별 수집필드들]
   - 최근수집일: `/api/dashboard/stats`의 `site_status`에서 사이트별 마지막 crawl_date 표시
   - 수집항목 포함 시 'O' 마킹 (파란색 하이라이트)
   - 비활성 사이트 반투명 처리

2. `web/frontend/src/App.jsx` — Matrix 라우트 추가 (`/matrix`)
3. `web/frontend/src/components/Layout.jsx` — 사이드바 메뉴 추가 (`📋 대시보드-매트릭스`)
4. `web/frontend/src/App.css` — 매트릭스 테이블 전용 CSS 스타일 추가
   - `.matrix-summary`, `.matrix-filter-bar`, `.matrix-table`, `.matrix-collected` 등
   - CSS Variables 사용 (하드코딩 색상 없음)

**수정된 파일**:
- `web/frontend/src/pages/Matrix.jsx` (신규)
- `web/frontend/src/App.jsx` (라우트 추가)
- `web/frontend/src/components/Layout.jsx` (메뉴 추가)
- `web/frontend/src/App.css` (매트릭스 CSS 추가)

### Phase 30. LLM 토큰 사용량 추적 인프라 구축

> 에이전트에서 LLM API 사용 시 토큰 사용량/비용을 자동 추적하는 전체 구조

**사용자 요청**: 향후 Agent에서 LLM 사용 시 유형별/항목별 토큰 사용량을 대시보드로 확인

**작업 내역**:

1. `CLAUDE.md` — LLM 사용 규칙 변경
   - 기존 "LLM/AI API 호출 금지" → "LLM API 사용 허용 (비용 추적 필수)"
   - `core/llm_client.py` 통해 호출 + 토큰/비용 DB 기록 필수

2. `core/db.py` — `llm_usage` 테이블 + CRUD 메서드
   - 테이블 컬럼: site_id, agent_type, task_type, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, input_preview, output_preview, elapsed_ms, created_at
   - `add_llm_usage()`: 사용 이력 기록
   - `get_llm_usage_summary()`: 전체 요약 (에이전트별, 작업유형별, 모델별, 일별 추이)
   - `get_llm_usage_detail()`: 필터링 가능한 상세 이력 조회

3. `core/llm_client.py` — **LLM 호출 클라이언트** (신규)
   - `LLMClient` 클래스: agent_type, site_id, model 설정
   - `ask()` 메서드: 프롬프트 전송 → 응답 + 토큰 사용량 반환 + DB 자동 기록
   - `MODEL_PRICING`: 모델별 토큰 단가 (Claude Sonnet/Haiku/Opus, GPT-4o 등)
   - `TASK_TYPES`: 작업 유형 상수 (8종: structure_detection, description_summary 등)
   - Anthropic Messages API 기반 (API 키 없으면 RuntimeError)

4. `web/backend/routes/llm.py` — API 라우트 (신규)
   - `GET /api/llm/summary`: 전체 요약
   - `GET /api/llm/detail`: 상세 이력 (agent_type, task_type, site_id 필터)

5. `web/backend/app.py` — llm 라우터 등록

6. `web/frontend/src/pages/LlmUsage.jsx` — **LLM 사용량 대시보드** (신규)
   - 전체 현황 탭: 요약 카드 (호출수, 입력/출력/전체 토큰, 비용)
   - 에이전트별/작업유형별 바 차트 + 상세 테이블
   - 모델별 사용량, 일별 추이 차트
   - 상세 이력 탭: 필터 + 호출별 상세 테이블 (일시, 에이전트, 작업유형, 모델, 토큰, 비용, 미리보기)
   - 데이터 없을 때 사용 가이드 코드 표시

7. `web/frontend/src/App.jsx` — `/admin/llm` 라우트 추가
8. `web/frontend/src/components/Layout.jsx` — 관리자 메뉴 추가 (`🤖 LLM 토큰 사용량`)
9. `web/frontend/src/App.css` — LLM 대시보드 전용 CSS

**에이전트에서 사용 방법**:
```python
from core.llm_client import LLMClient

llm = LLMClient(agent_type="product", site_id=5)
result = llm.ask(
    task_type="description_summary",
    prompt="상품 설명을 요약해줘: ...",
)
# result["text"], result["tokens"], result["cost_usd"]
```

**수정된 파일**:
- `CLAUDE.md` (LLM 사용 규칙 변경)
- `core/db.py` (llm_usage 테이블 + CRUD)
- `core/llm_client.py` (신규 — LLM 클라이언트)
- `web/backend/routes/llm.py` (신규 — API)
- `web/backend/app.py` (라우터 등록)
- `web/frontend/src/pages/LlmUsage.jsx` (신규 — 대시보드)
- `web/frontend/src/App.jsx` (라우트 추가)
- `web/frontend/src/components/Layout.jsx` (메뉴 추가)
- `web/frontend/src/App.css` (LLM CSS 추가)

---

### Phase 31. CouponAgent 이벤트 자동 탐색 + 쿠폰 키워드 관리

> 이벤트 목록 페이지 자동 순회 + 키워드 기반 쿠폰 버튼 자동 탐색

**사용자 요청**: 이벤트 페이지 URL을 수동 등록하는 대신, 이벤트 목록 페이지를 자동 순회하고 키워드로 쿠폰 버튼을 탐색/클릭

**작업 내역**:

1. `agents/coupon/engine.py` — CouponAgent 자동 탐색 기능 추가
   - `JS_EXTRACT_EVENT_LINKS`: `#setEvtListDetail` 내 `a[data-value]` 링크에서 이벤트 URL 자동 수집
   - `_discover_event_pages()`: 이벤트 목록 페이지 → 하위 이벤트 URL 목록 반환
   - `run_auto_discovery_coupons()`: 자동 탐색 모드 — 이벤트 목록 순회 + 키워드로 쿠폰 클릭
   - `_normalize_config()`: `event_list_url`, `coupon_keywords` 필드 추가
   - `run_site()`: 수동(event_coupons) + 자동(event_list_url+coupon_keywords) 병행 지원

2. `agents/order/engine.py` — OrderAgent에서 자동 탐색 쿠폰 호출 추가
   - CouponAgent 호출 시 수동/자동 모드 분기
   - `run_auto_discovery_coupons()` 호출 로직 추가

3. `web/frontend/src/pages/SiteSettings.jsx` — UI 변경
   - **CouponConfig**: `event_list_url` 입력 + `coupon_keywords` 멀티라인 텍스트 영역 추가
   - **OrderConfig**: 동일하게 자동 탐색 섹션 추가
   - **AddSiteModal**: 주문서 추가 시 자동 탐색 설정 포함
   - 워크플로우 시각화에 "🔍 자동 탐색 쿠폰" 단계 추가
   - 쿠폰 키워드: 엔터로 구분, 중복 제거, parsedKeywords로 저장

4. `web/frontend/src/pages/Matrix.jsx` — 매트릭스 필드 추가
   - coupon 에이전트: `auto_discovery`, `coupon_keywords` 필드 추가 (3개→3개)
   - order 에이전트: `event_coupons`, `auto_discovery`, `coupon_keywords` 필드 추가 (16→19개)
   - `isFieldCollected()`: 자동 탐색/키워드 설정 여부 판정 로직

**config 구조 변경**:
```json
{
  "event_coupons": [{"url": "...", "selector": "..."}],
  "event_list_url": "https://kor.lottedfs.com/kr/event/eventDetail?evtDispNo=1044712",
  "coupon_keywords": ["쿠폰 다운로드", "혜택받기", "쿠폰받기", "다운받기"]
}
```

**수정된 파일**:
- `agents/coupon/engine.py` (자동 탐색 로직)
- `agents/order/engine.py` (자동 탐색 호출)
- `web/frontend/src/pages/SiteSettings.jsx` (UI: CouponConfig, OrderConfig, AddSiteModal)
- `web/frontend/src/pages/Matrix.jsx` (필드 정의 + 수집 판정)
- `web/PROGRESS.md` (Phase 31 기록)

---

### Phase 32. 수집 필드 정의 DB 관리 + 기본/추가 필드 구분 제거

> 에이전트별 수집 필드 정의를 하드코딩에서 DB 관리로 전환, 매트릭스와 설정 모달의 불일치 해소

**사용자 요청**: 매트릭스에 표시되는 수집 필드가 실제 설정과 다르게 노출됨. 수집 항목을 하드코딩하지 말고 DB에서 관리. 기본필드/추가필드 구분 제거.

**문제 원인**: 
- Matrix.jsx의 `AGENT_FIELD_DEFS`가 하드코딩되어 실제 에이전트와 불일치
- `isFieldCollected()`가 `collect_fields`만 확인하고 `optional_fields` 누락
- SiteSettings.jsx에서 기본/추가 필드를 별도 배열로 관리하여 복잡도 증가

**작업 내역**:

1. `core/db.py` — **agent_field_defs 테이블 추가**
   - 스키마: agent_type, field_key, label, config_key, sort_order, is_active
   - `_seed_agent_field_defs()`: 8개 에이전트 × 66개 필드 초기 데이터 자동 삽입
   - `get_agent_field_defs()`: 전체/에이전트별 필드 정의 조회
   - `upsert_agent_field_def()`: 필드 추가/수정 (UPSERT)
   - `delete_agent_field_def()`: 필드 비활성화

2. `web/backend/routes/sites.py` — **API 추가**
   - `GET /api/agent-fields`: 에이전트별 필드 정의 조회 (agent_type 그룹핑)
   - `PUT /api/agent-fields/{agent_type}`: 필드 정의 수정

3. `web/frontend/src/pages/Matrix.jsx` — **하드코딩 제거**
   - `AGENT_FIELD_DEFS` 상수 제거 → `/api/agent-fields` API에서 로드
   - `isFieldCollected()`: config_key 기반 범용 판정으로 재작성
     - `collect_fields`: collect_fields + optional_fields 모두 확인
     - `banner_areas`, `event_coupons` 등 개별 config_key 처리
   - 에이전트 필터 목록도 API 응답 기반으로 동적 생성

4. `web/frontend/src/pages/SiteSettings.jsx` — **필드 구분 제거 + DB 연동**
   - `PRODUCT_FIELDS`, `DEFAULT_COLLECT_FIELDS` 상수 제거
   - `DIR_FIELD_OPTIONS` 상수 제거
   - `ORDER_COLLECT_FIELDS`, `ALL_ORDER_FIELD_KEYS` 상수 제거
   - ProductConfig: `fieldDefs` props 사용, collect_fields + optional_fields → 단일 collect_fields 통합
   - DirectoryConfig: `fieldDefs` props 사용
   - OrderConfig: `fieldDefs` props 사용
   - ConfigModal: `agentFieldDefs` props 전달
   - AddSiteModal: `agentFieldDefs` props 전달
   - CATEGORY_DEFAULT_CONFIGS: optional_fields → collect_fields로 병합
   - COLLECT_ITEMS_BY_AGENT: group('basic'/'extra') 구분 제거
   - buildCrawlConfig(): optional_fields 분리 제거, 단일 collect_fields

**DB 스키마**:
```sql
CREATE TABLE agent_field_defs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_type   TEXT NOT NULL,
    field_key    TEXT NOT NULL,
    label        TEXT NOT NULL,
    config_key   TEXT NOT NULL DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    is_active    INTEGER NOT NULL DEFAULT 1,
    UNIQUE(agent_type, field_key)
)
```

**config_key 의미**: 해당 필드의 수집 여부를 결정하는 crawl_config 키
- `collect_fields`: 배열에 포함 여부로 판정
- `banner_areas`: 배열에 포함 여부로 판정
- `detail_page`, `collect_body` 등: boolean 값으로 판정
- `""` (빈 문자열): 항상 수집되는 필드

**수정된 파일**:
- `core/db.py` (agent_field_defs 테이블 + CRUD)
- `web/backend/routes/sites.py` (agent-fields API)
- `web/frontend/src/pages/Matrix.jsx` (전면 재작성)
- `web/frontend/src/pages/SiteSettings.jsx` (하드코딩 제거 + DB 연동)
- `web/PROGRESS.md` (Phase 32 기록)

### Phase 33. 실패 모니터링 시스템 구축
> 크롤링 실패 이벤트 구조화 저장 + 관리자 실패 모니터링 페이지

**사용자 요청**: 크롤링 실행 시 발생하는 실패(HTTP 차단, 소프트 차단, 로그인 실패, 카드 클릭 실패, 주문서 도달 실패, 결제정보 없음 등)를 구조화하여 DB에 저장하고, 관리자 페이지에서 모니터링

**설계 결정**:
- A안 채택: 크롤 1회 = DB 1행, 개별 이벤트는 JSONB 배열 저장
- 7종 실패 유형: http_block, soft_block, login_fail, click_fail, nav_fail, data_fail, exception
- FailureCollector 패턴: 크롤 중 메모리 수집 → 종료 시 한 번에 DB 저장

**작업 내역**:

1. **DB 테이블 + 메서드** (`core/db.py`)
   - `crawl_failure_log` 테이블 (JSONB: failure_summary, failure_events)
   - 3개 인덱스 (site_id, crawl_date DESC, agent_type)
   - insert_failure_log, get_failure_logs, get_failure_log_detail, get_failure_stats

2. **FailureCollector 클래스** (`core/failure_collector.py` 신규)
   - 크롤 1회 동안 실패 이벤트 메모리 수집
   - add(), build_summary(), save() 메서드
   - 실패 없으면 DB 저장 생략

3. **BaseAgent 통합** (`core/base_agent.py`)
   - `_failure_collector` 속성 + `_record_failure()` 헬퍼
   - `_safe_goto()`: HTTP 429/503, HTTP 403, 소프트 차단 감지 시 자동 기록
   - `_do_login()`: 로그인 페이지 차단, 폼 미발견, 성공 지표 미발견, 예외 시 기록

4. **에이전트 8종 통합** (agents/*/engine.py)
   - FailureCollector 초기화 (run_site 시작)
   - except 블록에서 exception 유형 기록
   - finally 블록에서 collector.save() 호출
   - OrderAgent: 상품상세 차단, 주문서 미도달, 출입국정보 미등록, 결제정보 없음 기록

5. **API 라우터** (`web/backend/routes/failures.py` 신규)
   - GET /api/failures/stats (기간별 통계 요약)
   - GET /api/failures (필터링 목록 조회)
   - GET /api/failures/{id} (단건 상세)

6. **관리자 페이지** (`web/frontend/src/pages/FailureMonitoring.jsx` 신규)
   - StatCard 4종 (전체 실패, HTTP차단, 클릭/이동 실패, 데이터 실패)
   - 필터 바 (에이전트, 기간, 사이트)
   - 실패 목록 테이블 + 행 클릭 시 상세 펼침
   - 이벤트 타임라인 (유형 아이콘/배지 + 메시지 + 컨텍스트)

7. **라우팅/메뉴** (`App.jsx`, `Layout.jsx`)
   - /admin/failures 라우트 추가
   - 관리자 사이드바에 '⚠️ 실패 모니터링' 메뉴

8. **스타일** (`App.css`)
   - `.failure-monitor-*`, `.failure-stat-*`, `.failure-filter-*`, `.failure-table-*`, `.failure-event-*` 스타일 추가

**수정된 파일**:
- `core/failure_collector.py` (신규)
- `core/db.py` (테이블 + 4개 메서드)
- `core/base_agent.py` (_record_failure + _safe_goto/_do_login 통합)
- `agents/product/engine.py`, `agents/news/engine.py`, `agents/cafe/engine.py`
- `agents/promotion/engine.py`, `agents/banner/engine.py`, `agents/directory/engine.py`
- `agents/order/engine.py`, `agents/coupon/engine.py`
- `web/backend/routes/failures.py` (신규)
- `web/backend/app.py` (라우터 등록)
- `web/frontend/src/pages/FailureMonitoring.jsx` (신규)
- `web/frontend/src/App.jsx` (라우트)
- `web/frontend/src/components/Layout.jsx` (메뉴)
- `web/frontend/src/App.css` (스타일)
- `web/PROGRESS.md` (Phase 33 기록)

### Phase 34. 로그 출력에 현재 IP 자동 노출
> 모든 `_log()` 출력에 현재 사용 중인 IP(프록시/direct)를 자동 포함

**사용자 요청**: 크롤링 로그에 현재 사용 중인 프록시 IP가 표시되지 않아, 봇 차단 시 어떤 IP로 접속했는지 파악 불가 → 모든 로그에 IP 노출

**설계 결정**:
- `_log()` 메서드가 모든 로그의 단일 출력점이므로, 여기에 `_proxy_ip` 자동 삽입
- 로그 포맷 변경: `[timestamp] [agent_type] msg` → `[timestamp] [agent_type] [IP:address] msg`
- 기존에 메시지 본문에 수동으로 `proxy=...`를 넣은 곳은 중복 제거

**작업 내역**:

1. **`_log()` 메서드 수정** (`core/base_agent.py`)
   - `[IP:{proxy_ip}]` 태그를 모든 로그 라인에 자동 포함
   - 프록시 사용 시: `[IP:http://123.45.67.89:8080]`
   - 직접 연결 시: `[IP:direct]`

2. **IP 중복 메시지 정리** (`core/base_agent.py`)
   - `_safe_goto()`: HTTP 429/503, 403 메시지에서 `proxy=` 제거
   - `_is_soft_blocked()`: 소프트 차단 감지 메시지에서 `proxy_info` 제거
   - `_do_login()`: 로그인 차단 메시지에서 `proxy=` 제거

3. **에이전트 6곳 IP 중복 제거**
   - `agents/product/engine.py`: RuntimeError 메시지
   - `agents/banner/engine.py`: RuntimeError 메시지
   - `agents/directory/engine.py`: RuntimeError 메시지
   - `agents/order/engine.py`: 로그인 차단 + 상품상세 차단 메시지
   - `agents/coupon/engine.py`: 로그인 차단 메시지

**로그 출력 예시**:
```
[2026-06-18 10:30:00] [order] [IP:http://123.45.67.89:8080] Stealth Chromium 브라우저 시작...
[2026-06-18 10:30:05] [order] [IP:http://123.45.67.89:8080] 로그인 시도: user@example.com
[2026-06-18 10:30:10] [order] [IP:http://123.45.67.89:8080] HTTP 403 @ lottedfs.com → 프록시 교체 시도
[2026-06-18 10:30:11] [order] [IP:http://98.76.54.32:3128] 프록시 교체 완료
[2026-06-18 10:30:15] [product] [IP:direct] 수집 시작: 사이트 #5
```

**수정된 파일**:
- `core/base_agent.py` (_log 포맷 변경 + 6곳 중복 IP 제거)
- `agents/product/engine.py` (중복 IP 제거)
- `agents/banner/engine.py` (중복 IP 제거)
- `agents/directory/engine.py` (중복 IP 제거)
- `agents/order/engine.py` (중복 IP 제거 2곳)
- `agents/coupon/engine.py` (중복 IP 제거)
- `web/PROGRESS.md` (Phase 34 기록)

---

### Phase 35. 데이터 테이블 분리 — 모니터링 vs 수집 데이터
> crawl_results(모니터링) + crawl_data(원시 데이터) 분리

**사용자 요청**: 크롤링 수집 데이터를 Agent 상태/건수와 별도 테이블에 분리. 실제 수집 데이터는 향후 메달리온 아키텍처(Bronze/Silver/Gold)에 편입 예정.

**설계**:
- `crawl_results` → 모니터링 전용 (status, product_count, elapsed_sec, error_msg)
- `crawl_data` (신규) → 수집 원시 데이터 (items JSONB, store_info JSONB) — 메달리온 Bronze 레이어

**작업 내역**:
1. **`core/db.py`** — 테이블 분리
   - `crawl_data` 테이블 생성 (crawl_result_id FK, site_id, agent_type, items JSONB, store_info JSONB, item_count)
   - `update_result()`: products가 있으면 `crawl_data`에 저장, `crawl_results`에는 상태/건수만 기록
   - `get_crawl_data(result_id)`: crawl_data 조회 메서드 추가
   - `get_latest_result()`: crawl_data JOIN으로 수집 데이터 포함 반환 (기존 데이터 fallback)

2. **`web/backend/routes/results.py`** — 상세 조회 API 수정
   - `get_result_detail()`: crawl_data에서 products 조회, 없으면 crawl_results fallback (기존 데이터 호환)
   - `dashboard_stats()`, `list_results()`: 변경 없음 (product_count만 사용)

3. **에이전트 코드**: 변경 없음 — `update_result()` 내부에서 자동 라우팅

4. **기존 데이터 마이그레이션**
   - `crawl_results.products/store_info` → `crawl_data.items/store_info`로 77건 이관
   - `crawl_results`에서 `products`, `store_info` 컬럼 DROP

5. **프론트엔드/백엔드 필드명 정리**
   - API 응답: `products` → `items` 으로 변경 (crawl_data.items 컬럼과 일치)
   - `CrawlResults.jsx`: 8개 상세 컴포넌트의 `detail.products` → `detail.items`
   - `main.py`: CLI 결과 조회 `result["products"]` → `result["items"]`

**수정된 파일**:
- `core/db.py` (crawl_data 테이블 + update_result 분리 + get_crawl_data 추가 + products 컬럼 제거)
- `web/backend/routes/results.py` (상세 조회 crawl_data JOIN, 응답 필드 items로 변경)
- `web/frontend/src/pages/CrawlResults.jsx` (detail.products → detail.items, 8개 컴포넌트)
- `main.py` (CLI 결과 조회 필드명 변경)
- `web/PROGRESS.md` (Phase 35 기록)

### Phase 36. 환경변수 관리 + 수집주기 개선 + 시스템 코드 테이블
> .env 환경변수 통합, 수집주기 타입 기반 UI, 코드 테이블 DB 관리

**사용자 요청**: 하드코딩 IP를 .env로 통합, 수집주기를 crontab 스타일로 개선, 코드성 데이터를 시스템 코드 테이블로 관리

**작업 내역**:
1. **환경변수 관리 (.env)**
   - `SERVER_HOST`, `SERVER_PORT`, `WEB_PORT`, `API_HOST`, `DB_HOST` 등 .env에서 관리
   - `core/db.py`, `web/start_web.py`, `web/frontend/vite.config.js` — .env 기반으로 변경
   - `.env.example` 업데이트

2. **수집주기 UI 개선**
   - 타입 기반 계단식 입력: 미설정 / 수시 / 매 N시간 / 매일 / 매주 / 매월
   - 각 타입별 세부 설정: 간격, 시각, 요일, 일자
   - 저장 형식: `""`, `"adhoc"`, `"hourly:6"`, `"daily:9"`, `"weekly:1:9"`, `"monthly:15:9"`
   - 변경 시 ✓/✕ 버튼으로 확인 후 ConfirmModal

3. **상태 아이콘 변경**
   - 활성/비활성 토글을 🟢/🔴 아이콘 버튼으로 변경

4. **시스템 코드 테이블 (`system_codes`)**
   - `core/db.py`: 테이블 생성 + 시드 데이터 (27개 코드)
     - `agent_type` (8종): badge_class 포함
     - `category` (14종): icon, color, agent_type 매핑 포함
     - `crawl_status` (5종): badge_class 포함
   - `web/backend/routes/codes.py`: GET /api/codes, GET /api/codes/grouped API
   - `SiteSettings.jsx`: API에서 코드 로드 → CATEGORY_LABELS, AGENT_BADGE_CLASS, AGENT_TYPE_LABELS, CATEGORY_AGENT_MAP 동적 생성
   - `CrawlResults.jsx`: AGENT_LABELS, AGENT_BADGE_CLASS API 기반으로 변경
   - `AddSiteModal`: agentTypeFromCategory를 코드 테이블 매핑으로 변경

5. **OCR 페이지 버그 수정**
   - `OcrUsage.jsx`: query string `?` 누락 수정 (selectedSite=0일 때 URL 오류)

**수정된 파일**:
- `core/db.py` (system_codes 테이블 + 시드 + get_system_codes)
- `web/backend/routes/codes.py` (신규 — 코드 조회 API)
- `web/backend/app.py` (codes 라우터 등록)
- `web/frontend/src/pages/SiteSettings.jsx` (코드 API 연동, 하드코딩 제거, 수집주기 UI)
- `web/frontend/src/pages/CrawlResults.jsx` (코드 API 연동)
- `web/frontend/src/pages/OcrUsage.jsx` (버그 수정)
- `web/frontend/src/App.css` (schedule-input, btn-status 스타일)
- `web/frontend/vite.config.js` (.env 파싱)
- `web/start_web.py` (환경변수 적용)
- `.env`, `.env.example` (WEB_PORT, API_HOST 추가)
- `web/PROGRESS.md` (Phase 36 기록)
