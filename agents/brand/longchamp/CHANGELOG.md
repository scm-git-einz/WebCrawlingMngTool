# Brand Agent — Longchamp 개발 이력

## 구조 개요

```
agents/brand/
├── base.py           # BrandAgent 공통 베이스
├── dispatcher.py     # BrandDispatcher (agent_type='brand' 진입점)
└── longchamp/
    └── engine.py     # LongchampAgent
```

---

## 구현 내용

### 1. BrandAgent 베이스 (`agents/brand/base.py`)

- **공통 가격 수집 전략** (우선순위 순):
  1. JSON-LD (`schema.org/Product`)
  2. 네트워크 API 캡처 (`NetworkInterceptor`)
  3. DOM fallback (브랜드별 CSS 셀렉터)
- **`fetch_product(url)`** — 상품 상세 페이지 URL로 직접 가격 수집
- **`fetch_by_sku(sku)`** — 브랜드별 오버라이드 (검색 → URL → 가격 수집)
- **`run_site(site_id)`** — DB 키워드(SKU) 목록을 읽어 전체 수집 실행
  - `news_keywords` 테이블에서 활성 검색어 로드
  - SKU별 `fetch_by_sku()` 순차 호출
  - `crawl_results` 테이블에 결과 기록 (UI 결과 탭 연동)
  - `output/{site_id}_{name}/brand_prices.json` 저장
- **`enable_proxy()` 비활성화** — 브랜드 공홈은 단건 조회라 프록시 미사용
  (프록시 사용 시 한국 사이트 접속 불가 문제 방지)

### 2. BrandDispatcher (`agents/brand/dispatcher.py`)

- `agent_type = 'brand'` 로 `AGENT_REGISTRY`에 단일 등록
- `crawl_config.brand_type` 값으로 실제 브랜드 에이전트에 위임
- 지원 브랜드: `longchamp`, `cartier`, `toryburch`, `rogervivier`, `iwc`, `jlc`, `louisvuitton`, `chanel`
- 순환 import 방지: `_BRAND_MAP` 지연 초기화

### 3. LongchampAgent (`agents/brand/longchamp/engine.py`)

- **검색 URL**: `https://www.longchamp.com/kr/ko/search?q={sku}&lang=ko_KR`
- **`_search_product_url(sku)`** — 검색 결과 페이지에서 상품 URL 추출
  - Salesforce Commerce Cloud(SFCC) 표준 셀렉터 사용
- **`fetch_by_sku(sku)`** — 검색 → 상품 URL → `fetch_product()` 순서로 가격 수집
- **DOM 가격 셀렉터**: SFCC 표준 (`.price .sales .value`, `[itemprop="price"]` 등)
- **`_sku_from_url(url)`** — URL 끝 `-{SKU}.html` 패턴으로 SKU 추출

### 4. DB 등록

```sql
INSERT INTO crawl_sites (
  site_name, site_url, agent_type, category, crawl_config
) VALUES (
  'LONGCHAMP(K)',
  'https://www.longchamp.com/kr/ko/',
  'brand',
  '브랜드공홈-상품가격조회(신세계면세점기준)',
  '{
    "collect_fields": ["reference_no","name","original_price","discount_rate","discount_price"],
    "list_type": "search",
    "pagination": "page",
    "max_pages": 5,
    "max_items": 100,
    "detail_page": true,
    "brand_type": "longchamp"
  }'
);
```

### 5. UI — BrandConfig 모달 (`web/frontend/src/pages/SiteSettings.jsx`)

- **검색어 관리**: SKU / 상품코드 / 상품명 추가·삭제 (`news_keywords` API 재사용)
- **상품 수집 항목 체크박스**: 레퍼런스번호 / 상품명 / 원가 / 할인율 / 할인가
  - `add-site-collect-section` + `field-checkbox-grid` 스타일 (사이트 추가 화면과 동일)
- `ConfigModal`에 `agentType === 'brand'` 분기 추가
- `CredentialManager` 브랜드 타입에서 제외 (계정 불필요)

### 6. UI — BrandDetail 결과 뷰 (`web/frontend/src/pages/CrawlResults.jsx`)

- `ExpandedDetail`에 `agentType === 'brand'` 분기 추가
- 테이블 컬럼: **순번 / SKU / 상품명 / 원가 / 할인율 / 할인가**
  - 상품명: 클릭 시 공식홈 상품 페이지로 이동 (링크)
  - 수집 실패 행: 흐리게 처리 + 오류 메시지 표시

---

## 수집 결과 데이터 구조

```json
[
  {
    "sku": "HPI01500",
    "url": "https://www.longchamp.com/kr/ko/...",
    "name": "판테르 드 까르띠에 반지",
    "price": "1200000",
    "currency": "KRW",
    "source": "json-ld",
    "original_price": "",
    "discount_rate": "",
    "discount_price": "",
    "raw_api_url": "",
    "error": ""
  }
]
```

---

## 알려진 한계

| 항목 | 상태 |
|------|------|
| 원가 / 할인율 / 할인가 분리 수집 | 미구현 — 현재 `price` 단일 필드만 반환 |
| `fetch_by_sku` 미구현 브랜드 | rogervivier, iwc, jlc, louisvuitton, chanel |
| 프록시 사용 불가 | 한국 브랜드 공홈 SSL 인증서 충돌로 전면 비활성화 |

---

## 실행 흐름

```
UI 실행 버튼 클릭
→ POST /api/crawl/run
→ subprocess: python main.py run --id {site_id}
→ BrandDispatcher.run_site(site_id)
→ LongchampAgent.run_site(site_id)   ← BrandAgent.run_site() 상속
→ news_keywords 테이블에서 SKU 목록 로드
→ SKU별 fetch_by_sku(sku) 호출
    → _search_product_url(sku)  검색 페이지에서 상품 URL 추출
    → fetch_product(url)        상품 상세에서 가격 수집 (JSON-LD → API → DOM)
→ crawl_results 테이블 기록
→ output/{site_id}_LONGCHAMP(K)/brand_prices.json 저장
```
