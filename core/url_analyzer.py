"""
URL 자동 분석기

사이트 등록 시 URL을 방문하여 수집 가능한 데이터를 탐지한다.
3단계 분석: 네트워크 API → JS 전역변수 → DOM 패턴

반환 구조:
  {
    "status": "success" | "blocked" | "error",
    "page_title": "...",
    "products": { "method": "api|state_var|dom", "count": N, "fields": [...], "sample": {...} },
    "banners":  { "count": N, "areas": [...] },
    "directory": { "count": N, "has_index": bool },
    "raw_fields": ["productName", "price", ...],
    "elapsed": 12.3
  }
"""
import json
import re
import time

from core.browser import BrowserManager
from core.network_interceptor import NetworkInterceptor


# 표준 필드 → 한국어 레이블
_FIELD_LABELS = {
    "name": "상품명", "product_name": "상품명", "productName": "상품명",
    "goodsNm": "상품명", "title": "제목", "itemName": "상품명",
    "price": "가격", "selling_price": "판매가", "sellingPrice": "판매가",
    "salePrice": "판매가", "sale_price": "판매가", "finalPrice": "최종가",
    "displayPrice": "표시가", "original_price": "원가", "originalPrice": "원가",
    "normalPrice": "정가", "listPrice": "정가", "regularPrice": "정가",
    "consumer_price": "소비자가",
    "brand": "브랜드", "brand_name": "브랜드명", "brandName": "브랜드명",
    "brandNm": "브랜드", "manufacturer": "제조사",
    "image": "이미지", "image_url": "이미지URL", "imageUrl": "이미지URL",
    "representativeImageUrl": "대표이미지", "thumbUrl": "썸네일",
    "thumbnail": "썸네일", "productImage": "상품이미지",
    "rank": "순위", "ranking": "순위", "display_order": "표시순서",
    "discount_rate": "할인율", "discountRate": "할인율",
    "discountPercent": "할인%", "benefitRate": "혜택률",
    "gift": "사은품", "giftDesc": "사은품", "freeGift": "사은품",
    "benefit": "혜택",
    "reference_no": "레퍼런스번호", "referenceNo": "레퍼런스번호",
    "modelNo": "모델번호", "productCode": "상품코드",
    "goodsCd": "상품코드", "itemNo": "아이템번호", "sku": "SKU",
    "category": "카테고리", "categoryName": "카테고리",
    "category_name": "카테고리", "cateName": "카테고리",
    "product_url": "상품URL", "productUrl": "상품URL",
    "url": "URL", "link": "링크", "detailUrl": "상세URL",
    "product_id": "상품ID", "productId": "상품ID",
    "productNo": "상품번호", "goodsNo": "상품번호",
    "reviewCount": "리뷰수", "totalReviewCount": "총리뷰수",
    "rating": "평점", "score": "점수",
    "description": "설명", "desc": "설명",
    "stockStatus": "재고상태", "soldOut": "품절여부",
}

# 표준화 매핑: raw 필드 → 표준 키
_STANDARD_MAP = {
    "상품명": "name", "제목": "name",
    "가격": "price", "판매가": "price", "최종가": "price", "표시가": "price",
    "원가": "original_price", "정가": "original_price", "소비자가": "original_price",
    "브랜드": "brand", "브랜드명": "brand", "제조사": "brand",
    "이미지": "image", "이미지URL": "image", "대표이미지": "image",
    "썸네일": "image", "상품이미지": "image",
    "순위": "rank", "표시순서": "rank",
    "할인율": "discount_rate", "할인%": "discount_rate", "혜택률": "discount_rate",
    "사은품": "gift", "혜택": "gift",
    "레퍼런스번호": "reference_no", "모델번호": "reference_no",
    "상품코드": "reference_no", "아이템번호": "reference_no", "SKU": "reference_no",
    "카테고리": "category",
    "상품URL": "product_url", "상품ID": "product_id",
    "URL": "product_url", "링크": "product_url", "상세URL": "product_url",
    "상품번호": "product_id",
    "리뷰수": "review_count", "총리뷰수": "review_count",
    "평점": "rating", "점수": "rating",
    "설명": "description",
    "재고상태": "stock_status", "품절여부": "stock_status",
}


def analyze_url(url: str, timeout_sec: int = 30) -> dict:
    """URL을 방문하여 수집 가능한 데이터를 분석한다."""
    t0 = time.time()
    bm = BrowserManager()
    result = {
        "status": "error",
        "page_title": "",
        "products": None,
        "banners": None,
        "directory": None,
        "discovered_fields": [],
        "elapsed": 0,
    }

    try:
        page = bm.create()
        interceptor = NetworkInterceptor()
        interceptor.start(page)

        # 페이지 방문
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
        if resp and resp.status in (429, 403, 503):
            result["status"] = "blocked"
            result["error"] = f"HTTP {resp.status}"
            return result

        page.wait_for_timeout(5000)
        result["page_title"] = page.title() or ""

        interceptor.stop(page)
        captured = list(interceptor.captured)

        # ── 1단계: 상품 데이터 탐지 ──
        product_info = _detect_products(page, captured)
        if product_info:
            result["products"] = product_info

        # ── 2단계: 배너 영역 탐지 ──
        banner_info = _detect_banners(page)
        if banner_info:
            result["banners"] = banner_info

        # ── 3단계: 목록/디렉토리 탐지 ──
        dir_info = _detect_directory(page)
        if dir_info:
            result["directory"] = dir_info

        # ── 통합 결과 ──
        fields = []
        if product_info:
            fields.extend(product_info.get("fields", []))
        result["discovered_fields"] = fields
        result["status"] = "success"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    finally:
        bm.close()
        result["elapsed"] = round(time.time() - t0, 1)

    return result


def _detect_products(page, captured: list) -> dict | None:
    """상품 데이터를 탐지한다 (API → JS → DOM)."""

    # 1) API 응답에서 탐지
    api_result = _try_api(captured)
    if api_result:
        return api_result

    # 2) JS 전역변수에서 탐지
    js_result = _try_js_globals(page)
    if js_result:
        return js_result

    # 3) DOM 패턴에서 탐지
    dom_result = _try_dom(page)
    if dom_result:
        return dom_result

    return None


def _try_api(captured: list) -> dict | None:
    """네트워크 캡처에서 상품 배열을 찾는다."""
    best = None
    best_count = 0

    for entry in captured:
        body = entry.get("body_parsed")
        if not body or not isinstance(body, (dict, list)):
            continue

        arr = _find_data_array(body)
        if arr and len(arr) > best_count:
            best_count = len(arr)
            sample = arr[0] if arr else {}
            best = {
                "method": "api",
                "count": len(arr),
                "api_url": entry.get("url", "")[:200],
                "sample": _safe_sample(sample),
                "fields": _extract_fields(sample),
            }

    if best and best_count >= 3:
        return best
    return None


def _try_js_globals(page) -> dict | None:
    """JS 전역변수에서 상품 배열을 찾는다."""
    try:
        result = page.evaluate(_JS_ANALYZE_GLOBALS)
    except Exception:
        return None

    if not result or not result.get("items"):
        return None

    sample = result["items"][0] if result["items"] else {}
    return {
        "method": "state_var",
        "count": len(result["items"]),
        "source": result.get("source", ""),
        "sample": _safe_sample(sample),
        "fields": _extract_fields(sample),
    }


def _try_dom(page) -> dict | None:
    """DOM 반복 패턴에서 상품 카드를 찾는다."""
    try:
        result = page.evaluate(_JS_ANALYZE_DOM)
    except Exception:
        return None

    if not result or not result.get("items"):
        return None

    sample = result["items"][0] if result["items"] else {}
    return {
        "method": "dom",
        "count": len(result["items"]),
        "sample": _safe_sample(sample),
        "fields": _extract_fields(sample),
    }


def _detect_banners(page) -> dict | None:
    """배너/슬라이더 영역을 탐지한다."""
    try:
        result = page.evaluate(_JS_ANALYZE_BANNERS)
    except Exception:
        return None

    if not result or not isinstance(result, list) or len(result) == 0:
        return None

    areas = list(set(b.get("type", "unknown") for b in result))
    return {
        "count": len(result),
        "areas": areas,
        "has_slider": any(b.get("is_slider") for b in result),
    }


def _detect_directory(page) -> dict | None:
    """브랜드/이벤트 목록 구조를 탐지한다."""
    try:
        result = page.evaluate(_JS_ANALYZE_DIRECTORY)
    except Exception:
        return None

    if not result:
        return None

    return {
        "count": result.get("count", 0),
        "has_index": result.get("has_index", False),
        "list_type": result.get("list_type", "unknown"),
    }


# ── 필드 추출 ──

def _extract_fields(sample: dict) -> list:
    """샘플 객체에서 수집 가능한 필드 목록을 추출한다."""
    if not sample or not isinstance(sample, dict):
        return []

    fields = []
    seen_std = set()

    for key, val in sample.items():
        if val is None or val == "" or isinstance(val, (dict, list)):
            continue

        label = _FIELD_LABELS.get(key, key)
        std_key = _STANDARD_MAP.get(label, "")

        if std_key and std_key in seen_std:
            continue
        if std_key:
            seen_std.add(std_key)

        val_preview = str(val)[:80] if val is not None else ""

        fields.append({
            "raw_key": key,
            "label": label,
            "standard_key": std_key or key,
            "value_preview": val_preview,
            "value_type": type(val).__name__,
        })

    # 중첩 1레벨도 검사
    for key, val in sample.items():
        if not isinstance(val, dict):
            continue
        for sub_key, sub_val in val.items():
            if sub_val is None or sub_val == "" or isinstance(sub_val, (dict, list)):
                continue
            full_key = f"{key}.{sub_key}"
            label = _FIELD_LABELS.get(sub_key, sub_key)
            std_key = _STANDARD_MAP.get(label, "")
            if std_key and std_key in seen_std:
                continue
            if std_key:
                seen_std.add(std_key)

            fields.append({
                "raw_key": full_key,
                "label": label,
                "standard_key": std_key or sub_key,
                "value_preview": str(sub_val)[:80],
                "value_type": type(sub_val).__name__,
            })

    return fields


def _safe_sample(obj: dict) -> dict:
    """샘플 객체를 JSON 직렬화 가능하게 정리한다."""
    out = {}
    for k, v in list(obj.items())[:20]:
        if isinstance(v, (str, int, float, bool)):
            out[k] = v if len(str(v)) <= 100 else str(v)[:100] + "..."
        elif isinstance(v, dict):
            out[k] = "{...}"
        elif isinstance(v, list):
            out[k] = f"[{len(v)} items]"
        elif v is None:
            out[k] = None
    return out


def _find_data_array(data, depth: int = 0) -> list | None:
    """JSON에서 데이터 배열을 재귀 탐색한다."""
    if depth > 5:
        return None
    if isinstance(data, list) and len(data) >= 3:
        if isinstance(data[0], dict) and len(data[0]) >= 3:
            return data
    if isinstance(data, dict):
        for val in data.values():
            result = _find_data_array(val, depth + 1)
            if result:
                return result
    return None


# ══════════════════════════════════════════════════════════════
# JS 스니펫
# ══════════════════════════════════════════════════════════════

_JS_ANALYZE_GLOBALS = """(() => {
    var GLOBALS = [
        '__NEXT_DATA__','__PRELOADED_STATE__','__INITIAL_STATE__',
        '__NUXT__','__pinia','__remixContext'
    ];
    var NAME_RE = /name|title|product|goods|item/i;
    var PRICE_RE = /price|cost|amount|sell/i;

    function isDataLike(obj) {
        if (!obj || typeof obj !== 'object') return false;
        var ks = Object.keys(obj).join(' ');
        return NAME_RE.test(ks) || PRICE_RE.test(ks);
    }

    function findArrays(obj, depth, src) {
        if (depth > 6 || !obj || typeof obj !== 'object') return [];
        var results = [];
        if (Array.isArray(obj)) {
            if (obj.length >= 3 && typeof obj[0] === 'object' && obj[0] !== null) {
                results.push({source: src, count: obj.length, items: obj});
            }
            return results;
        }
        var keys = Object.keys(obj);
        for (var i = 0; i < keys.length; i++) {
            try {
                var child = obj[keys[i]];
                if (child && typeof child === 'object') {
                    var found = findArrays(child, depth + 1, src);
                    results = results.concat(found);
                }
            } catch(e) {}
        }
        return results;
    }

    for (var gi = 0; gi < GLOBALS.length; gi++) {
        try {
            var val = window[GLOBALS[gi]];
            if (!val) continue;
            var found = findArrays(val, 0, GLOBALS[gi]);
            if (found.length === 0) continue;
            found.sort(function(a,b){ return b.count - a.count; });
            var best = found[0];
            if (best.count >= 3 && isDataLike(best.items[0])) {
                return {
                    source: best.source,
                    items: best.items.slice(0, 5)
                };
            }
        } catch(e) {}
    }
    return null;
})()"""

_JS_ANALYZE_DOM = r"""(() => {
    var PRICE_RE = /[\d,]+\s*원|₩\s*[\d,]+|\$\s*[\d,.]+|¥\s*[\d,.]+/;
    var priceEls = [];
    var allEls = document.body.querySelectorAll('*');
    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        if (el.children.length > 0) continue;
        var txt = (el.textContent || '').trim();
        if (txt.length >= 3 && txt.length < 50 && PRICE_RE.test(txt)) {
            priceEls.push(el);
        }
    }
    if (priceEls.length < 3) return null;

    var bestParent = null, bestTag = '', bestCount = 0;
    for (var pi = 0; pi < Math.min(priceEls.length, 30); pi++) {
        var node = priceEls[pi];
        for (var depth = 1; depth <= 5; depth++) {
            var cur = priceEls[pi];
            for (var d = 0; d < depth; d++) {
                if (!cur.parentElement) break;
                cur = cur.parentElement;
            }
            if (!cur.parentElement) break;
            var parent = cur.parentElement;
            var tag = cur.tagName;
            var sameCount = 0;
            for (var si = 0; si < parent.children.length; si++) {
                if (parent.children[si].tagName === tag) sameCount++;
            }
            if (sameCount >= 3 && sameCount > bestCount) {
                bestParent = parent;
                bestTag = tag;
                bestCount = sameCount;
            }
        }
    }
    if (!bestParent || bestCount < 3) return null;

    var cards = bestParent.querySelectorAll(':scope > ' + bestTag);
    var items = [];
    for (var ci = 0; ci < Math.min(cards.length, 5); ci++) {
        var card = cards[ci];
        var img = card.querySelector('img[src]');
        var link = card.querySelector('a[href]');
        var texts = [], prices = [];
        var walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, null);
        while (walker.nextNode()) {
            var t = walker.currentNode.textContent.trim();
            if (t.length < 2) continue;
            if (PRICE_RE.test(t)) prices.push(t);
            else if (t.length >= 2 && t.length <= 200) texts.push(t);
        }
        items.push({
            name: texts[0] || '', brand: texts.length > 1 ? texts[1] : '',
            price: prices[0] || '', original_price: prices.length > 1 ? prices[1] : '',
            image: img ? img.src : '', product_url: link ? link.href : ''
        });
    }
    if (items.length < 3) return null;
    return {count: bestCount, items: items};
})()"""

_JS_ANALYZE_BANNERS = """(() => {
    var results = [];
    var vpW = window.innerWidth;
    var sels = [
        '.swiper-container', '.swiper', '[class*="swiper"]',
        '.slick-slider', '[class*="carousel"]', '[class*="slider"]',
        '[class*="banner_slide"]', '[class*="main_visual"]',
        '[class*="hero"]', '[class*="main_banner"]',
        '[class*="key_visual"]', '[class*="top_banner"]',
    ];
    var seen = [];
    for (var i = 0; i < sels.length; i++) {
        try {
            var els = document.querySelectorAll(sels[i]);
            for (var j = 0; j < els.length; j++) {
                var r = els[j].getBoundingClientRect();
                if (r.width < vpW * 0.4 || r.height < 80) continue;
                if (r.top > window.innerHeight * 2) continue;
                var dup = seen.some(function(s) {
                    return Math.abs(s.w - r.width) < 50 && Math.abs(s.h - r.height) < 50;
                });
                if (dup) continue;
                seen.push({w: r.width, h: r.height});
                var isSlider = /swiper|slick|carousel|slider/i.test(sels[i]);
                results.push({
                    type: r.top < 400 ? 'hero' : 'sub_banner',
                    is_slider: isSlider,
                    width: Math.round(r.width),
                    height: Math.round(r.height)
                });
            }
        } catch(e) {}
    }
    return results.length > 0 ? results : null;
})()"""

_JS_ANALYZE_DIRECTORY = """(() => {
    /* 인덱스 탭 탐지 */
    var indexSels = [
        '[class*="brand"] [class*="index"]', '[class*="brand"] [class*="alpha"]',
        '[class*="alphabet"]', '[class*="initial"]',
    ];
    var hasIndex = false;
    for (var i = 0; i < indexSels.length; i++) {
        try {
            var els = document.querySelectorAll(indexSels[i] + ' a, ' + indexSels[i] + ' button');
            if (els.length >= 5) { hasIndex = true; break; }
        } catch(e) {}
    }

    /* 리스트 항목 탐지 */
    var listSels = [
        '[class*="brand"] [class*="list"] li',
        '[class*="brand"] [class*="item"]',
        '[class*="event"] [class*="list"] li',
        '[class*="event"] [class*="item"]',
    ];
    var bestCount = 0;
    var listType = 'unknown';
    for (var li = 0; li < listSels.length; li++) {
        try {
            var items = document.querySelectorAll(listSels[li]);
            if (items.length > bestCount) {
                bestCount = items.length;
                listType = /brand/i.test(listSels[li]) ? 'brand_directory' : 'event_list';
            }
        } catch(e) {}
    }

    if (bestCount < 3 && !hasIndex) return null;
    return { count: bestCount, has_index: hasIndex, list_type: listType };
})()"""
