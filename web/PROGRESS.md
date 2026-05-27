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
