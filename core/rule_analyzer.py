"""
규칙 기반 사이트 구조 분석기 (LLM 불필요)

사이트에 접속한 뒤 JS 전역 변수, 네트워크 요청, DOM 구조를 분석하여
플랫폼 감지 규칙과 추출 템플릿을 자동 생성한다.

분석 파이프라인:
  1단계: JS 전역 변수 탐지 → 프레임워크 감지 → state_var 전략 템플릿 생성
  2단계: 네트워크 요청 인터셉트 → API 엔드포인트 탐지 → api 전략 템플릿 생성
  3단계: DOM 반복 패턴 탐지 → dom 전략 템플릿 생성
  4단계: 키 이름 휴리스틱으로 표준 스키마에 자동 매핑

지원 프레임워크:
  - 네이버 스마트스토어 (__PRELOADED_STATE__)
  - Next.js SSR (__NEXT_DATA__)
  - Next.js RSC (__next_f)
  - Nuxt.js (__NUXT__, __pinia)
  - 서버 렌더링 (JSP/Spring 등) — DOM 전략
  - SPA (React/Vue 등) — API + DOM 전략
"""
import json
import re
from urllib.parse import urlparse

from playwright.sync_api import Page

from core.network_interceptor import NetworkInterceptor


# ═══════════════════════════════════════════════════════════════════
# 표준 필드 ↔ 키 이름 매칭 패턴
# ═══════════════════════════════════════════════════════════════════

_STORE_FIELD_PATTERNS = {
    "store_name": [
        "channelName", "storeName", "shopName", "brandName",
        "mallName", "companyName", "name",
    ],
    "store_id": [
        "channelId", "storeId", "shopId", "mallId", "id",
    ],
    "description": [
        "description", "storeDescription", "shopDescription",
        "introduce", "aboutUs",
    ],
    "representative": [
        "representName", "ceoName", "ownerName", "representative",
    ],
    "sale_count": [
        "saleCount", "totalSaleCount", "salesCount", "orderCount",
    ],
    "logo_url": [
        "representativeImageUrl", "logoUrl", "logoImageUrl",
        "profileImageUrl", "shopImageUrl",
    ],
    "address": [
        "fullAddressInfo", "basicAddress", "address",
        "businessAddress", "companyAddress",
    ],
    "phone": [
        "formattedNumber", "telNo", "phoneNumber", "contactNumber",
        "phone", "tel",
    ],
}

_PRODUCT_FIELD_PATTERNS = {
    "product_id": [
        "productNo", "productId", "goodsCd", "goodsNo",
        "itemId", "itemNo", "id",
    ],
    "product_name": [
        "name", "productName", "goodsNm", "goodsName",
        "itemName", "dispName", "title",
    ],
    "selling_price": [
        "salePrice", "sellingPrice", "sellPrice", "price",
        "finalPrice", "customerPrice",
    ],
    "original_price": [
        "originPrice", "normalPrice", "retailPrice",
        "listPrice", "regularPrice", "consumerPrice",
    ],
    "discount_rate": [
        "discountRate", "discountRatio", "discountedRatio",
        "discountPercent", "saleRate",
    ],
    "discounted_price": [
        "discountedSalePrice", "discountedPrice", "discountPrice",
        "memberPrice", "eventPrice",
    ],
    "image_url": [
        "representativeImageUrl", "imageUrl", "thumbnailUrl",
        "imgUrl", "mainImage", "productImage", "goodsImage",
    ],
    "review_count": [
        "totalReviewCount", "reviewCount", "reviewCnt",
        "reviewAmount", "commentCount",
    ],
    "average_score": [
        "averageReviewScore", "averageScore", "avgScore",
        "rating", "starScore", "score",
    ],
    "brand_name": [
        "brandName", "brand", "makerName", "manufacturer",
    ],
    "category_name": [
        "categoryName", "category", "cateName",
    ],
    "detail_text": [
        "detailContentText", "detailContent", "description",
        "goodsContent", "productDetail",
    ],
}

_CATEGORY_FIELD_PATTERNS = {
    "id": [
        "id", "catId", "cateId", "categoryNo",
    ],
    "name": [
        "categoryName", "cateName", "name", "label", "title",
    ],
}

# 루트 키 감지용 패턴

_STORE_ROOT_CANDIDATES = [
    "channel", "store", "shop", "seller", "merchant",
    "brand", "mall", "vendor",
]

_PRODUCT_ROOT_CANDIDATES = [
    "categoryProducts", "products", "productList",
    "goodsList", "items", "catalog", "searchProducts",
]

_CATEGORY_ROOT_CANDIDATES = [
    "categoryMenu", "categories", "categoryList",
    "navigation", "menu", "gnb",
]

_DETAIL_ROOT_CANDIDATES = [
    "product", "productDetail", "goodsDetail",
    "simpleProductForDetailPage", "itemDetail",
]

_PRODUCT_LIST_KEY_CANDIDATES = [
    "simpleProducts", "products", "productList", "list",
    "items", "goodsList", "content",
]

_CATEGORY_LIST_KEY_CANDIDATES = [
    "firstCategories", "categories", "categoryList",
    "subCategories", "children", "items", "list",
]

_KNOWN_STATE_VARS = [
    "__PRELOADED_STATE__", "__NEXT_DATA__", "__NUXT__",
    "__INITIAL_STATE__", "__APP_DATA__", "__STORE_STATE__",
    "__SSR_DATA__", "__APOLLO_STATE__", "Shopify",
    "__pinia", "__REACT_QUERY_STATE__",
]


# ═══════════════════════════════════════════════════════════════════
# 딥 스캔 JS — 브라우저에서 상세 구조를 수집
# ═══════════════════════════════════════════════════════════════════

_JS_DEEP_SCAN = """(varName) => {
    var state = window[varName];
    if (!state || typeof state !== 'object') return null;

    function scanObj(obj, depth) {
        if (depth > 3 || !obj || typeof obj !== 'object') return null;
        var result = {};
        var keys = Object.keys(obj);
        var limit = (depth === 0) ? keys.length : Math.min(keys.length, 30);
        for (var i = 0; i < limit; i++) {
            var k = keys[i];
            var v;
            try { v = obj[k]; } catch(e) { continue; }
            if (v === null || v === undefined) {
                result[k] = {type: 'null'};
            } else if (Array.isArray(v)) {
                var info = {type: 'array', length: v.length};
                if (v.length > 0 && typeof v[0] === 'object' && v[0] !== null) {
                    info.itemKeys = Object.keys(v[0]).slice(0, 30);
                    var sample = {};
                    var ik = info.itemKeys;
                    for (var j = 0; j < Math.min(ik.length, 20); j++) {
                        var sv = v[0][ik[j]];
                        if (sv === null || sv === undefined) {
                            sample[ik[j]] = null;
                        } else if (typeof sv === 'object' && !Array.isArray(sv)) {
                            sample[ik[j]] = '{' + Object.keys(sv).slice(0,10).join(',') + '}';
                        } else if (Array.isArray(sv)) {
                            sample[ik[j]] = '[len=' + sv.length + ']';
                        } else {
                            sample[ik[j]] = String(sv).substring(0, 80);
                        }
                    }
                    info.itemSample = sample;
                }
                result[k] = info;
            } else if (typeof v === 'object') {
                var subKeys = Object.keys(v).slice(0, 30);
                result[k] = {type: 'object', keys: subKeys};
                if (depth < 2) {
                    result[k].children = scanObj(v, depth + 1);
                }
            } else {
                var str = String(v);
                result[k] = {
                    type: typeof v,
                    sample: str.length > 80 ? str.substring(0, 80) + '...' : str
                };
            }
        }
        return result;
    }

    return scanObj(state, 0);
}"""

_JS_FIND_STATE_VARS = """() => {
    var found = [];
    var candidates = [
        '__PRELOADED_STATE__', '__NEXT_DATA__', '__NUXT__',
        '__INITIAL_STATE__', '__APP_DATA__', '__STORE_STATE__',
        '__SSR_DATA__', '__APOLLO_STATE__'
    ];
    for (var i = 0; i < candidates.length; i++) {
        try {
            if (window[candidates[i]] && typeof window[candidates[i]] === 'object') {
                found.push(candidates[i]);
            }
        } catch(e) {}
    }
    var allKeys = Object.keys(window);
    for (var j = 0; j < allKeys.length; j++) {
        var key = allKeys[j];
        try {
            if (key.indexOf('__') === 0 && key.length > 4
                && typeof window[key] === 'object' && window[key] !== null
                && found.indexOf(key) === -1) {
                var kc = Object.keys(window[key]).length;
                if (kc > 2 && kc < 200) {
                    found.push(key);
                }
            }
        } catch(e) {}
    }
    return found;
}"""


# ── 프레임워크별 딥 스캔 JS ──────────────────────────────────────

_JS_DEEP_SCAN_NEXTJS = """() => {
    var nd = window.__NEXT_DATA__;
    if (!nd || !nd.props || !nd.props.pageProps) return null;
    var pp = nd.props.pageProps;

    function scanObj(obj, depth) {
        if (depth > 3 || !obj || typeof obj !== 'object') return null;
        var result = {};
        var keys = Object.keys(obj);
        var limit = (depth === 0) ? keys.length : Math.min(keys.length, 30);
        for (var i = 0; i < limit; i++) {
            var k = keys[i];
            var v;
            try { v = obj[k]; } catch(e) { continue; }
            if (v === null || v === undefined) {
                result[k] = {type: 'null'};
            } else if (Array.isArray(v)) {
                var info = {type: 'array', length: v.length};
                if (v.length > 0 && typeof v[0] === 'object' && v[0] !== null) {
                    info.itemKeys = Object.keys(v[0]).slice(0, 30);
                    var sample = {};
                    var ik = info.itemKeys;
                    for (var j = 0; j < Math.min(ik.length, 20); j++) {
                        var sv = v[0][ik[j]];
                        if (sv === null || sv === undefined) {
                            sample[ik[j]] = null;
                        } else if (typeof sv === 'object' && !Array.isArray(sv)) {
                            sample[ik[j]] = '{' + Object.keys(sv).slice(0,10).join(',') + '}';
                        } else if (Array.isArray(sv)) {
                            sample[ik[j]] = '[len=' + sv.length + ']';
                        } else {
                            sample[ik[j]] = String(sv).substring(0, 80);
                        }
                    }
                    info.itemSample = sample;
                }
                result[k] = info;
            } else if (typeof v === 'object') {
                var subKeys = Object.keys(v).slice(0, 30);
                result[k] = {type: 'object', keys: subKeys};
                if (depth < 2) {
                    result[k].children = scanObj(v, depth + 1);
                }
            } else {
                var str = String(v);
                result[k] = {
                    type: typeof v,
                    sample: str.length > 80 ? str.substring(0, 80) + '...' : str
                };
            }
        }
        return result;
    }

    // pageProps 자체를 스캔
    var result = scanObj(pp, 0);

    // dehydratedState (React Query) 가 있으면 추가 탐색
    if (pp.dehydratedState && pp.dehydratedState.queries) {
        var queries = pp.dehydratedState.queries;
        var queryInfo = [];
        for (var q = 0; q < Math.min(queries.length, 10); q++) {
            var query = queries[q];
            var qi = {queryKey: null, dataKeys: null};
            try { qi.queryKey = JSON.stringify(query.queryKey); } catch(e) {}
            if (query.state && query.state.data && typeof query.state.data === 'object') {
                qi.dataKeys = Object.keys(query.state.data).slice(0, 20);
                qi.dataScan = scanObj(query.state.data, 1);
            }
            queryInfo.push(qi);
        }
        result['__dehydratedQueries'] = {type: 'array', length: queries.length,
                                          queries: queryInfo};
    }

    return result;
}"""

_JS_DEEP_SCAN_NUXT = """() => {
    var nuxt = window.__NUXT__;
    if (!nuxt) return null;

    function scanObj(obj, depth) {
        if (depth > 3 || !obj || typeof obj !== 'object') return null;
        var result = {};
        var keys = Object.keys(obj);
        var limit = (depth === 0) ? keys.length : Math.min(keys.length, 30);
        for (var i = 0; i < limit; i++) {
            var k = keys[i];
            var v;
            try { v = obj[k]; } catch(e) { continue; }
            if (v === null || v === undefined) {
                result[k] = {type: 'null'};
            } else if (Array.isArray(v)) {
                var info = {type: 'array', length: v.length};
                if (v.length > 0 && typeof v[0] === 'object' && v[0] !== null) {
                    info.itemKeys = Object.keys(v[0]).slice(0, 30);
                }
                result[k] = info;
            } else if (typeof v === 'object') {
                var subKeys = Object.keys(v).slice(0, 30);
                result[k] = {type: 'object', keys: subKeys};
                if (depth < 2) {
                    result[k].children = scanObj(v, depth + 1);
                }
            } else {
                result[k] = {type: typeof v, sample: String(v).substring(0, 80)};
            }
        }
        return result;
    }

    var result = {};

    // Nuxt 2: data, state
    if (nuxt.data && typeof nuxt.data === 'object') {
        result.data = scanObj(nuxt.data, 0);
    }
    if (nuxt.state && typeof nuxt.state === 'object') {
        result.state = scanObj(nuxt.state, 0);
    }

    // Nuxt 3: pinia stores
    if (nuxt.pinia && typeof nuxt.pinia === 'object') {
        result.pinia = scanObj(nuxt.pinia, 0);
    }

    // __pinia 별도 전역 변수
    if (window.__pinia && typeof window.__pinia === 'object') {
        var stores = window.__pinia;
        if (stores.state && stores.state.value) {
            result.piniaGlobal = scanObj(stores.state.value, 0);
        }
    }

    return result;
}"""

# ── DOM 분석 JS ──────────────────────────────────────────────────

_JS_DOM_PRODUCT_SCAN = """() => {
    var candidates = [];
    var priceEls = [];
    var allEls = document.querySelectorAll('*');
    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        var text = el.textContent || '';
        if (/\\d{1,3}(,\\d{3})+/.test(text) && el.children.length < 5) {
            priceEls.push(el);
        }
    }

    // CSS-in-JS 해시 감지: 순수 영문자 4-8자 + 대소문자 혼합 → 해시 가능성
    function isHashLikeClass(cls) {
        if (cls.length < 4 || cls.length > 8) return false;
        if (/[-_]/.test(cls)) return false;  // 하이픈/언더스코어 있으면 의미있는 이름
        if (/^[a-z]+$/.test(cls)) return false;  // 전체 소문자는 의미있는 이름
        // PascalCase 단일 단어 (Button, Price, Header, Card)
        if (/^[A-Z][a-z]+$/.test(cls)) return false;
        // 혼합 대소문자 → 해시 (EyWwa, ffXMhl, jAWGzh, gKBJNE)
        if (/[A-Z]/.test(cls) && /[a-z]/.test(cls)) return true;
        return false;
    }

    var parentClasses = {};
    for (var p = 0; p < priceEls.length; p++) {
        var parent = priceEls[p].parentElement;
        for (var depth = 0; depth < 6 && parent; depth++) {
            var cls = parent.className;
            if (typeof cls === 'string' && cls.trim()) {
                // 모든 클래스를 순회 (firstCls 대신)
                var allClasses = cls.trim().split(/\\s+/);
                for (var ci = 0; ci < allClasses.length; ci++) {
                    var clsItem = allClasses[ci];
                    // sc-* (styled-components), sdui-* (SDUI 프레임워크) 스킵
                    if (clsItem.indexOf('sc-') === 0 || clsItem.indexOf('sdui-') === 0) continue;
                    // styled-components BEM 해시 스킵 (Component-sc-HASH)
                    if (/-sc-[a-z0-9]/.test(clsItem)) continue;
                    // CSS-in-JS 해시 스킵
                    if (isHashLikeClass(clsItem)) continue;
                    var key = parent.tagName.toLowerCase() + '.' + clsItem;
                    parentClasses[key] = (parentClasses[key] || 0) + 1;
                }
            }
            parent = parent.parentElement;
        }
    }

    // 유틸리티 CSS 클래스 블랙리스트 (Tailwind, Bootstrap, 공통 UI, SDUI)
    var utilityClasses = [
        'flex', 'block', 'grid', 'hidden', 'relative', 'absolute', 'fixed',
        'inline', 'static', 'sticky', 'overflow', 'container', 'wrapper',
        'row', 'col', 'column', 'section', 'main', 'header', 'footer',
        'swiper-slide', 'swiper-wrapper', 'slick-slide', 'slick-list',
        'carousel-item', 'tab-pane', 'tab-content', 'modal', 'dropdown',
        'w-full', 'h-full', 'mx-auto', 'my-auto', 'px-4', 'py-4',
        'items-center', 'justify-center', 'text-center',
        'cursor-pointer', 'pointer-events-auto', 'pointer-events-none',
    ];
    // 유틸리티 접두사 (prefix) 패턴
    var utilityPrefixes = [
        'pc:', 'tablet:', 'mo:', 'sdui-', 'sc-',
        'layout_', 'layout-',
        'flex-', 'grid-',
        'list-vertical', 'list-horizontal',
        'bullet-pagination',
        'flicking-', 'swiper-', 'slick-',
        // Tailwind CSS 유틸리티 접두사
        'pl-', 'pr-', 'pt-', 'pb-', 'px-', 'py-', 'p-',
        'ml-', 'mr-', 'mt-', 'mb-', 'mx-', 'my-', 'm-',
        'w-', 'h-', 'min-w-', 'min-h-', 'max-w-', 'max-h-',
        'bg-', 'text-', 'font-', 'rounded-', 'border-',
        'shadow-', 'overflow-', 'z-', 'gap-',
        'col-', 'row-', 'items-', 'justify-', 'self-',
        'opacity-', 'transition-', 'duration-', 'ease-',
        'top-', 'bottom-', 'left-', 'right-', 'inset-',
        'space-', 'divide-', 'ring-', 'outline-',
        'order-', 'grow-', 'shrink-', 'basis-',
        // Analytics 접두사 (gtm-은 안정적 트래킹 클래스로 유지)
        'ga-', 'gtag-',
    ];
    // 짧은 유틸리티 패턴: "xx-숫자" (예: pl-3, mt-4, z-10)
    var shortUtilityPattern = /^[a-z]{1,4}-\\d+$/;

    for (var ck in parentClasses) {
        if (parentClasses[ck] >= 3) {
            var dotIdx = ck.indexOf('.');
            var clsName = ck.substring(dotIdx + 1);

            // CSS 선택자에 안전하지 않은 문자 스킵
            if (/[^a-zA-Z0-9_-]/.test(clsName)) continue;

            // 유틸리티 클래스 스킵
            var isUtility = false;
            for (var ui = 0; ui < utilityClasses.length; ui++) {
                if (clsName === utilityClasses[ui]) { isUtility = true; break; }
            }
            if (!isUtility) {
                var clsLow = clsName.toLowerCase();
                for (var upi = 0; upi < utilityPrefixes.length; upi++) {
                    if (clsLow.indexOf(utilityPrefixes[upi]) === 0) { isUtility = true; break; }
                }
            }
            // 짧은 유틸리티 패턴 (pl-3, mt-4, z-10 등)
            if (!isUtility && shortUtilityPattern.test(clsName)) {
                isUtility = true;
            }
            if (isUtility) continue;

            var sampleEls;
            try { sampleEls = document.querySelectorAll('.' + clsName); }
            catch(e) { continue; }

            var totalEls = sampleEls.length;
            var priceCount = parentClasses[ck];

            if (totalEls < 3) continue;  // 반복 패턴 아님

            // 먼저 img/link 정보를 확인 (ratio 판단에 필요)
            var sampleEl = sampleEls[0];
            var childInfo = {};
            if (sampleEl) {
                var imgs = sampleEl.querySelectorAll('img');
                var links = sampleEl.querySelectorAll('a[href]');
                // 카드 자체가 <a> 태그인 경우 (예: KREAM product_card)
                var selfIsLink = sampleEl.tagName.toLowerCase() === 'a' && sampleEl.hasAttribute('href');
                childInfo = {
                    hasImg: imgs.length > 0,
                    imgSelector: imgs.length > 0 ? _getSelector(imgs[0]) : '',
                    hasLink: links.length > 0 || selfIsLink,
                    selfIsLink: selfIsLink,
                    linkHrefs: [],
                    linkSelector: selfIsLink ? ':scope' : (links.length > 0 ? _getSelector(links[0]) : ''),
                    dataAttrs: {},
                };
                if (selfIsLink) {
                    childInfo.linkHrefs.push(sampleEl.getAttribute('href'));
                }
                for (var li = 0; li < Math.min(links.length, 3); li++) {
                    childInfo.linkHrefs.push(links[li].getAttribute('href'));
                }
                var attrs = sampleEl.attributes;
                for (var ai = 0; ai < attrs.length; ai++) {
                    var an = attrs[ai].name;
                    if (an.indexOf('data-') === 0) {
                        childInfo.dataAttrs[an] = attrs[ai].value.substring(0, 50);
                    }
                }
            }

            // 상품 카드는 반드시 img 또는 link 를 포함해야 함
            // 가격 텍스트만 있는 요소 (예: .tx_cur) 는 카드가 아닌 가격 셀
            if (!childInfo.hasImg && !childInfo.hasLink) continue;

            // 컨테이너 필터: ratio = totalEls / priceCount
            // 상품 카드: 각 카드에 1-2개 가격 → ratio ≈ 0.5~1.0
            // Tailwind 카드: 카드당 다수 가격 텍스트 → ratio ≈ 0.1~0.3
            // 컨테이너: 1-2개 래퍼가 모든 가격 포함 → ratio < 0.05
            var ratio = totalEls / priceCount;
            if (childInfo.hasImg && childInfo.hasLink) {
                // img+link 모두 있으면 상품 카드 가능성 높음 → 더 관대한 기준
                if (ratio < 0.05) continue;
            } else {
                // img 또는 link 만 있으면 기존 기준 유지
                if (ratio < 0.15) continue;
            }

            // 스코어 계산: 카드 특성(img+link 보유, ratio≈0.5~1.0)을 가진 반복 요소 우선
            var ratioScore;
            if (ratio >= 0.3 && ratio <= 1.5) {
                ratioScore = 1.0;  // 이상적 범위: 카드당 1~2개 가격
            } else if (ratio > 1.5) {
                ratioScore = 1.0 / ratio;  // 가격 없는 요소가 많음 → 패널티
            } else {
                ratioScore = ratio;  // 가격이 너무 많음 → 패널티
            }
            var score = totalEls * ratioScore;
            // 이미지+링크 모두 있으면 상품 카드 확실 (5x)
            if (childInfo.hasImg && childInfo.hasLink) {
                score = score * 5.0;
            } else if (childInfo.hasImg || childInfo.hasLink) {
                score = score * 2.0;
            }

            candidates.push({
                selector: ck,
                className: clsName,
                count: priceCount,
                totalElements: totalEls,
                ratio: Math.round(ratio * 100) / 100,
                score: Math.round(score * 100) / 100,
                sample: childInfo,
            });
        }
    }

    // === 속성 기반 카드 감지 (class 기반 후보가 부족한 경우) ===
    // data-item-id, data-product-id 등의 속성, 또는 a[href*="/product"] 패턴
    if (candidates.length === 0 || (candidates[0] && candidates[0].score < 20)) {
        var attrPatterns = [
            {sel: '[data-item-id]', name: 'data-item-id'},
            {sel: '[data-product-id]', name: 'data-product-id'},
            {sel: '[data-goods-id]', name: 'data-goods-id'},
            {sel: '[data-goods-no]', name: 'data-goods-no'},
        ];
        for (var api = 0; api < attrPatterns.length; api++) {
            var ap = attrPatterns[api];
            try {
                var attrEls = document.querySelectorAll(ap.sel);
                if (attrEls.length >= 5) {
                    var sEl = attrEls[0];
                    var sImgs = sEl.querySelectorAll('img');
                    var sLinks = sEl.querySelectorAll('a[href]');
                    var sSelfLink = sEl.tagName.toLowerCase() === 'a' && sEl.hasAttribute('href');

                    if (sImgs.length > 0 || sLinks.length > 0 || sSelfLink) {
                        var aScore = attrEls.length * 3;
                        candidates.push({
                            selector: ap.sel,
                            className: ap.sel,
                            count: attrEls.length,
                            totalElements: attrEls.length,
                            ratio: 1.0,
                            score: aScore,
                            sample: {
                                hasImg: sImgs.length > 0,
                                hasLink: sLinks.length > 0 || sSelfLink,
                                selfIsLink: sSelfLink,
                                linkSelector: sSelfLink ? ':scope' : (sLinks.length > 0 ? _getSelector(sLinks[0]) : ''),
                                imgSelector: sImgs.length > 0 ? _getSelector(sImgs[0]) : '',
                                dataAttrs: {},
                                isAttrBased: true,
                            },
                        });
                    }
                }
            } catch(e) {}
        }
    }

    // 스코어 기준 정렬 (컨테이너가 아닌 실제 상품 카드 우선)
    candidates.sort(function(a, b) { return b.score - a.score; });
    return candidates.slice(0, 8);

    function _getSelector(el) {
        if (el.id) return '#' + el.id;
        var cls = el.className;
        if (typeof cls === 'string' && cls.trim()) {
            return el.tagName.toLowerCase() + '.' + cls.trim().split(/\\s+/)[0];
        }
        return el.tagName.toLowerCase();
    }
}"""

_JS_DOM_CATEGORY_SCAN = """() => {
    var candidates = [];
    var navEls = document.querySelectorAll(
        'nav, [class*="cate"], [class*="menu"], [class*="gnb"], '
        + '[class*="tab"], [class*="nav"], [role="navigation"]'
    );

    for (var i = 0; i < navEls.length; i++) {
        var nav = navEls[i];
        var links = nav.querySelectorAll('a[href]');
        if (links.length < 2 || links.length > 100) continue;

        var hrefs = [];
        var texts = [];
        for (var j = 0; j < Math.min(links.length, 15); j++) {
            var href = links[j].getAttribute('href') || '';
            var text = (links[j].textContent || '').trim();
            if (href && text && text.length < 30) {
                hrefs.push(href);
                texts.push(text);
            }
        }
        if (hrefs.length < 2) continue;

        var cls = nav.className;
        var navSelector = '';
        if (typeof cls === 'string' && cls.trim()) {
            navSelector = '.' + cls.trim().split(/\\s+/)[0];
        } else if (nav.id) {
            navSelector = '#' + nav.id;
        } else {
            navSelector = nav.tagName.toLowerCase();
        }

        candidates.push({
            selector: navSelector,
            linkCount: hrefs.length,
            hrefs: hrefs,
            texts: texts,
        });
    }

    candidates.sort(function(a, b) { return b.linkCount - a.linkCount; });
    return candidates.slice(0, 5);
}"""

_JS_DOM_PAGINATION_SCAN = """() => {
    var result = {type: null, details: {}};

    // 1. 페이지 번호 링크
    var pagingEl = document.querySelector(
        '[class*="pagination"], [class*="paging"], [class*="pageing"],'
        + ' nav[aria-label*="page"], [class*="page_nav"]'
    );
    if (pagingEl) {
        var pageLinks = pagingEl.querySelectorAll('a[href]');
        result.type = 'url_param';
        result.details.selector = _getSelector(pagingEl);
        result.details.linkCount = pageLinks.length;
        if (pageLinks.length > 0) {
            var href = pageLinks[pageLinks.length - 1].getAttribute('href') || '';
            result.details.sampleHref = href;
        }
        return result;
    }

    // 2. 다음 버튼
    var nextBtn = document.querySelector(
        'a[class*="next"], button[class*="next"],'
        + ' [class*="btn_next"], [aria-label="next"],'
        + ' [class*="arrow_next"]'
    );
    if (nextBtn) {
        result.type = 'click';
        result.details.selector = _getSelector(nextBtn);
        return result;
    }

    // 3. 더보기 버튼
    var moreBtn = document.querySelector(
        'button[class*="more"], a[class*="more"],'
        + ' [class*="load_more"], [class*="loadmore"],'
        + ' [class*="view_more"], [class*="viewmore"]'
    );
    if (moreBtn) {
        result.type = 'click';
        result.details.selector = _getSelector(moreBtn);
        return result;
    }

    // 4. 무한 스크롤 표시
    var scrollSentinel = document.querySelector(
        '[class*="infinite"], [class*="sentinel"],'
        + ' [class*="scroll_load"], [data-infinite],'
        + ' [class*="observe"]'
    );
    if (scrollSentinel) {
        result.type = 'scroll';
        return result;
    }

    return result;

    function _getSelector(el) {
        if (el.id) return '#' + el.id;
        var cls = el.className;
        if (typeof cls === 'string' && cls.trim()) {
            return '.' + cls.trim().split(/\\s+/)[0];
        }
        return el.tagName.toLowerCase();
    }
}"""

_JS_DOM_STORE_SCAN = """() => {
    var result = {};
    result.title = document.title || '';

    // og 메타
    var ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) result.og_title = ogTitle.getAttribute('content') || '';
    var ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) result.og_description = ogDesc.getAttribute('content') || '';
    var ogImage = document.querySelector('meta[property="og:image"]');
    if (ogImage) result.og_image = ogImage.getAttribute('content') || '';

    // h1
    var h1 = document.querySelector('h1');
    if (h1) result.h1 = h1.textContent.trim().substring(0, 100);

    // 로고
    var logo = document.querySelector(
        '[class*="logo"] img, header img, [class*="brand"] img'
    );
    if (logo) result.logo_url = logo.getAttribute('src') || '';

    return result;
}"""

_JS_DOM_DETAIL_URL_SCAN = """() => {
    // 상품 링크에서 URL 패턴 추출
    var links = document.querySelectorAll('a[href]');
    var productUrls = [];
    for (var i = 0; i < links.length; i++) {
        var href = links[i].getAttribute('href') || '';
        var lower = href.toLowerCase();
        if (lower.indexOf('product') > -1 || lower.indexOf('goods') > -1
            || lower.indexOf('item') > -1 || lower.indexOf('detail') > -1) {
            if (href.indexOf('javascript:') === -1 && href.length > 5) {
                productUrls.push(href.substring(0, 200));
            }
        }
    }

    // data 속성에서 상품 ID 패턴 탐색
    var dataProductIds = [];
    var withData = document.querySelectorAll(
        '[data-product-id], [data-goods-no], [data-item-id],'
        + ' [data-product-no], [data-goodsno], [data-no]'
    );
    for (var j = 0; j < Math.min(withData.length, 10); j++) {
        var el = withData[j];
        var attrs = el.attributes;
        for (var k = 0; k < attrs.length; k++) {
            if (attrs[k].name.indexOf('data-') === 0
                && (attrs[k].name.indexOf('product') > -1
                    || attrs[k].name.indexOf('goods') > -1
                    || attrs[k].name.indexOf('item') > -1)) {
                dataProductIds.push({
                    attr: attrs[k].name,
                    value: attrs[k].value.substring(0, 50)
                });
            }
        }
    }

    return {
        productUrls: productUrls.slice(0, 20),
        dataProductIds: dataProductIds.slice(0, 10),
    };
}"""

_JS_DOM_CARD_FIELDS_SCAN = """(cardClass) => {
    // 상품 카드 내부 구조를 분석하여 최적 필드 셀렉터를 찾는다.
    // 속성 셀렉터([data-*])인 경우 그대로 사용, 클래스인 경우 .접두사 추가
    var cardSelector = cardClass.indexOf('[') === 0 ? cardClass : ('.' + cardClass);
    var cards = document.querySelectorAll(cardSelector);
    if (cards.length === 0) return null;

    // CSS 셀렉터로 사용 불가능한 클래스명 체크 (Tailwind [] 등)
    function isSafeClass(cls) {
        if (!cls || typeof cls !== 'string') return false;
        return !/[\\[\\](){}!@#$%^&*+=<>~`|]/.test(cls);
    }

    // CSS-in-JS 해시 감지 (styled-components 등)
    function isHashClass(cls) {
        // styled-components BEM 해시: ComponentName-sc-HASH
        if (/-sc-[a-z0-9]/.test(cls)) return true;
        if (cls.length < 4 || cls.length > 8) return false;
        if (/[-_]/.test(cls)) return false;
        if (/^[a-z]+$/.test(cls)) return false;
        // PascalCase 단일 단어 (Button, Price, Header, Card)
        if (/^[A-Z][a-z]+$/.test(cls)) return false;
        // 혼합 대소문자 → 해시 (EyWwa, ffXMhl, jAWGzh, gKBJNE)
        if (/[A-Z]/.test(cls) && /[a-z]/.test(cls)) return true;
        return false;
    }

    // 유틸리티 접두사 (SDUI, styled-components, Tailwind 등)
    var skipPrefixes = [
        'sc-', 'sdui-', 'pc:', 'tablet:', 'mo:',
        'pl-', 'pr-', 'pt-', 'pb-', 'px-', 'py-', 'p-',
        'ml-', 'mr-', 'mt-', 'mb-', 'mx-', 'my-', 'm-',
        'w-', 'h-', 'bg-', 'text-', 'font-', 'rounded-',
        'border-', 'shadow-', 'z-', 'gap-',
    ];
    var shortUtilPattern = /^[a-z]{1,4}-\\d+$/;

    // 안전한 CSS 셀렉터 생성 (가장 안정적인 클래스 선택)
    function safeCls(el) {
        var cls = el.className || '';
        if (typeof cls !== 'string') return '';
        var classes = cls.trim().split(/\\s+/);
        // 안정적인 클래스 우선: 유틸리티 접두사 제외, 해시 제외, CSS-안전한 클래스
        for (var i = 0; i < classes.length; i++) {
            var c = classes[i];
            if (!c) continue;
            var skip = false;
            for (var sp = 0; sp < skipPrefixes.length; sp++) {
                if (c.indexOf(skipPrefixes[sp]) === 0) { skip = true; break; }
            }
            if (skip) continue;
            if (shortUtilPattern.test(c)) continue;
            if (isHashClass(c)) continue;
            if (!isSafeClass(c)) continue;
            return c;
        }
        return '';
    }

    // 특정 패턴을 포함하는 안정적인 클래스 찾기 (더 구체적인 클래스 우선)
    function safeClsWithPattern(el, patterns) {
        var cls = el.className || '';
        if (typeof cls !== 'string') return '';
        var classes = cls.trim().split(/\\s+/);
        // 패턴 매칭된 안정적 클래스 수집 (모두)
        var matches = [];
        for (var i = 0; i < classes.length; i++) {
            var c = classes[i];
            if (!c) continue;
            var skip = false;
            for (var sp = 0; sp < skipPrefixes.length; sp++) {
                if (c.indexOf(skipPrefixes[sp]) === 0) { skip = true; break; }
            }
            if (skip) continue;
            if (shortUtilPattern.test(c)) continue;
            if (isHashClass(c)) continue;
            if (!isSafeClass(c)) continue;
            var cLow = c.toLowerCase();
            for (var p = 0; p < patterns.length; p++) {
                if (cLow.indexOf(patterns[p]) > -1) {
                    matches.push(c);
                    break;
                }
            }
        }
        if (matches.length === 0) return safeCls(el);
        // 더 구체적인(긴) 클래스 우선 (예: prdc-price > price)
        matches.sort(function(a, b) { return b.length - a.length; });
        return matches[0];
    }

    // 최대 3개 카드 샘플링
    var namePatterns = ['name', 'title', 'product', 'goods', 'item'];
    var pricePatterns = ['price', 'won', 'cost', 'amount'];
    var curPricePatterns = ['cur', 'sell', 'sale', 'final', 'discount'];
    var orgPricePatterns = ['org', 'origin', 'normal', 'regular', 'list', 'before'];
    var brandPatterns = ['brand', 'maker', 'vendor', 'manufacturer'];

    var result = {
        nameSelector: null,
        priceSelector: null,
        orgPriceSelector: null,
        brandSelector: null,
        linkSelector: null,
        imgSelector: null,
        nameSamples: [],
        priceSamples: [],
    };

    // 첫 번째 카드에서 내부 요소 분석
    var card = cards[0];
    var allEls = card.querySelectorAll('*');
    var nameCands = [];
    var priceCands = [];
    var orgPriceCands = [];
    var brandCands = [];
    var linkCands = [];

    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        var cls = el.className || '';
        if (typeof cls !== 'string') cls = '';
        var clsLower = cls.toLowerCase();
        var tag = el.tagName.toLowerCase();
        var text = (el.textContent || '').trim();

        // CSS에 안전한 첫 클래스
        var sc = safeCls(el);

        // 이름 후보: class에 name/title 포함 + 텍스트 5자 이상
        for (var ni = 0; ni < namePatterns.length; ni++) {
            if (clsLower.indexOf(namePatterns[ni]) > -1 && text.length >= 5) {
                var nameCls = safeClsWithPattern(el, namePatterns);
                if (nameCls) {
                    nameCands.push({
                        selector: tag + '.' + nameCls,
                        text: text.substring(0, 80),
                        priority: ni,
                        childCount: el.children.length,
                    });
                    break;
                }
            }
        }

        // 가격 후보: class에 price/cur/sell 포함 + 숫자,숫자 패턴
        if (/\\d{1,3}(,\\d{3})+/.test(text)) {
            var isOrgPrice = false;
            var isCurPrice = false;

            for (var oi = 0; oi < orgPricePatterns.length; oi++) {
                if (clsLower.indexOf(orgPricePatterns[oi]) > -1) {
                    isOrgPrice = true;
                    break;
                }
            }
            for (var ci = 0; ci < curPricePatterns.length; ci++) {
                if (clsLower.indexOf(curPricePatterns[ci]) > -1) {
                    isCurPrice = true;
                    break;
                }
            }

            var isGenericPrice = false;
            for (var pi = 0; pi < pricePatterns.length; pi++) {
                if (clsLower.indexOf(pricePatterns[pi]) > -1) {
                    isGenericPrice = true;
                    break;
                }
            }

            // 패턴 매칭된 안정적 클래스를 셀렉터로 사용
            var allPricePatterns = pricePatterns.concat(curPricePatterns).concat(orgPricePatterns);
            var priceCls = safeClsWithPattern(el, allPricePatterns);
            if (priceCls) {
                var pSel = tag + '.' + priceCls;
                var entry = {selector: pSel, text: text.substring(0, 40),
                             childCount: el.children.length};

                if (isOrgPrice) {
                    orgPriceCands.push(entry);
                } else if (isCurPrice) {
                    priceCands.push(entry);
                } else if (isGenericPrice) {
                    priceCands.push(entry);
                }
            }
        }

        // 브랜드 후보: class 기반
        for (var bi = 0; bi < brandPatterns.length; bi++) {
            if (clsLower.indexOf(brandPatterns[bi]) > -1 && text.length >= 1 && text.length < 40) {
                var brandCls = safeClsWithPattern(el, brandPatterns);
                if (brandCls) {
                    brandCands.push({
                        selector: tag + '.' + brandCls,
                        text: text.substring(0, 40),
                    });
                    break;
                }
            }
        }

        // 브랜드 후보: href 기반 (/brand/ 링크)
        if (tag === 'a' && text.length >= 1 && text.length < 40) {
            var brandHref = (el.getAttribute('href') || '').toLowerCase();
            if (brandHref.indexOf('/brand') > -1 && brandHref.indexOf('/products') === -1) {
                var brandLinkCls = safeCls(el);
                var brandLinkSel = brandLinkCls ? 'a.' + brandLinkCls : 'a[href*="/brand"]';
                brandCands.push({
                    selector: brandLinkSel,
                    text: text.substring(0, 40),
                });
            }
        }

        // 링크 후보: href에 product/goods/detail/item 포함
        if (tag === 'a') {
            var href = el.getAttribute('href') || '';
            var hrefLower = href.toLowerCase();
            if (hrefLower.indexOf('product') > -1 || hrefLower.indexOf('goods') > -1
                || hrefLower.indexOf('detail') > -1 || hrefLower.indexOf('item') > -1) {
                var linkSel = sc ? 'a.' + sc : 'a[href*="product"], a[href*="goods"], a[href*="detail"]';
                var hasImgChild = el.querySelector('img') != null;
                linkCands.push({
                    selector: linkSel,
                    href: href.substring(0, 200),
                    textLen: text.length,
                    hasImg: hasImgChild,
                });
            }
        }
    }

    // 카드 자체가 <a> 태그인 경우 (예: KREAM product_card)
    if (card.tagName.toLowerCase() === 'a' && card.hasAttribute('href')) {
        var cardHref = card.getAttribute('href') || '';
        var cardHrefLower = cardHref.toLowerCase();
        if (cardHrefLower.indexOf('product') > -1 || cardHrefLower.indexOf('goods') > -1
            || cardHrefLower.indexOf('detail') > -1 || cardHrefLower.indexOf('item') > -1) {
            linkCands.push({
                selector: ':self',
                href: cardHref.substring(0, 200),
                textLen: (card.textContent || '').trim().length,
                isSelf: true,
            });
        }
    }

    // 이름: children이 적은(leaf) 요소 우선, priority 순
    nameCands.sort(function(a, b) {
        if (a.childCount !== b.childCount) return a.childCount - b.childCount;
        return a.priority - b.priority;
    });
    if (nameCands.length > 0) {
        var bestNameSel = nameCands[0].selector;
        // 셀렉터가 카드 내 여러 요소에 매칭되면 이미지 래핑 요소 제외
        try {
            var nameMatchEls = card.querySelectorAll(bestNameSel);
            if (nameMatchEls.length > 1) {
                var hasImgWrapper = false;
                for (var nmi = 0; nmi < nameMatchEls.length; nmi++) {
                    if (nameMatchEls[nmi].querySelector('img')) {
                        hasImgWrapper = true;
                        break;
                    }
                }
                if (hasImgWrapper && bestNameSel.indexOf(',') === -1) {
                    bestNameSel = bestNameSel + ':not(:has(img))';
                }
            }
        } catch(e) {}
        result.nameSelector = bestNameSel;
    }

    // 가격: children이 적은(leaf) 요소 우선
    priceCands.sort(function(a, b) { return a.childCount - b.childCount; });
    if (priceCands.length > 0) {
        result.priceSelector = priceCands[0].selector;
    }

    // 원래 가격
    orgPriceCands.sort(function(a, b) { return a.childCount - b.childCount; });
    if (orgPriceCands.length > 0) {
        result.orgPriceSelector = orgPriceCands[0].selector;
    }

    // 브랜드
    if (brandCands.length > 0) {
        result.brandSelector = brandCands[0].selector;
    }

    // 링크: 텍스트가 긴 링크 우선 (상품명 포함)
    linkCands.sort(function(a, b) { return b.textLen - a.textLen; });
    if (linkCands.length > 0) {
        result.linkSelector = linkCands[0].selector;
    }

    // 이미지
    var imgs = card.querySelectorAll('img[src]');
    if (imgs.length > 0) {
        result.imgSelector = 'img';
    }

    // ── 폴백: 시맨틱 클래스가 없는 경우 텍스트/구조 기반 추론 ──
    // 상품명: 이미지 없는 링크(텍스트 링크) 우선 선택
    if (!result.nameSelector && linkCands.length > 0) {
        // 이미지 없고 텍스트 5자 이상인 링크 찾기
        var textLink = null;
        for (var tli = 0; tli < linkCands.length; tli++) {
            if (!linkCands[tli].hasImg && linkCands[tli].textLen > 5) {
                textLink = linkCands[tli];
                break;
            }
        }
        if (textLink) {
            var nameLinkSel = textLink.selector;
            // 같은 셀렉터로 이미지 링크도 존재하면 :not(:has(img)) 추가
            var imgLinkExists = false;
            for (var ili = 0; ili < linkCands.length; ili++) {
                if (linkCands[ili].hasImg && linkCands[ili].selector === nameLinkSel) {
                    imgLinkExists = true;
                    break;
                }
            }
            if (imgLinkExists && nameLinkSel.indexOf(',') === -1) {
                nameLinkSel = nameLinkSel + ':not(:has(img))';
            }
            result.nameSelector = nameLinkSel;
        } else {
            result.nameSelector = linkCands[0].selector;
        }
    }

    // 가격: 시맨틱 클래스 없으면 가격 패턴을 가진 리프 요소 탐색
    if (!result.priceSelector) {
        var priceLeaves = [];
        for (var pi2 = 0; pi2 < allEls.length; pi2++) {
            var pe = allEls[pi2];
            var pt = (pe.textContent || '').trim();
            // 리프 요소에서 "숫자,숫자원" 또는 "숫자,숫자" 패턴
            if (pe.children.length === 0 && /^[\\d,]+원?$/.test(pt) && pt.length >= 4) {
                var psc = safeCls(pe);
                if (psc) {
                    priceLeaves.push({
                        selector: pe.tagName.toLowerCase() + '.' + psc,
                        text: pt
                    });
                }
            }
        }
        if (priceLeaves.length > 0) {
            result.priceSelector = priceLeaves[0].selector;
        }
    }

    // ── 교차 검증: 셀렉터가 여러 카드에서 일관되게 동작하는지 확인 ──
    function validateSelector(sel, sampleCards) {
        if (!sel) return 0;
        var hits = 0;
        for (var vi = 0; vi < sampleCards.length; vi++) {
            try {
                if (sampleCards[vi].querySelector(sel)) hits++;
            } catch(e) {}
        }
        return hits;
    }

    // 검증용 카드 샘플 (최대 5개, 균일 분포)
    var sampleCards = [];
    var step = Math.max(1, Math.floor(cards.length / 5));
    for (var sci = 0; sci < cards.length && sampleCards.length < 5; sci += step) {
        sampleCards.push(cards[sci]);
    }
    var minHits = Math.ceil(sampleCards.length * 0.6);  // 60% 이상 통과 필요

    // 이름 셀렉터 검증 → 실패 시 후보에서 대안 선택
    if (result.nameSelector) {
        var nameHits = validateSelector(result.nameSelector, sampleCards);
        if (nameHits < minHits && nameCands.length > 1) {
            for (var nci = 1; nci < nameCands.length; nci++) {
                var altHits = validateSelector(nameCands[nci].selector, sampleCards);
                if (altHits >= minHits) {
                    result.nameSelector = nameCands[nci].selector;
                    break;
                }
            }
        }
    }

    // 가격 셀렉터 검증
    if (result.priceSelector) {
        var priceHits = validateSelector(result.priceSelector, sampleCards);
        if (priceHits < minHits && priceCands.length > 1) {
            for (var pci = 1; pci < priceCands.length; pci++) {
                var altPHits = validateSelector(priceCands[pci].selector, sampleCards);
                if (altPHits >= minHits) {
                    result.priceSelector = priceCands[pci].selector;
                    break;
                }
            }
        }
    }

    // 디버그: 후보 + 검증 결과
    result._debug = {
        priceCandCount: priceCands.length,
        priceCands: priceCands.slice(0, 3).map(function(c) { return c.selector; }),
        sampleCardCount: sampleCards.length,
        minHits: minHits,
    };

    // 여러 카드에서 샘플 수집
    for (var si = 0; si < Math.min(cards.length, 3); si++) {
        if (result.nameSelector) {
            try {
                var nEl = cards[si].querySelector(result.nameSelector);
                if (nEl) result.nameSamples.push((nEl.textContent || '').trim().substring(0, 60));
            } catch(e) {}
        }
        if (result.priceSelector) {
            try {
                var pEl = cards[si].querySelector(result.priceSelector);
                if (pEl) result.priceSamples.push((pEl.textContent || '').trim().substring(0, 30));
            } catch(e) {}
        }
    }

    return result;
}"""


# ═══════════════════════════════════════════════════════════════════
# 규칙 기반 분석기
# ═══════════════════════════════════════════════════════════════════

class RuleAnalyzer:
    """
    규칙 기반 사이트 구조 분석기.
    JS 전역 변수 + 네트워크 요청 + DOM 패턴을 분석하여
    플랫폼 감지 규칙 + 추출 템플릿을 자동 생성한다.
    """

    def analyze(
        self, page: Page, site_url: str,
        captured_requests: list[dict] | None = None,
    ) -> dict | None:
        """
        사이트를 분석하여 platform + templates 딕셔너리를 반환한다.

        Args:
            page: 이미 사이트에 접속한 Playwright 페이지
            site_url: 사이트 URL
            captured_requests: NetworkInterceptor 가 수집한 요청 목록 (선택)

        Returns:
            {"platform": {...}, "templates": [...]} 또는 실패 시 None
        """
        print("[analyzer] 사이트 구조 분석 시작...")

        domain = urlparse(site_url).hostname or ""
        templates = []

        # 1단계: JS 전역 변수 기반 분석 (프레임워크 감지 포함)
        framework = self._detect_framework(page)
        print(f"[analyzer] 프레임워크: {framework}")

        state_templates = self._analyze_state_var_multi(
            page, site_url, framework,
        )
        if state_templates:
            templates.extend(state_templates)

        # 2단계: 네트워크 요청 기반 API 분석
        if captured_requests is not None:
            interceptor = NetworkInterceptor()
            interceptor.captured = captured_requests
        else:
            interceptor = None

        if interceptor:
            api_templates = self._analyze_api(interceptor, site_url)
            if api_templates:
                # state_var 로 이미 만든 target 과 중복 제거
                existing_targets = {t["target"] for t in templates}
                for at in api_templates:
                    if at["target"] not in existing_targets:
                        templates.append(at)
                        existing_targets.add(at["target"])

        # 3단계: DOM 기반 분석
        # DOM product_list 는 API 보다 낮은 우선순위로 저장 (폴백)
        dom_templates = self._analyze_dom_enhanced(page, site_url)
        if dom_templates:
            existing_targets = {t["target"] for t in templates}
            for dt in dom_templates:
                if dt["target"] not in existing_targets:
                    templates.append(dt)
                    existing_targets.add(dt["target"])
                elif dt["target"] == "product_list":
                    # API product_list 가 이미 있어도 DOM 을 폴백으로 저장
                    dt["target"] = "product_list_dom"
                    templates.append(dt)

        # 4단계: product_list 유효성 검증 + 상품 페이지 자동 탐색
        product_tmpl = None
        for t in templates:
            if t["target"] in ("product_list", "product_list_dom"):
                product_tmpl = t
                break

        need_discovery = product_tmpl is None
        if product_tmpl and product_tmpl["strategy"] == "dom":
            # DOM product_list 의 실제 아이템 수를 검증
            item_sel = product_tmpl["config"].get("item_selector", "")
            if item_sel:
                try:
                    item_count = page.evaluate(
                        "(sel) => document.querySelectorAll(sel).length",
                        item_sel,
                    )
                    print(f"[analyzer] product_list 검증: '{item_sel}' → {item_count}개")
                    if item_count < 5:
                        print("[analyzer] 상품 수 부족 → 상품 페이지 탐색 필요")
                        # 기존 product_list 제거
                        templates = [
                            t for t in templates
                            if t["target"] not in ("product_list", "product_list_dom")
                        ]
                        need_discovery = True
                except Exception:
                    pass

        if need_discovery:
            discovered = self._discover_product_page(page, site_url)
            if discovered:
                for dt in discovered:
                    existing_targets = {t["target"] for t in templates}
                    if dt["target"] not in existing_targets:
                        templates.append(dt)
                        existing_targets.add(dt["target"])

        # 결과 조합
        if not templates:
            print("[analyzer] 분석 실패: 어떤 전략으로도 상품 데이터를 찾을 수 없습니다")
            return None

        # 플랫폼 정보 생성
        observed_domains = interceptor.get_observed_domains() if interceptor else []
        detection_var = self._get_primary_state_var(framework)

        platform = self._build_platform_info(
            detection_var, domain, site_url, observed_domains,
        )

        target_names = [t["target"] for t in templates]
        print(f"[analyzer] 템플릿 {len(templates)}개 생성 완료: {target_names}")
        return {"platform": platform, "templates": templates}

    # ═══════════════════════════════════════════════════════════════
    # 프레임워크 감지
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _detect_framework(page: Page) -> str:
        """페이지의 프레임워크를 감지한다."""
        try:
            fw = page.evaluate("""() => {
                if (window.__PRELOADED_STATE__) return 'preloaded_state';
                if (window.__NEXT_DATA__ && window.__NEXT_DATA__.props) return 'nextjs';
                if (window.__next_f && Array.isArray(window.__next_f)) return 'nextjs_rsc';
                if (window.__NUXT__) return 'nuxt';
                if (window.__INITIAL_STATE__) return 'generic_state';
                if (window.__APOLLO_STATE__) return 'apollo';
                return 'unknown';
            }""")
            return fw or "unknown"
        except Exception:
            return "unknown"

    @staticmethod
    def _get_primary_state_var(framework: str) -> str:
        """프레임워크에 해당하는 주요 전역 변수명을 반환한다."""
        return {
            "preloaded_state": "__PRELOADED_STATE__",
            "nextjs": "__NEXT_DATA__",
            "nextjs_rsc": "__next_f",
            "nuxt": "__NUXT__",
            "generic_state": "__INITIAL_STATE__",
            "apollo": "__APOLLO_STATE__",
        }.get(framework, "")

    # ═══════════════════════════════════════════════════════════════
    # 1단계: state_var 기반 분석 (프레임워크별 분기)
    # ═══════════════════════════════════════════════════════════════

    def _analyze_state_var_multi(
        self, page: Page, site_url: str, framework: str,
    ) -> list[dict]:
        """프레임워크에 맞는 state_var 분석을 실행한다."""

        if framework == "preloaded_state":
            return self._analyze_preloaded_state(page, site_url)

        if framework == "nextjs":
            return self._analyze_nextjs(page, site_url)

        if framework == "nuxt":
            return self._analyze_nuxt(page, site_url)

        if framework == "generic_state":
            # __INITIAL_STATE__ 등 범용 전역 변수
            state_vars = self._find_state_vars(page)
            if state_vars:
                return self._analyze_generic_state(page, site_url, state_vars)

        # unknown / nextjs_rsc 등 — state_var 분석 불가
        return []

    # ── __PRELOADED_STATE__ (네이버 등) ───────────────────────────

    def _analyze_preloaded_state(
        self, page: Page, site_url: str,
    ) -> list[dict]:
        """기존 __PRELOADED_STATE__ 분석 로직."""
        var_name = "__PRELOADED_STATE__"
        print(f"[analyzer] '{var_name}' 구조 분석 중...")

        try:
            structure = page.evaluate(_JS_DEEP_SCAN, var_name)
        except Exception as e:
            print(f"[analyzer] 구조 스캔 실패: {e}")
            return []

        if not structure:
            return []

        top_keys = list(structure.keys())
        print(f"[analyzer] 최상위 키: {top_keys[:20]}")

        store_root = self._find_root_key(structure, _STORE_ROOT_CANDIDATES)
        product_root = self._find_root_key(structure, _PRODUCT_ROOT_CANDIDATES)
        category_root = self._find_root_key(structure, _CATEGORY_ROOT_CANDIDATES)
        detail_roots = self._find_detail_roots(structure)

        if not store_root and not product_root:
            print(f"[analyzer] '{var_name}' 에서 매장/상품 루트를 찾지 못함")
            return []

        print(f"[analyzer] 감지: store={store_root}, product={product_root}, "
              f"category={category_root}, detail={detail_roots}")

        templates = []

        if store_root:
            tmpl = self._build_store_template(var_name, store_root, structure)
            if tmpl:
                templates.append(tmpl)

        if category_root:
            tmpl = self._build_category_template(
                var_name, category_root, structure, site_url,
            )
            if tmpl:
                templates.append(tmpl)

        if product_root:
            tmpl = self._build_product_list_template(
                var_name, product_root, structure,
            )
            if not tmpl and category_root:
                tmpl = self._rescan_product_on_category_page(
                    page, var_name, product_root, category_root,
                    structure, site_url,
                )
            if tmpl:
                templates.append(tmpl)

        if detail_roots:
            tmpl = self._build_detail_template(
                var_name, detail_roots, structure, site_url,
            )
            if tmpl:
                templates.append(tmpl)

        return templates

    # ── Next.js __NEXT_DATA__ ─────────────────────────────────────

    def _analyze_nextjs(self, page: Page, site_url: str) -> list[dict]:
        """Next.js __NEXT_DATA__.props.pageProps 구조를 분석한다."""
        print("[analyzer] Next.js __NEXT_DATA__ 분석 중...")

        try:
            structure = page.evaluate(_JS_DEEP_SCAN_NEXTJS)
        except Exception as e:
            print(f"[analyzer] Next.js 스캔 실패: {e}")
            return []

        if not structure:
            return []

        top_keys = list(structure.keys())
        print(f"[analyzer] pageProps 키: {top_keys[:20]}")

        templates = []

        # dehydratedState (React Query) 가 있으면 우선 탐색
        dq = structure.get("__dehydratedQueries")
        if dq and isinstance(dq, dict) and dq.get("queries"):
            rq_templates = self._analyze_react_query(dq["queries"], site_url)
            templates.extend(rq_templates)

        # pageProps 직계 데이터에서 표준 루트 탐색
        store_root = self._find_root_key(structure, _STORE_ROOT_CANDIDATES)
        product_root = self._find_root_key(structure, _PRODUCT_ROOT_CANDIDATES)
        category_root = self._find_root_key(structure, _CATEGORY_ROOT_CANDIDATES)

        # data 키 안에 중첩되어 있을 수 있음
        data_info = structure.get("data")
        if data_info and isinstance(data_info, dict):
            data_children = data_info.get("children") or data_info
            if isinstance(data_children, dict):
                if not store_root:
                    store_root = self._find_root_key(
                        data_children, _STORE_ROOT_CANDIDATES,
                    )
                if not product_root:
                    product_root = self._find_root_key(
                        data_children, _PRODUCT_ROOT_CANDIDATES,
                    )
                if not category_root:
                    category_root = self._find_root_key(
                        data_children, _CATEGORY_ROOT_CANDIDATES,
                    )

        if store_root or product_root:
            print(f"[analyzer] Next.js 루트: store={store_root}, "
                  f"product={product_root}, category={category_root}")

        return templates

    def _analyze_react_query(
        self, queries: list[dict], site_url: str,
    ) -> list[dict]:
        """React Query dehydratedState 에서 상품 데이터를 찾는다."""
        templates = []
        print(f"[analyzer] React Query {len(queries)}개 쿼리 분석...")

        for qi in queries:
            data_scan = qi.get("dataScan")
            if not data_scan or not isinstance(data_scan, dict):
                continue

            # 상품 리스트 탐색
            product_root = self._find_root_key(data_scan, _PRODUCT_ROOT_CANDIDATES)
            if product_root:
                tmpl = self._build_product_list_template(
                    "__NEXT_DATA__", product_root, data_scan,
                )
                if tmpl:
                    # React Query 에서 가져온 것이므로 state_var 경로 조정
                    tmpl["config"]["nextjs_path"] = "dehydratedState"
                    templates.append(tmpl)
                    print(f"[analyzer] React Query 에서 product_list 발견: {product_root}")

        return templates

    # ── Nuxt.js __NUXT__ ──────────────────────────────────────────

    def _analyze_nuxt(self, page: Page, site_url: str) -> list[dict]:
        """Nuxt.js __NUXT__ + Pinia 상태를 분석한다."""
        print("[analyzer] Nuxt.js __NUXT__ / Pinia 분석 중...")

        try:
            structure = page.evaluate(_JS_DEEP_SCAN_NUXT)
        except Exception as e:
            print(f"[analyzer] Nuxt 스캔 실패: {e}")
            return []

        if not structure:
            print("[analyzer] Nuxt 상태 비어있음 → API/DOM 분석 필요")
            return []

        templates = []

        # data, state, pinia 순서로 탐색
        for section_name in ("data", "state", "pinia", "piniaGlobal"):
            section = structure.get(section_name)
            if not section or not isinstance(section, dict):
                continue

            print(f"[analyzer] Nuxt {section_name} 키: {list(section.keys())[:15]}")

            product_root = self._find_root_key(section, _PRODUCT_ROOT_CANDIDATES)
            store_root = self._find_root_key(section, _STORE_ROOT_CANDIDATES)

            if product_root:
                tmpl = self._build_product_list_template(
                    "__NUXT__", product_root, section,
                )
                if tmpl:
                    tmpl["config"]["nuxt_section"] = section_name
                    templates.append(tmpl)

            if store_root:
                tmpl = self._build_store_template(
                    "__NUXT__", store_root, section,
                )
                if tmpl:
                    tmpl["config"]["nuxt_section"] = section_name
                    templates.append(tmpl)

        return templates

    # ── 범용 전역 변수 ────────────────────────────────────────────

    def _analyze_generic_state(
        self, page: Page, site_url: str, state_vars: list[str],
    ) -> list[dict]:
        """범용 전역 변수를 분석한다 (기존 로직 호환)."""
        for var_name in state_vars:
            print(f"[analyzer] '{var_name}' 구조 분석 중...")

            try:
                structure = page.evaluate(_JS_DEEP_SCAN, var_name)
            except Exception as e:
                print(f"[analyzer] 구조 스캔 실패: {e}")
                continue

            if not structure:
                continue

            store_root = self._find_root_key(structure, _STORE_ROOT_CANDIDATES)
            product_root = self._find_root_key(structure, _PRODUCT_ROOT_CANDIDATES)

            if not store_root and not product_root:
                continue

            templates = []
            if store_root:
                tmpl = self._build_store_template(var_name, store_root, structure)
                if tmpl:
                    templates.append(tmpl)
            if product_root:
                tmpl = self._build_product_list_template(
                    var_name, product_root, structure,
                )
                if tmpl:
                    templates.append(tmpl)

            if templates:
                return templates

        return []

    # ═══════════════════════════════════════════════════════════════
    # 2단계: API 분석 (네트워크 인터셉트 결과 활용)
    # ═══════════════════════════════════════════════════════════════

    def _analyze_api(
        self, interceptor: NetworkInterceptor, site_url: str,
    ) -> list[dict]:
        """인터셉트된 네트워크 요청에서 API 템플릿을 생성한다."""
        candidates = interceptor.get_api_candidates()
        if not candidates:
            return []

        print(f"[analyzer] API 후보 {len(candidates)}개 발견")
        templates = []

        for cand in candidates:
            target = cand["target_type"]
            analysis = cand["analysis"]

            print(f"[analyzer] API: {target} score={cand['score']} "
                  f"path={cand['path']}")

            tmpl = self._build_api_template(cand, site_url)
            if tmpl:
                templates.append(tmpl)

        return templates

    def _build_api_template(self, candidate: dict, site_url: str) -> dict | None:
        """API 후보 정보로 api 전략 템플릿을 생성한다."""
        target = candidate["target_type"]
        analysis = candidate["analysis"]
        field_mapping = analysis.get("field_mapping", {})

        if not field_mapping:
            return None

        parsed = urlparse(candidate["url"])
        # endpoint: 같은 도메인이면 경로만, 다른 도메인이면 전체 URL
        site_domain = urlparse(site_url).hostname or ""
        if parsed.hostname == site_domain:
            endpoint = parsed.path
        else:
            endpoint = f"{parsed.scheme}://{parsed.hostname}{parsed.path}"

        # 쿼리 파라미터 구성
        params = {}
        for k, v_list in candidate.get("query", {}).items():
            val = v_list[0] if v_list else ""
            params[k] = val

        # 페이지네이션 파라미터 처리
        pagination = analysis.get("pagination")
        if pagination and pagination.get("param"):
            params[pagination["param"]] = "{page}"

        config = {
            "endpoint": endpoint,
            "method": candidate.get("method", "GET"),
            "params": params,
            "response": {
                "fields": field_mapping,
            },
        }

        # POST body 캡처 (네트워크 인터셉터에서 수집)
        request_body = candidate.get("request_body")
        if request_body and isinstance(request_body, dict):
            config["body"] = request_body

        # 원본 요청 헤더 중 필요한 것만 포함
        req_headers = candidate.get("request_headers", {})
        custom_headers = {}
        for hk, hv in req_headers.items():
            hk_lower = hk.lower()
            if hk_lower in ("content-type", "x-api-key", "authorization",
                            "x-custom-header", "x-requested-with"):
                custom_headers[hk] = hv
        if custom_headers:
            config["headers"] = custom_headers

        if target == "product_list":
            config["response"]["list_path"] = analysis.get("list_path", "")
            if analysis.get("total_count_path"):
                config["response"]["total_count_path"] = analysis["total_count_path"]

        elif target == "category":
            config["response"]["list_path"] = analysis.get("list_path", "")

        elif target == "store":
            config["response"]["data_path"] = analysis.get("data_path", "")

        return {
            "target": target,
            "strategy": "api",
            "config": config,
        }

    # ═══════════════════════════════════════════════════════════════
    # 4단계: 상품 페이지 자동 탐색 (메인 페이지에 상품 없는 경우)
    # ═══════════════════════════════════════════════════════════════

    _PRODUCT_PAGE_KEYWORDS = [
        "shop", "store", "product", "search",
        "상품", "쇼핑", "전체", "전체상품",
    ]

    def _discover_product_page(
        self, page: Page, site_url: str,
    ) -> list[dict]:
        """
        메인 페이지에서 상품 목록이 없을 때,
        네비게이션 링크를 탐색하여 상품 목록 페이지를 찾는다.
        """
        print("[analyzer] 메인 페이지에 상품 없음 → 상품 페이지 탐색 중...")

        js_find_nav_links = r"""() => {
            var keywords = ['shop', 'store', 'product', 'search',
                            'all', 'catalog', 'browse'];
            var kwKo = ['상품', '쇼핑', '전체', '스토어', '검색'];
            var links = document.querySelectorAll('a[href]');
            var candidates = [];
            for (var i = 0; i < links.length; i++) {
                var el = links[i];
                var href = el.getAttribute('href') || '';
                var text = (el.textContent || '').trim().toLowerCase();
                if (!href || href === '#' || href === '/') continue;
                // 외부 링크 제외
                if (href.indexOf('http') === 0 && href.indexOf(location.hostname) === -1) continue;

                var score = 0;
                var hrefLower = href.toLowerCase();
                for (var k = 0; k < keywords.length; k++) {
                    if (hrefLower.indexOf('/' + keywords[k]) > -1) score += 3;
                    if (text === keywords[k] || text === keywords[k].toUpperCase()) score += 2;
                }
                for (var j = 0; j < kwKo.length; j++) {
                    if (text.indexOf(kwKo[j]) > -1) score += 2;
                }
                // 네비게이션 영역 내 링크 우선
                var inNav = false;
                var parent = el.parentElement;
                for (var d = 0; d < 5 && parent; d++) {
                    var pCls = (typeof parent.className === 'string' ? parent.className : '').toLowerCase();
                    var pTag = parent.tagName.toLowerCase();
                    if (pTag === 'nav' || pCls.indexOf('gnb') > -1 || pCls.indexOf('nav') > -1
                        || pCls.indexOf('header') > -1 || pCls.indexOf('menu') > -1) {
                        inNav = true;
                        break;
                    }
                    parent = parent.parentElement;
                }
                if (inNav) score += 1;

                if (score >= 2) {
                    candidates.push({
                        href: href,
                        text: el.textContent.trim().substring(0, 30),
                        score: score,
                    });
                }
            }
            candidates.sort(function(a, b) { return b.score - a.score; });
            return candidates.slice(0, 5);
        }"""

        try:
            nav_links = page.evaluate(js_find_nav_links)
        except Exception as e:
            print(f"[analyzer] 네비게이션 탐색 실패: {e}")
            return []

        if not nav_links:
            print("[analyzer] 상품 페이지 후보 없음")
            return []

        print(f"[analyzer] 상품 페이지 후보 {len(nav_links)}개:")
        for nl in nav_links:
            print(f"[analyzer]   score={nl['score']} href={nl['href']} text={nl['text']}")

        # 상위 후보 페이지로 이동하여 분석
        from urllib.parse import urljoin
        base_url = page.url

        for nl in nav_links[:3]:
            target_url = urljoin(base_url, nl["href"])
            print(f"[analyzer] 상품 페이지 시도: {target_url}")
            try:
                resp = self._safe_goto(
                    page, target_url,
                    wait_until="networkidle", timeout=60000,
                )
                if resp and resp.status in (429, 403, 503):
                    print(f"[analyzer] 상품 페이지 차단됨 → 다음 후보 시도")
                    continue
                page.wait_for_timeout(5000)

                # 스크롤로 지연 로드 트리거
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    page.wait_for_timeout(1500)

                # DOM 분석 재시도
                dom_templates = self._analyze_dom_enhanced(page, target_url)
                product_templates = [
                    t for t in dom_templates
                    if t["target"] in ("product_list", "product_list_dom")
                ]

                if product_templates:
                    print(f"[analyzer] 상품 페이지 발견: {target_url}")
                    # product_list 템플릿에 page_url 저장 (수집 시 사용)
                    for pt in product_templates:
                        pt["config"]["page_url"] = target_url
                    # 같은 페이지에서 다른 템플릿도 포함
                    return dom_templates
            except Exception as e:
                print(f"[analyzer] {target_url} 접속 실패: {e}")
                continue

        print("[analyzer] 상품 페이지 탐색 실패")
        return []

    # ═══════════════════════════════════════════════════════════════
    # 3단계: DOM 분석 (강화판)
    # ═══════════════════════════════════════════════════════════════

    def _analyze_dom_enhanced(self, page: Page, site_url: str) -> list[dict]:
        """DOM 구조를 분석하여 가능한 모든 템플릿을 생성한다."""
        templates = []

        # 3-1. 매장 정보 (DOM)
        store_tmpl = self._build_dom_store_template(page)
        if store_tmpl:
            templates.append(store_tmpl)

        # 3-2. 카테고리 메뉴 (DOM)
        cat_tmpl = self._build_dom_category_template(page, site_url)
        if cat_tmpl:
            templates.append(cat_tmpl)

        # 3-3. 상품 목록 (DOM)
        prod_tmpl = self._build_dom_product_template(page, site_url)
        if prod_tmpl:
            templates.append(prod_tmpl)

        # 3-4. 상품 상세 URL 패턴 (DOM)
        detail_tmpl = self._build_dom_detail_template(page, site_url)
        if detail_tmpl:
            templates.append(detail_tmpl)

        return templates

    def _build_dom_store_template(self, page: Page) -> dict | None:
        """DOM 에서 매장 기본 정보를 추출하는 템플릿을 생성한다."""
        try:
            store_info = page.evaluate(_JS_DOM_STORE_SCAN)
        except Exception:
            return None

        if not store_info:
            return None

        selectors = {}
        if store_info.get("og_title"):
            selectors["store_name"] = {
                "selector": 'meta[property="og:title"]',
                "attr": "content",
            }
        elif store_info.get("h1"):
            selectors["store_name"] = {
                "selector": "h1", "attr": "textContent",
            }

        if store_info.get("og_description"):
            selectors["description"] = {
                "selector": 'meta[property="og:description"]',
                "attr": "content",
            }

        if store_info.get("og_image"):
            selectors["logo_url"] = {
                "selector": 'meta[property="og:image"]',
                "attr": "content",
            }

        if not selectors:
            return None

        return {
            "target": "store",
            "strategy": "dom",
            "config": {
                "selectors": selectors,
            },
        }

    def _build_dom_category_template(
        self, page: Page, site_url: str,
    ) -> dict | None:
        """DOM 에서 카테고리 메뉴를 추출하는 템플릿을 생성한다."""
        try:
            candidates = page.evaluate(_JS_DOM_CATEGORY_SCAN)
        except Exception:
            return None

        if not candidates:
            return None

        # 가장 많은 링크를 가진 네비게이션 선택
        best = candidates[0]
        print(f"[analyzer] DOM 카테고리 후보: '{best['selector']}' "
              f"({best['linkCount']}개 링크)")

        # URL 패턴 분석
        hrefs = best.get("hrefs", [])
        if not hrefs:
            return None

        # 카테고리 URL 패턴 추론
        url_pattern = self._infer_category_url_pattern(hrefs, site_url)

        return {
            "target": "category",
            "strategy": "dom",
            "config": {
                "container": best["selector"],
                "item_selector": "a[href]",
                "fields": {
                    "name": {"selector": "a", "attr": "textContent"},
                    "url": {"selector": "a", "attr": "href"},
                },
                "url_pattern": url_pattern,
                "categories_from_links": True,
            },
        }

    def _build_dom_product_template(
        self, page: Page, site_url: str,
    ) -> dict | None:
        """DOM 에서 상품 목록을 추출하는 템플릿을 생성한다."""
        try:
            candidates = page.evaluate(_JS_DOM_PRODUCT_SCAN)
        except Exception:
            return None

        if not candidates:
            return None

        best = candidates[0]
        item_class = best["className"]
        count = best["count"]
        total = best.get("totalElements", count)
        ratio = best.get("ratio", 1.0)
        score = best.get("score", count)
        display_sel = item_class if item_class.startswith("[") else f".{item_class}"
        print(f"[analyzer] DOM 상품 카드 후보: '{display_sel}' "
              f"(요소={total}, 가격연관={count}, ratio={ratio}, score={score})")

        # 디버그: 상위 3개 후보 출력
        for i, cand in enumerate(candidates[:3]):
            cn = cand['className']
            ds = cn if cn.startswith("[") else f".{cn}"
            print(f"[analyzer]   #{i+1} {ds}: "
                  f"요소={cand.get('totalElements', '?')}, "
                  f"ratio={cand.get('ratio', '?')}, "
                  f"score={cand.get('score', '?')}")

        if total < 3:
            return None

        sample = best.get("sample", {})

        # ── 카드 내부 필드 스캐너로 최적 셀렉터 탐색 ──────────────
        card_fields = None
        try:
            card_fields = page.evaluate(_JS_DOM_CARD_FIELDS_SCAN, item_class)
        except Exception as e:
            print(f"[analyzer] 카드 필드 스캔 오류: {e}")

        fields = {}

        if card_fields:
            # 카드 내부 분석 결과 사용
            if card_fields.get("nameSamples"):
                print(f"[analyzer] 카드 필드 감지: "
                      f"name={card_fields.get('nameSelector')}, "
                      f"price={card_fields.get('priceSelector')}, "
                      f"brand={card_fields.get('brandSelector')}")
                print(f"[analyzer]   이름 샘플: {card_fields['nameSamples'][:2]}")
                if card_fields.get("_debug"):
                    dbg = card_fields["_debug"]
                    print(f"[analyzer]   가격 후보: {dbg.get('priceCands', [])}, "
                          f"검증={dbg.get('sampleCardCount',0)}카드 "
                          f"minHits={dbg.get('minHits',0)}")

            # 상품명
            if card_fields.get("nameSelector"):
                fields["product_name"] = {
                    "selector": card_fields["nameSelector"],
                    "attr": "textContent",
                }
            elif card_fields.get("linkSelector"):
                fields["product_name"] = {
                    "selector": card_fields["linkSelector"],
                    "attr": "textContent",
                }

            # 링크 (상품 URL)
            link_sel = card_fields.get("linkSelector")
            if link_sel == ":self":
                # 카드 자체가 <a> 태그 → :self_attr 로 마킹
                fields["product_url"] = {
                    "selector": ":self",
                    "attr": "href",
                }
            elif link_sel:
                fields["product_url"] = {
                    "selector": link_sel,
                    "attr": "href",
                }
            elif sample.get("selfIsLink"):
                fields["product_url"] = {
                    "selector": ":self",
                    "attr": "href",
                }
            elif sample.get("hasLink"):
                fields["product_url"] = {
                    "selector": "a[href]", "attr": "href",
                }

            # 가격
            if card_fields.get("priceSelector"):
                fields["selling_price"] = {
                    "selector": card_fields["priceSelector"],
                    "attr": "textContent",
                    "regex": r"[\d,]+",
                }
            if card_fields.get("orgPriceSelector"):
                fields["original_price"] = {
                    "selector": card_fields["orgPriceSelector"],
                    "attr": "textContent",
                    "regex": r"[\d,]+",
                }

            # 브랜드
            if card_fields.get("brandSelector"):
                fields["brand_name"] = {
                    "selector": card_fields["brandSelector"],
                    "attr": "textContent",
                }

            # 이미지
            if card_fields.get("imgSelector"):
                fields["image_url"] = {
                    "selector": card_fields["imgSelector"],
                    "attr": "src",
                }

        # 카드 필드 스캐너 결과가 불충분하면 기본 셀렉터 보완
        if "product_name" not in fields:
            if sample.get("hasLink"):
                fields["product_name"] = {
                    "selector": "a", "attr": "textContent",
                }
            else:
                fields["product_name"] = {
                    "selector": "*", "attr": "textContent",
                }

        if "product_url" not in fields and sample.get("hasLink"):
            fields["product_url"] = {
                "selector": "a[href]", "attr": "href",
            }

        if "image_url" not in fields and sample.get("hasImg"):
            fields["image_url"] = {"selector": "img", "attr": "src"}

        if "selling_price" not in fields:
            fields["selling_price"] = {
                "selector": ":self", "attr": "textContent",
                "regex": r"\d{1,3}(,\d{3})+",
            }

        # data 속성에서 product_id 추출
        data_attrs = sample.get("dataAttrs", {})
        for attr_name in data_attrs:
            if "product" in attr_name or "goods" in attr_name or "item" in attr_name:
                if item_class.startswith("["):
                    id_sel = item_class
                else:
                    id_sel = f".{item_class}"
                fields["product_id"] = {
                    "selector": ":self",
                    "attr": attr_name,
                }
                break

        # 상품 상세 URL 패턴 추론
        detail_url_pattern = None
        link_hrefs = sample.get("linkHrefs", [])
        if link_hrefs:
            detail_url_pattern = self._infer_detail_url_pattern(
                link_hrefs, site_url,
            )

        # 페이지네이션 감지
        try:
            pagination = page.evaluate(_JS_DOM_PAGINATION_SCAN)
        except Exception:
            pagination = {"type": None}

        pag_config = None
        if pagination.get("type") == "click":
            pag_config = {
                "type": "click",
                "next_button": pagination["details"].get("selector", ""),
                "max_pages": 50,
            }
        elif pagination.get("type") == "scroll":
            pag_config = {
                "type": "scroll",
                "max_scrolls": 30,
                "scroll_wait_ms": 2000,
            }
        elif pagination.get("type") == "url_param":
            pag_config = {
                "type": "url_param",
                "param": "page",
                "max_pages": 50,
            }

        # 속성 기반 셀렉터인 경우 그대로 사용 (예: [data-item-id])
        if item_class.startswith("["):
            item_sel = item_class
        else:
            item_sel = f".{item_class}"

        config = {
            "container": "body",
            "item_selector": item_sel,
            "fields": fields,
        }
        if pag_config:
            config["pagination"] = pag_config
        if detail_url_pattern:
            config["detail_url_pattern"] = detail_url_pattern

        return {
            "target": "product_list",
            "strategy": "dom",
            "config": config,
        }

    def _build_dom_detail_template(
        self, page: Page, site_url: str,
    ) -> dict | None:
        """DOM 에서 상품 상세 페이지 정보를 추출하는 템플릿을 생성한다."""
        try:
            detail_info = page.evaluate(_JS_DOM_DETAIL_URL_SCAN)
        except Exception:
            return None

        if not detail_info:
            return None

        product_urls = detail_info.get("productUrls", [])
        if not product_urls:
            return None

        url_pattern = self._infer_detail_url_pattern(product_urls, site_url)
        if not url_pattern:
            return None

        return {
            "target": "product_detail",
            "strategy": "dom",
            "config": {
                "selectors": {
                    "description": {
                        "selector": (
                            '[class*="detail"], [class*="description"], '
                            '[class*="content"], [id*="detail"]'
                        ),
                        "attr": "textContent",
                    },
                    "detail_images": {
                        "selector": (
                            '[class*="detail"] img, [class*="description"] img, '
                            '[class*="content"] img'
                        ),
                        "attr": "src",
                        "multiple": True,
                    },
                },
                "url_pattern": url_pattern,
            },
        }

    # ═══════════════════════════════════════════════════════════════
    # URL 패턴 추론
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _infer_detail_url_pattern(
        urls: list[str], site_url: str,
    ) -> str | None:
        """상품 URL 목록에서 상세 URL 패턴을 추론한다."""
        if not urls:
            return None

        parsed_site = urlparse(site_url)
        patterns = []

        for url in urls[:10]:
            # 절대 URL 또는 상대 URL 처리
            if url.startswith("http"):
                parsed = urlparse(url)
                path = parsed.path
                query = parsed.query
            elif url.startswith("/"):
                path = url.split("?")[0]
                query = url.split("?")[1] if "?" in url else ""
            else:
                continue

            # 경로에서 숫자/ID 세그먼트를 {product_id} 로 치환
            segments = path.strip("/").split("/")
            pattern_segments = []
            for seg in segments:
                # 숫자만으로 이루어진 세그먼트 → product_id
                if re.match(r"^\d+$", seg):
                    pattern_segments.append("{product_id}")
                else:
                    pattern_segments.append(seg)

            pattern_path = "/" + "/".join(pattern_segments)

            # 쿼리 파라미터에서 ID 패턴 탐색
            if query:
                # goodsNo=A000000253729 같은 패턴
                q_pattern = re.sub(
                    r"(goodsNo|productNo|itemId|goodsCd|no|id)=[^&]+",
                    r"\1={product_id}",
                    query,
                )
                # 트래킹 파라미터 제거
                q_parts = []
                for part in q_pattern.split("&"):
                    key = part.split("=")[0].lower()
                    if key not in ("t_page", "t_click", "t_number",
                                   "trackingcd", "utm_source", "utm_medium"):
                        q_parts.append(part)
                if q_parts:
                    pattern_path += "?" + "&".join(q_parts)

            patterns.append(pattern_path)

        if not patterns:
            return None

        # 가장 흔한 패턴 반환
        from collections import Counter
        counter = Counter(patterns)
        return counter.most_common(1)[0][0]

    @staticmethod
    def _infer_category_url_pattern(
        hrefs: list[str], site_url: str,
    ) -> str | None:
        """카테고리 링크에서 URL 패턴을 추론한다."""
        if not hrefs:
            return None

        # 상대/절대 URL 에서 경로 추출
        paths = []
        for href in hrefs:
            if href.startswith("http"):
                paths.append(urlparse(href).path)
            elif href.startswith("/"):
                paths.append(href.split("?")[0])

        if not paths:
            return None

        # 공통 접두사 찾기
        common = paths[0]
        for p in paths[1:]:
            while not p.startswith(common) and common:
                common = "/".join(common.split("/")[:-1])

        if common and common != "/":
            return common + "/{cat_id}"

        return None

    # ═══════════════════════════════════════════════════════════════
    # 루트 키 탐지
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _find_root_key(structure: dict, candidates: list[str]) -> str | None:
        """structure 의 최상위 키 중 candidates 에 매칭되는 것을 반환한다."""
        top_keys = list(structure.keys())

        # 정확히 일치
        for cand in candidates:
            if cand in top_keys:
                return cand

        # 부분 일치 (대소문자 무시)
        for cand in candidates:
            cand_lower = cand.lower()
            for key in top_keys:
                if cand_lower in key.lower():
                    return key

        return None

    @staticmethod
    def _find_detail_roots(structure: dict) -> list[str]:
        """상품 상세 루트 키 후보를 반환한다."""
        found = []
        top_keys = list(structure.keys())

        for cand in _DETAIL_ROOT_CANDIDATES:
            if cand in top_keys:
                found.append(cand)

        if not found:
            for cand in _DETAIL_ROOT_CANDIDATES:
                for key in top_keys:
                    if key.lower() == cand.lower() and key not in found:
                        found.append(key)

        return found[:3]

    # ═══════════════════════════════════════════════════════════════
    # 필드 매핑 자동 생성
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _auto_map_fields(
        available_keys: list[str],
        pattern_map: dict[str, list[str]],
    ) -> dict[str, str | list[str]]:
        """available_keys 에서 표준 필드에 매칭되는 키를 찾아 매핑한다."""
        mapping = {}
        used = set()

        for std_field, patterns in pattern_map.items():
            matches = []
            for pattern in patterns:
                if pattern in available_keys and pattern not in used:
                    matches.append(pattern)
                    continue
                if "." in pattern:
                    root = pattern.split(".")[0]
                    if root in available_keys:
                        matches.append(pattern)
                        continue
                pattern_lower = pattern.lower()
                for key in available_keys:
                    if key.lower() == pattern_lower and key not in used:
                        matches.append(key)

            if len(matches) == 1:
                mapping[std_field] = matches[0]
                used.add(matches[0])
            elif len(matches) > 1:
                mapping[std_field] = matches[:2]
                used.add(matches[0])

        return mapping

    @staticmethod
    def _find_list_key(
        parent_info: dict, candidates: list[str],
    ) -> str | None:
        """부모 객체 정보에서 배열 키를 찾는다."""
        if not parent_info:
            return None

        children = parent_info.get("children", parent_info)
        if isinstance(children, dict):
            keys = list(children.keys())
        else:
            return None

        for cand in candidates:
            if cand in keys:
                info = children.get(cand, {})
                if isinstance(info, dict) and info.get("type") == "array":
                    return cand

        for cand in candidates:
            cand_lower = cand.lower()
            for key in keys:
                if key.lower() == cand_lower:
                    info = children.get(key, {})
                    if isinstance(info, dict) and info.get("type") == "array":
                        return key

        array_keys = []
        for key in keys:
            info = children.get(key, {})
            if isinstance(info, dict) and info.get("type") == "array":
                length = info.get("length", 0)
                if length > 0:
                    array_keys.append((key, length))

        if array_keys:
            array_keys.sort(key=lambda x: x[1], reverse=True)
            return array_keys[0][0]

        for cand in candidates:
            if cand in keys:
                return cand

        return None

    # ═══════════════════════════════════════════════════════════════
    # state_var 템플릿 빌더 (기존 로직 보존)
    # ═══════════════════════════════════════════════════════════════

    def _build_platform_info(
        self, state_var: str, domain: str, site_url: str,
        observed_domains: list[str] | None = None,
    ) -> dict:
        """플랫폼 감지 정보를 생성한다."""
        name = domain.replace(".", "_").replace("-", "_")

        if "brand.naver.com" in site_url or "smartstore.naver.com" in site_url:
            name = "naver_smartstore"
            display_name = "네이버 스마트스토어"
        else:
            display_name = domain

        rules = []
        if state_var:
            rules.append({"type": "js_var_exists", "var": state_var})
        rules.append({"type": "url_match", "pattern": re.escape(domain)})

        return {
            "name": name,
            "display_name": display_name,
            "detection": {
                "rules": rules,
                "match_mode": "all",
            },
            "browser": _default_browser_config(domain, observed_domains),
        }

    def _build_store_template(
        self, state_var: str, root_key: str, structure: dict,
    ) -> dict | None:
        """매장 정보 추출 템플릿을 생성한다."""
        root_info = structure.get(root_key, {})
        if not isinstance(root_info, dict):
            return None

        available = root_info.get("keys", [])
        if not available and root_info.get("children"):
            available = list(root_info["children"].keys())
        if not available:
            return None

        fields = self._auto_map_fields(available, _STORE_FIELD_PATTERNS)
        if not fields:
            return None

        # address 중첩 탐색
        if "address" not in fields:
            for key in available:
                if "address" in key.lower():
                    children = root_info.get("children", {})
                    addr_info = children.get(key, {})
                    if isinstance(addr_info, dict) and addr_info.get("keys"):
                        sub_keys = addr_info["keys"]
                        for sk in sub_keys:
                            if "full" in sk.lower() or "basic" in sk.lower():
                                fields["address"] = f"{key}.{sk}"
                                break
                        if "address" not in fields and sub_keys:
                            fields["address"] = f"{key}.{sub_keys[0]}"
                    break

        # phone 중첩 탐색
        if "phone" not in fields:
            for key in available:
                if "contact" in key.lower() or "tel" in key.lower():
                    children = root_info.get("children", {})
                    contact_info = children.get(key, {})
                    if isinstance(contact_info, dict):
                        sub_children = contact_info.get("children", {})
                        if sub_children:
                            for sk, sv in sub_children.items():
                                if isinstance(sv, dict) and sv.get("keys"):
                                    for ssk in sv["keys"]:
                                        if "format" in ssk.lower() or "number" in ssk.lower():
                                            fields["phone"] = f"{key}.{sk}.{ssk}"
                                            break

        print(f"[analyzer] store 필드 매핑: {fields}")

        return {
            "target": "store",
            "strategy": "state_var",
            "config": {
                "state_var": state_var,
                "root_key": root_key,
                "fields": fields,
                "dom_fallback": {"store_name": "title"},
            },
        }

    def _build_category_template(
        self, state_var: str, root_key: str, structure: dict,
        site_url: str,
    ) -> dict | None:
        """카테고리 목록 추출 템플릿을 생성한다."""
        root_info = structure.get(root_key, {})
        if not isinstance(root_info, dict):
            return None

        list_key = self._find_list_key(root_info, _CATEGORY_LIST_KEY_CANDIDATES)
        if not list_key:
            return None

        children = root_info.get("children", root_info)
        list_info = children.get(list_key, {}) if isinstance(children, dict) else {}
        item_keys = list_info.get("itemKeys", []) if isinstance(list_info, dict) else []

        if not item_keys:
            return None

        fields = self._auto_map_fields(item_keys, _CATEGORY_FIELD_PATTERNS)
        if not fields:
            return None

        url_pattern = "/{slug}/category/{cat_id}?cp={page}"

        print(f"[analyzer] category 필드 매핑: {fields}")

        return {
            "target": "category",
            "strategy": "state_var",
            "config": {
                "state_var": state_var,
                "root_key": root_key,
                "list_key": list_key,
                "fields": fields,
                "url_pattern": url_pattern,
            },
        }

    def _build_product_list_template(
        self, state_var: str, root_key: str, structure: dict,
    ) -> dict | None:
        """상품 목록 추출 템플릿을 생성한다."""
        root_info = structure.get(root_key, {})
        if not isinstance(root_info, dict):
            return None

        list_key = self._find_list_key(root_info, _PRODUCT_LIST_KEY_CANDIDATES)
        if not list_key:
            return None

        children = root_info.get("children", root_info)
        list_info = children.get(list_key, {}) if isinstance(children, dict) else {}
        item_keys = list_info.get("itemKeys", []) if isinstance(list_info, dict) else []

        if not item_keys:
            return None

        # 중첩 키 탐색
        extended_keys = list(item_keys)
        item_sample = list_info.get("itemSample", {})
        for key in item_keys:
            sample_val = item_sample.get(key, "")
            if isinstance(sample_val, str) and sample_val.startswith("{"):
                sub_keys_str = sample_val.strip("{}").split(",")
                for sk in sub_keys_str:
                    sk = sk.strip()
                    if sk:
                        extended_keys.append(f"{key}.{sk}")

        fields = self._auto_map_fields(extended_keys, _PRODUCT_FIELD_PATTERNS)
        if not fields:
            return None

        total_count_key = None
        children_keys = list(children.keys()) if isinstance(children, dict) else []
        for key in children_keys:
            if "total" in key.lower() and "count" in key.lower():
                total_count_key = key
                break
            if key == "totalCount":
                total_count_key = key
                break

        print(f"[analyzer] product_list 필드 매핑: {fields}")

        return {
            "target": "product_list",
            "strategy": "state_var",
            "config": {
                "state_var": state_var,
                "root_key": root_key,
                "list_key": list_key,
                "total_count_key": total_count_key,
                "page_size": 40,
                "fields": fields,
            },
        }

    def _build_detail_template(
        self, state_var: str, detail_roots: list[str], structure: dict,
        site_url: str,
    ) -> dict | None:
        """상품 상세 추출 템플릿을 생성한다."""
        fields = {}
        for root_key in detail_roots:
            root_info = structure.get(root_key, {})
            if not isinstance(root_info, dict):
                continue

            available = root_info.get("keys", [])
            if not available and root_info.get("children"):
                available = list(root_info["children"].keys())

            extended = list(available)
            children = root_info.get("children", {})
            for key in available:
                child = children.get(key, {}) if isinstance(children, dict) else {}
                if isinstance(child, dict) and child.get("keys"):
                    for sk in child["keys"]:
                        extended.append(f"{key}.{sk}")

            detail_patterns = {
                "description": _PRODUCT_FIELD_PATTERNS.get("detail_text", []) + [
                    "description", "content", "detailContent",
                ],
                "detail_images": [
                    "optionalImageUrls", "detailImages", "imageUrls",
                    "additionalImages", "images",
                ],
            }
            candidate = self._auto_map_fields(extended, detail_patterns)
            if candidate:
                fields.update(candidate)

        if not fields:
            fields = {
                "description": "detailContents.detailContentText",
                "detail_images": "optionalImageUrls",
            }

        url_pattern = "/{slug}/products/{product_id}"

        return {
            "target": "product_detail",
            "strategy": "state_var",
            "config": {
                "state_var": state_var,
                "root_keys": detail_roots,
                "fields": fields,
                "url_pattern": url_pattern,
                "dom_fallback": [
                    '[class*="se-viewer"]',
                    '[class*="detail_content"]',
                    '#INTRODUCE',
                ],
            },
        }

    # ─── 카테고리 페이지 재스캔 ─────────────────────────────────────

    def _rescan_product_on_category_page(
        self, page: Page, state_var: str, product_root: str,
        category_root: str, structure: dict, site_url: str,
    ) -> dict | None:
        """메인 페이지에 상품 없을 때 카테고리 페이지에서 재분석."""
        print("[analyzer] 메인 페이지에 상품 데이터 없음 → 카테고리 페이지로 이동하여 재분석")

        cat_root_info = structure.get(category_root, {})
        cat_list_key = self._find_list_key(cat_root_info, _CATEGORY_LIST_KEY_CANDIDATES)
        if not cat_list_key:
            return None

        try:
            cat_id = page.evaluate(f"""() => {{
                var state = window.{state_var};
                if (!state || !state.{category_root}) return null;
                var list = state.{category_root}.{cat_list_key};
                if (!list || list.length === 0) return null;
                return list[0].categoryId || list[0].id || null;
            }}""")
        except Exception:
            cat_id = None

        if not cat_id:
            print("[analyzer] 카테고리 ID 추출 실패")
            return None

        slug = site_url.rstrip("/").split("/")[-1]
        origin = "/".join(site_url.rstrip("/").split("/")[:-1])
        cat_url = f"{origin}/{slug}/category/{cat_id}?cp=1"

        print(f"[analyzer] 카테고리 페이지 접속: {cat_url}")
        resp = self._safe_goto(page, cat_url)
        if resp and resp.status in (429, 403, 503):
            print(f"[analyzer] 카테고리 페이지 차단됨")
            return None
        page.wait_for_timeout(3000)

        try:
            rescan = page.evaluate(_JS_DEEP_SCAN, state_var)
        except Exception as e:
            print(f"[analyzer] 재스캔 실패: {e}")
            return None

        if not rescan or product_root not in rescan:
            return None

        tmpl = self._build_product_list_template(state_var, product_root, rescan)

        try:
            self._safe_goto(page, site_url)
            page.wait_for_timeout(2000)
        except Exception:
            pass

        return tmpl

    # ─── 유틸 ────────────────────────────────────────────────────

    @staticmethod
    def _safe_goto(
        page: Page, url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 60000,
        max_retries: int = 3,
    ):
        """429/503 자동 재시도가 포함된 안전한 페이지 이동"""
        last_resp = None
        for attempt in range(max_retries):
            try:
                resp = page.goto(url, wait_until=wait_until, timeout=timeout)
                last_resp = resp
                if resp and resp.status in (429, 503):
                    wait_secs = (attempt + 1) * 15
                    print(
                        f"[analyzer] HTTP {resp.status} → "
                        f"{wait_secs}초 대기 후 재시도"
                    )
                    page.wait_for_timeout(wait_secs * 1000)
                    continue
                return resp
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_secs = (attempt + 1) * 10
                    print(f"[analyzer] 페이지 로딩 오류 → {wait_secs}초 대기")
                    try:
                        page.wait_for_timeout(wait_secs * 1000)
                    except Exception:
                        pass
                else:
                    raise
        return last_resp

    @staticmethod
    def _find_state_vars(page: Page) -> list[str]:
        """페이지에서 JS 전역 변수를 탐지한다."""
        try:
            return page.evaluate(_JS_FIND_STATE_VARS) or []
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════
# 브라우저 설정
# ═══════════════════════════════════════════════════════════════════

def _extract_base_domain(domain: str) -> str:
    """
    www.wconcept.co.kr → wconcept.co.kr
    brand.naver.com → naver.com
    서브도메인이 없으면 그대로 반환.
    """
    parts = domain.split(".")
    # co.kr, com.au 등 2단계 TLD 처리
    if len(parts) >= 3 and parts[-2] in ("co", "com", "net", "org", "ac"):
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return domain


def _default_browser_config(
    domain: str,
    observed_domains: list[str] | None = None,
) -> dict:
    """기본 브라우저 설정을 생성한다."""
    base_domain = _extract_base_domain(domain)
    # 베이스 도메인을 포함하면 모든 서브도메인이 자동 허용됨
    allowed = [domain]
    if base_domain != domain:
        allowed.append(base_domain)

    # 도메인별 CDN 추론
    if "naver.com" in domain:
        allowed.extend([
            "brand.naver.com", "smartstore.naver.com",
            "shop-phinf.pstatic.net", "shopping-phinf.pstatic.net",
            "ssl.pstatic.net",
        ])
    elif "musinsa" in domain:
        allowed.extend([
            "musinsa.com", "www.musinsa.com",
            "static.msscdn.net", "image.msscdn.net",
            "msscdn.net",
        ])
    elif "kream" in domain:
        allowed.extend([
            "kream.co.kr", "www.kream.co.kr",
            "kream-phinf.pstatic.net",
        ])
    elif "oliveyoung" in domain:
        allowed.extend([
            "www.oliveyoung.co.kr",
            "image.oliveyoung.co.kr",
        ])
    elif "29cm" in domain:
        allowed.extend([
            "www.29cm.co.kr",
            "cdn-resource-microservice.29cm.co.kr",
            "content-api.29cm.co.kr",
            "img.29cm.co.kr",
        ])
    elif "wconcept" in domain:
        allowed.extend([
            "wconcept.co.kr",
            "display.wconcept.co.kr",
            "www.wconcept.co.kr",
            "cdn.wconcept.co.kr",
        ])

    # 네트워크 인터셉트에서 감지된 도메인 추가
    if observed_domains:
        for od in observed_domains:
            if od not in allowed:
                allowed.append(od)

    return {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1920, "height": 1080},
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Ch-Ua": '"Chromium";v="125", "Google Chrome";v="125", "Not=A?Brand";v="8"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
        "allowed_domains": allowed,
        "blocked_resource_types": ["font", "media"],
        "timeout": 30000,
    }
