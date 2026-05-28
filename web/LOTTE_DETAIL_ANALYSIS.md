# 롯데면세점 상세 페이지 가격 구조 분석

> 작성: 2026-05-28
> 대상 URL: `https://kor.lottedfs.com/kr/product/productDetail?prdNo=20000946008&adltPrdYn=N`
> 용도: `_JS_EXTRACT_DETAIL` 확장 필드 추출 로직 설계 참고

---

## 1. 가격 영역 DOM 구조

### 1.1 정상가 (할인 전 원래 가격)

```html
<li class="regular_price discount">  <!-- discount 클래스: 할인 적용 중 표시 -->
    <span>$35</span>
    <span>(52,776원)</span>
</li>
```

- **셀렉터**: `li.regular_price span`
- **특징**: `discount` 클래스가 추가되면 취소선 스타일 적용
- **추출 필드**: `regular_price_usd` = `$35`, `regular_price_krw` = `52,776원`

### 1.2 할인율

```html
<strong class="rate" id="grdDscntRt">30%</strong>
```

- **셀렉터**: `#grdDscntRt` 또는 `strong.rate`
- **추출 필드**: `discount_rate` = `30%`

### 1.3 판매가 (할인 적용 후 실제 판매 가격)

```html
<div class="number">
    <strong class="price" id="grdSrpDscntAmt">$24.5</strong>
    <span class="sub_price" id="grdGlblDscntAmt">(36,943원)</span>
</div>
```

- **셀렉터**: `#grdSrpDscntAmt`, `#grdGlblDscntAmt`
- **추출 필드**: `sale_price_usd` = `$24.5`, `sale_price_krw` = `36,943원`
- **참고**: 할인이 없을 경우 판매가 = 정상가

### 1.4 최대혜택가 영역 (프로모션 적용 정보)

```html
<dl class="toggle tgArea" data-ganame="maxBenefit">
    <dt>
        <strong>최대혜택가</strong>
        <div class="number">
            <strong class="price">$24.5</strong>
            <span class="sub_price">(36,943원)</span>
        </div>
    </dt>
    <dd>
        <ul class="benefit_price_box">
            <li>
                <dl>
                    <dt>정상가</dt>
                    <dd><span>$35</span><em>(52,776원)</em></dd>
                </dl>
                <!-- 세일가 적용 -->
                <dl class="dot">
                    <dt>상품세일(<span id="grdDscntRt">30%</span>)</dt>
                    <dd><span class="sale">-$10.5</span></dd>
                </dl>
            </li>
            <li>
                <dl>
                    <dt>세일가</dt>
                    <dd><span id="grdSrpDscntAmt">$24.5</span><em>(36,943원)</em></dd>
                </dl>
                <dl class="dot">
                    <dt>기본혜택(<span>적용제외</span>)</dt>
                    <dd><span>$0</span></dd>
                </dl>
            </li>
            <li>
                <dl>
                    <dt>기본혜택가</dt>
                    <dd><span id="grdSrpSvmnUseAmt">$24.5</span><em>(36,943원)</em></dd>
                </dl>
            </li>
        </ul>
        <!-- 쿠폰 정보 -->
        <div class="coupon_info">
            <span class="tit">주문 시 적용 가능 쿠폰</span>
            <div class="coupon_info_tag">
                <span>상품쿠폰</span>
                <span>브랜드쿠폰</span>
            </div>
        </div>
    </dd>
</dl>
```

- **셀렉터**: `dl[data-ganame="maxBenefit"]`
- **추출 필드**: `max_benefit_info` = 전체 영역 구조화된 텍스트

---

## 2. 가격 필드 정의 (신규/변경)

| 필드 | 의미 | 셀렉터 우선순위 |
|------|------|----------------|
| `regular_price_usd` | 정상가 (달러, 할인 전) | `li.regular_price span` → `maxBenefit` 내 정상가 → dt/th 라벨 매칭 |
| `regular_price_krw` | 정상가 (원화, 할인 전) | 동일 |
| `discount_rate` | 할인율 | `#grdDscntRt` → `strong.rate` → 텍스트 정규식 |
| `sale_price_usd` | 판매가 (달러, 할인 후) | `#grdSrpDscntAmt` → `strong.price` → dt/th 라벨 매칭 |
| `sale_price_krw` | 판매가 (원화, 할인 후) | `#grdGlblDscntAmt` → `span.sub_price` → dt/th 라벨 매칭 |
| `max_benefit_info` | 최대혜택가 프로모션 전체 | `dl[data-ganame="maxBenefit"]` → `[class*="benefit_price"]` |

---

## 3. 범용 가격 추출 전략 (롯데 외 사이트 대응)

롯데면세점 전용 셀렉터를 우선 시도하되, 실패 시 범용 패턴으로 fallback:

1. **ID 기반** (롯데 특화): `#grdDscntRt`, `#grdSrpDscntAmt` 등
2. **클래스 기반**: `li.regular_price`, `strong.rate`, `strong.price`
3. **라벨 매칭**: dt/th 텍스트에서 "정상가", "판매가", "할인율" 등 키워드 매칭
4. **가격 래퍼**: `.cmpsPrice_pkg`, `.price_wrap` 등 상위 컨테이너 내 텍스트 파싱
5. **정규식 fallback**: 페이지 텍스트에서 `$숫자` / `숫자원` 패턴 추출

---

## 4. 할인 미적용 상품 처리

할인이 없는 경우:
- `regular_price` = 표시 가격
- `discount_rate` = 빈값
- `sale_price` = 빈값 (또는 regular_price와 동일)
- `li.regular_price`에 `discount` 클래스 없음

---

## 5. 테스트 결과 (2026-05-28)

### 할인 상품 (prdNo=20000946008)
| 필드 | 값 | 상태 |
|------|------|------|
| regular_price_usd | $35 | O |
| regular_price_krw | 52,776원 | O |
| discount_rate | 30% | O |
| sale_price_usd | $24.5 | O |
| sale_price_krw | 36,943원 | O |
| max_benefit_info | 정상가→상품세일(30%)→세일가→기본혜택→기본혜택가 + 적용가능쿠폰(상품쿠폰, 브랜드쿠폰) | O |
| product_code | 2731038224 | O |
| reference_code | 150100584 | O |
| category_breadcrumb | (빈값 — 이 페이지에 breadcrumb 없음) | - |

### 비할인 상품 (prdNo=10001395589)
| 필드 | 값 | 상태 |
|------|------|------|
| regular_price_usd | $200 | O |
| regular_price_krw | 301,580원 | O |
| discount_rate | (빈값) | O (정상) |
| sale_price_usd | (빈값) | O (정상) |
| sale_price_krw | (빈값) | O (정상) |
| max_benefit_info | (빈값) | O (정상) |
| product_code | 2040265616 | O |
| reference_code | 3328 | O |
| category_breadcrumb | HOME > 향수 > 스킨케어 > 페이스에센스오일 | O |

### 구현 위치
- `_JS_EXTRACT_DETAIL` 내 섹션 6 (가격) — `agents/product/engine.py`
- 추출 전략: 6-a(롯데 특화) → 6-b(범용 라벨) → 6-c(가격 래퍼) → 6-d(del/s 태그)
- `DETAIL_FIELD_DEFS`: 14개 필드 정의
- `_DETAIL_ONLY_KEYS`: products.json 제외 대상 6종

### 완료 / 남은 작업
- [x] UI(ProductConfig) detail_fields 선택 체크박스 — Phase 19에서 구현
- [x] PROGRESS.md Phase 19 기록
- [ ] 다른 면세점 사이트 범용 테스트 (신라/현대)
