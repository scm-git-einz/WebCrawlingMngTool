# 롯데면세점 크롤링 에이전트 - 프로세스 문서

## 개요

롯데면세점(kor.lottedfs.com) 사이트에서 매장 정보와 상품 데이터를 수집하는 크롤링 에이전트입니다.

- **대상 URL**: `https://kor.lottedfs.com/kr/shopmain/rankingTrending/main#none`
- **실제 수집 URL**: `https://m.kor.lottedfs.com/kr/shopmain/rankingTrending/main` (모바일)
- **수집 방식**: Playwright Stealth (모바일 브라우저) + BeautifulSoup (HTML 파싱)
- **출력 형식**: JSON

---

## LLM 판단 결과: Playwright 사용

### 판단 근거

| 항목 | 결과 |
|------|------|
| 사이트 유형 | SPA (jQuery 기반, AJAX 동적 로딩) |
| 추천 도구 | **Playwright (Stealth 모드)** |
| BeautifulSoup 단독 불가 사유 | 데스크톱 도메인이 CloudFront에서 점검 이미지 반환, Incapsula WAF 적용 |

### 사이트 접근성 분석

```
접근 방식                            결과
───────────────────────────────────────────────────────
requests -> kor.lottedfs.com        X PNG 이미지 반환 (S3/CloudFront 점검)
Playwright -> kor.lottedfs.com      X PNG 이미지 반환 (봇 감지)
Playwright Stealth -> m.kor.lottedfs.com  O 전체 기능 접근 가능
```

---

## 봇 감지 우회 전략

### 1. playwright-stealth 적용
- `navigator.webdriver = false` 강제 설정
- Chrome runtime, plugins, languages 등 속성 위장
- WebDriver 플래그 자동 제거

### 2. 실제 브라우저 핑거프린트
```python
# User-Agent: 실제 iPhone Safari 17.5
"Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) "
"AppleWebKit/605.1.15 (KHTML, like Gecko) "
"Version/17.5 Mobile/15E148 Safari/604.1"
```

### 3. HTTP 헤더 설정
```python
COMMON_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
```

### 4. 사람처럼 행동
- 랜덤 딜레이 (0.5~5초)
- 사람처럼 스크롤 (랜덤 속도/간격)
- 요청 간 1.5~3초 랜덤 대기
- 세션 유지 (단일 브라우저 컨텍스트)

### 5. 도메인 필터링
- 롯데면세점 도메인만 허용 (lottedfs.com, static.lottedfs.com)
- 외부 광고/분석 도메인 차단 (google-analytics, doubleclick 등)
- 이미지/폰트/미디어 리소스 차단 (속도 향상)

---

## 실행 방법

```bash
# 가상환경 활성화
.venv\Scripts\activate

# 전체 실행
python run.py

# 특정 단계만 실행
python run.py --step 1        # 랭킹 페이지 HTML 수집
python run.py --step 2        # 매장/상품 목록 추출
python run.py --step 3        # 상품 상세 수집
python run.py --step 4        # 통합 결과 생성
python run.py --step 1 2      # 1~2단계만
```

---

## 파이프라인 상세

### STEP 1: 랭킹 페이지 HTML 수집 (`fetch_ranking.py`)

**목적**: 롯데면세점 랭킹/트렌딩 메인 페이지의 렌더링된 HTML 및 AJAX 데이터 수집

**프로세스**:
1. Stealth 모바일 브라우저로 `m.kor.lottedfs.com/kr/shopmain/home` 접속
2. Incapsula WAF 챌린지 통과 대기 (3~5초)
3. 랭킹 페이지로 이동 (`/kr/shopmain/rankingTrending/main`)
4. 스크롤하여 초기 lazy-loaded 상품 로드
5. **브라우저 내부에서 AJAX API 직접 호출** (모든 카테고리, 모든 페이지)

**AJAX API 엔드포인트**:
```
GET /kr/shopmain/rankingTrending/getCategoryPrdasRanking
    ?dispShopNo={catCode}&cateNm={catName}&curPageNo={page}&cntPerPage=20

GET /kr/shopmain/rankingTrending/getTrendingPrdListAjax
GET /kr/shopmain/rankingTrending/getRecomBestListAjax
```

**출력**:
- `output/mobile_ranking.html` - DOM HTML
- `output/ajax_fragments.json` - AJAX HTML 조각 (카테고리별)

---

### STEP 2: 매장 정보 + 상품 목록 추출 (`extract_data.py`)

**목적**: 수집된 HTML에서 매장 정보와 상품 목록을 노출 순서 포함하여 JSON으로 추출

**프로세스**:
1. DOM HTML에서 `ul.unit_LSTE li` 상품 추출 (CSS 선택자 기반)
2. AJAX HTML 조각에서 `ul#categoryPrdasRanking_ul > li` 상품 추출 (AJAX 전용 파서)
3. 중복 상품 ID 제거, display_order 부여

**DOM HTML CSS 선택자**:
```
카테고리:  li.bestPrd_cate_li > a
상품 카드: div.goods_list ul.unit_LSTE > li
순위:      span.unit_no
이미지:    div.unit_img img
브랜드:    span.brand > i.kor
상품명:    span.name
정상가:    span.price01
판매가:    strong.price02 (i.sale 제거 후)
할인율:    i.sale
원화가격:  span.price03
```

**AJAX HTML CSS 선택자** (구조가 다름):
```
상품 리스트: ul#categoryPrdasRanking_ul > li (direct children만)
링크:       a.gaEvtTg (NOT a.unit_link)
상품 ID:    href의 JavaScript 함수 인자에서 추출
순위:       div.display_unit > div.number
브랜드:     div.info > div.name
상품명:     div.info > div.title
이미지:     img[data-src]
```

**수집 데이터 (285개 상품)**:
| 필드 | 설명 | 예시 |
|------|------|------|
| display_order | 노출 순서 | 1, 2, 3... |
| product_id | 상품 ID | 20001034326 |
| product_name | 상품명 | LG PraL SP 써마샷 얼티밋 |
| brand | 브랜드 | LG프라엘 |
| original_price | 정상가 (USD) | $351 |
| selling_price | 판매가 (USD) | $287.82 |
| discount_rate | 할인율 | 18% |
| krw_price | 원화 가격 | 432,824원 |
| image_url | 상품 이미지 | https://static.lottedfs.com/... |
| product_url | 상세 페이지 URL | https://m.kor.lottedfs.com/kr/product/productDetail?prdNo=... |

**출력**: `output/02_shop_products.json`

---

### STEP 3: 상품 상세 수집 (`fetch_product_details.py`)

**목적**: 각 상품의 상세 페이지에서 커머스 공통 element를 수집

**프로세스**:
1. 상품 URL 목록에서 상위 20개 선택
2. 동일한 Stealth 브라우저 세션으로 각 상품 상세 페이지 접속
3. BeautifulSoup으로 구조화된 데이터 추출
4. 요청 간 랜덤 딜레이 (1.5~3초)

**상품 상세 URL 패턴**: `https://m.kor.lottedfs.com/kr/product/productDetail?prdNo={id}`

**커머스 공통 수집 Element**:
| 카테고리 | CSS 선택자 | 설명 |
|----------|-----------|------|
| 상품명 | `div.name` | 한글 상품명 |
| 상품코드 | `p.code` | 영문 + 코드 |
| 브랜드 | OG title `[브랜드]` 패턴 | 브랜드명 |
| 정상가(USD) | `li.regular_price .currency` | 달러 정상가 |
| 정상가(KRW) | `li.regular_price .won` | 원화 정상가 |
| 할인율 | `li.benefit_price .rate` | 할인 퍼센트 |
| 판매가(USD) | `li.benefit_price .price` | 달러 판매가 |
| 판매가(KRW) | `li.benefit_price .sub_price` | 원화 판매가 |
| 최대혜택가 | `#prdMaxBenefitPriceArea .price` | 최대 할인 적용가 |
| 메인 이미지 | `img[src*='prd-img']` | 대표 이미지 |
| 상세 이미지 | `img[src*='ckeditor-img']` | 상세 설명 이미지 |
| 평점 | `#top_review_score` | 평균 평점 |
| 리뷰 수 | `#prdasTotalScore_top` | 리뷰 건수 |
| 옵션 | `.optionArea select` | 색상, 사이즈 등 |
| 재고 상태 | `.btn_soldout` / `.btn_buy` | 판매중/품절 |

**출력**: `output/03_product_details.json`

---

### STEP 4: 통합 결과 생성 (`generate_final.py`)

상품 목록에 상세 데이터를 병합하여 최종 JSON 생성.

**출력**: `output/crawl_result.json`

```json
{
  "crawl_meta": { "target_url": "...", "crawl_date": "...", "crawl_method": "Playwright Stealth" },
  "site_analysis": { "is_dynamic": true, "recommended_tool": "playwright", "bot_bypass": {...} },
  "shop_info": { "shop_name": "...", "categories": [...] },
  "products": [
    {
      "display_order": 1,
      "product_id": "20001034326",
      "product_name": "LG PraL SP 써마샷 얼티밋",
      "brand": "LG프라엘",
      "selling_price": "$287.82",
      "detail": { "price": {...}, "images": {...}, "rating": {...} }
    }
  ],
  "total_products": 285,
  "detail_collected": 20
}
```

---

## 아키텍처

```
browser.py              -> Stealth 브라우저 설정 (봇 감지 우회 핵심)
config.py               -> 설정 (URL, 딜레이, 타임아웃)
fetch_ranking.py        -> STEP 1: 모바일 Stealth + AJAX API 직접 호출
extract_data.py         -> STEP 2: DOM + AJAX HTML 파싱
fetch_product_details.py -> STEP 3: 상품 상세 페이지 수집
generate_final.py       -> STEP 4: 통합 JSON 생성
run.py                  -> 통합 실행 (전체 또는 단계별)
```

## 기술 스택

| 구성 요소 | 기술 | 용도 |
|-----------|------|------|
| 브라우저 자동화 | Playwright (모바일) | SPA 렌더링, WAF 통과 |
| 봇 감지 우회 | playwright-stealth | WebDriver 플래그 제거 |
| HTML 파싱 | BeautifulSoup + lxml | 구조화된 데이터 추출 |
| 도메인 필터 | URL 파싱 | 롯데면세점만 수집 |

## 수집 결과 요약

- 매장 정보: 롯데면세점 랭킹/트렌딩 (15개 카테고리)
- 상품 목록: **285개** (노출 순서 포함, 14개 카테고리)
- 상품 상세: **20개** (가격, 평점, 이미지, 옵션 등)
