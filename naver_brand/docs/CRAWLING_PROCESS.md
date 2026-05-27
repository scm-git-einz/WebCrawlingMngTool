# 네이버 브랜드스토어 크롤링 에이전트 - 프로세스 문서

## 개요

네이버 브랜드스토어에서 매장 정보와 상품 데이터를 수집하는 범용 크롤링 에이전트입니다.
`--store` 인자로 어떤 네이버 브랜드스토어든 크롤링할 수 있습니다.

- **대상 URL**: `https://brand.naver.com/{store_slug}`
- **수집 방식**: Playwright Stealth + `window.__PRELOADED_STATE__` JSON 파싱
- **출력 형식**: JSON (브랜드별 `output/{store_slug}/` 디렉토리에 분리 저장)
- **검증 완료 스토어**:

| 스토어 | 슬러그 | 상품 수 | 상세 수집 |
|--------|--------|---------|----------|
| 에스티 로더 | `esteelauderkorea` | 107개 | 20개 |
| 케라스타즈 | `kerastase` | 72개 | 20개 |

---

## LLM 판단 결과: Playwright 사용

### 판단 근거

| 항목 | 결과 |
|------|------|
| 사이트 유형 | React SPA (CSR), 네이버 자체 프레임워크 |
| 추천 도구 | **Playwright (Stealth 모드)** |
| BeautifulSoup 단독 불가 사유 | JS 렌더링 필수, 정적 HTML은 빈 페이지 반환 |
| 핵심 데이터 소스 | `window.__PRELOADED_STATE__` (872KB JSON) |

### 사이트 구조 분석 결과

```
데이터 소스:  window.__PRELOADED_STATE__ (브라우저 전역 변수)
  ├── channel (65 keys)           → 매장 정보 (이름, 설명, 사업자 정보)
  ├── categoryMenu                → 카테고리 목록 (11개)
  ├── categoryProducts            → 카테고리별 상품 목록
  │   └── simpleProducts[]        → 상품 배열 (이름, 가격, 이미지, 리뷰, 상세 텍스트)
  ├── categoryNames (26 keys)     → 카테고리 ID → 이름 매핑
  └── widgetContents              → 메인 페이지 위젯 (lazy 로딩)

주의: __NEXT_DATA__ 는 존재하지 않음 (Next.js 아님)
주의: /all 경로는 404 반환
주의: 주소/전화번호는 네이버 개인정보 보호 정책으로 ******** 마스킹됨
```

---

## 봇 감지 우회 전략

### 1. playwright-stealth v2 적용
- `Stealth` 클래스 사용 (`apply_stealth_sync`)
- `navigator.webdriver = false` 설정
- 언어: `ko-KR`, 플랫폼: `Win32`

### 2. 브라우저 핑거프린트
```
User-Agent: Chrome 125 / Windows 10
Viewport: 1920x1080
Locale: ko-KR
Timezone: Asia/Seoul
```

### 3. 요청 제어
- 랜덤 딜레이 1~2초
- `brand.naver.com`, `smartstore.naver.com`, `pstatic.net` CDN만 허용
- 폰트/미디어 리소스 차단 (속도 향상)

---

## 패키지 구조

```
naver_brand/
├── docs/
│   └── CRAWLING_PROCESS.md    ← 이 문서
├── config/
│   ├── __init__.py
│   └── settings.py            ← URL, 딜레이, 타임아웃, UA 설정
├── crawlers/
│   ├── __init__.py
│   ├── store_crawler.py       ← 매장 정보 수집
│   └── product_crawler.py     ← 상품 목록 + 상세 수집
├── utils/
│   ├── __init__.py
│   ├── browser.py             ← Playwright Stealth 브라우저 관리
│   └── file_handler.py        ← JSON 저장/로드
├── output/                    ← 수집 결과 JSON
├── main.py                    ← 통합 실행 엔트리포인트
└── requirements.txt
```

---

## 실행 방법

```bash
# 가상환경 활성화
.venv\Scripts\activate

# 의존성 설치
pip install -r naver_brand/requirements.txt

# 브랜드 지정하여 전체 실행 (약 60~70초)
python naver_brand/main.py --store kerastase
python naver_brand/main.py --store esteelauderkorea

# 단계별 실행
python naver_brand/main.py --store kerastase --step 1        # 매장 정보
python naver_brand/main.py --store kerastase --step 2 3 4    # 2~4단계

# --store 미지정 시 기본값: esteelauderkorea
# 환경변수로도 지정 가능: STORE_SLUG=kerastase python naver_brand/main.py
```

---

## 파이프라인 상세

### STEP 1: 매장 정보 수집 (`crawlers/store_crawler.py`)

**데이터 소스**: `__PRELOADED_STATE__.channel`

| 필드 | 소스 키 | 예시 |
|------|---------|------|
| store_name | `channel.channelName` | 에스티 로더 |
| store_id | `channel.id` | 101180106 |
| description | `channel.description` | 갈색병부터 더블웨어 까지... |
| representative | `channel.representName` | 이엘씨에이한국 (유) |
| sale_count | `channel.saleCount` | 8742 |
| address | `channel.businessAddressInfo.fullAddressInfo` | ******** (마스킹) |
| logo_url | `channel.representativeImageUrl` | https://shop-phinf... |

**출력**: `output/store_info.json`

---

### STEP 2: 상품 목록 수집 (`crawlers/product_crawler.py` — crawl_list)

**수집 전략**:
1. 메인 페이지 → `__PRELOADED_STATE__.categoryMenu.firstCategories` 에서 11개 카테고리 확보
2. 각 카테고리 URL (`/category/{id}?cp={page}`) 순회
3. `__PRELOADED_STATE__.categoryProducts.simpleProducts` 에서 상품 추출
4. 중복 상품 ID 제거 → 최종 107개

**카테고리별 수집 현황**:
| 카테고리 | 상품 수 | 신규 (중복 제거) |
|----------|---------|------------------|
| 라운지위크 | 18 | 18 |
| 아시아 NO.1 갈색병 | 13 | 11 |
| 아시아 NO.1 더블 웨어 | 18 | 12 |
| 리바이탈라이징 수프림+ | 13 | 9 |
| 리-뉴트리브 | 18 | 18 |
| 라운지 고객 단독 | 20 | 1 |
| 스킨케어 | 34 | 10 |
| 메이크업 | 39 | 19 |
| 향수 | 9 | 6 |
| 컬렉션 | 30 | 0 |
| 전체상품 | 40+ | 3 |
| **합계** | | **107** |

**상품 데이터 매핑**:
| 필드 | 소스 키 |
|------|---------|
| product_name | `simpleProduct.name` |
| original_price | `simpleProduct.salePrice` |
| selling_price | `simpleProduct.benefitsView.discountedSalePrice` |
| discount_rate | `simpleProduct.benefitsView.discountedRatio` |
| image_url | `simpleProduct.representativeImageUrl` |
| review_count | `simpleProduct.reviewAmount.totalReviewCount` |
| average_score | `simpleProduct.reviewAmount.averageReviewScore` |
| description | `simpleProduct.detailContents.detailContentText` |

**출력**: `output/product_list.json` (107개)

---

### STEP 3: 상품 상세 수집 (`crawlers/product_crawler.py` — crawl_details)

카테고리 페이지의 `simpleProduct` 에 이미 `detailContents.detailContentText` 가 포함되어 있어
별도 상세 페이지 방문 없이 상세 설명을 확보할 수 있음.

상세 텍스트가 부족한 경우에만 개별 상품 페이지를 방문.

**출력**: `output/product_details.json` (상위 20개)

---

### STEP 4: 통합 결과 생성

매장 정보 + 상품 데이터를 병합하여 최종 JSON 생성.

**출력**: `output/crawl_result.json`

---

## 예외 처리

| 상황 | 처리 |
|------|------|
| 데이터 항목 없음 | `"N/A"` 대체 |
| __PRELOADED_STATE__ 없음 | DOM title 태그 폴백 |
| 카테고리 페이지 404 | 스킵 후 계속 |
| 이모지 콘솔 출력 오류 | cp949 safe 인코딩 |
| 페이지 신규 상품 0개 | 즉시 다음 카테고리로 이동 |
| 네트워크 타임아웃 | 30초 후 스킵 |

---

## 기술 스택

| 구성 요소 | 기술 | 버전 |
|-----------|------|------|
| 브라우저 자동화 | Playwright | 1.52.0 |
| 봇 감지 우회 | playwright-stealth | 2.0.3 |
| HTML 파싱 | BeautifulSoup + lxml | 4.13.4 / 5.4.0 |
| 데이터 저장 | JSON (내장 모듈) | - |
