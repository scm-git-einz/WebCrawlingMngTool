"""Musinsa 진단 - 23 products 원인 분석"""
import sys
import json
sys.path.insert(0, "D:\\crawling")

from core.browser import BrowserManager
from core.network_interceptor import NetworkInterceptor

bm = BrowserManager()
interceptor = NetworkInterceptor()
page = bm.create()
interceptor.start(page)

url = "https://www.musinsa.com/main/musinsa/ranking"
print(f"[diag] Loading: {url}")

resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
print(f"[diag] Status: {resp.status if resp else 'None'}")
page.wait_for_timeout(8000)

# 스크롤
for i in range(5):
    page.evaluate("window.scrollBy(0, window.innerHeight)")
    page.wait_for_timeout(1500)

interceptor.stop(page)
captured = list(interceptor.captured)

# 1) 프레임워크 감지
framework_info = page.evaluate("""() => {
    var result = {};
    if (window.__NEXT_DATA__) result.nextjs = true;
    if (document.getElementById('__NEXT_DATA__')) result.nextjs_script = true;
    if (window.__NUXT__) result.nuxt = true;
    if (window.__next_f) result.nextjs_rsc = true;
    if (window.__PRELOADED_STATE__) result.preloaded = true;
    return result;
}""")
print(f"\n[diag] Framework: {json.dumps(framework_info)}")

# 2) 현재 item_selector 확인
old_sel = ".UIProductColumn__Wrap-sc-1t5ihy5-0"
old_count = page.evaluate(f"() => document.querySelectorAll('{old_sel}').length")
print(f"\n[diag] Old selector '{old_sel}': {old_count} elements")

# 3) DOM 상품 후보 탐색
product_dom = page.evaluate("""() => {
    var selectors = [
        '[class*="product"]', '[class*="Product"]',
        '[class*="item"]', '[class*="Item"]',
        '[class*="goods"]', '[class*="Goods"]',
        '[class*="ranking"]', '[class*="Ranking"]',
        'a[href*="/products/"]', 'a[href*="/app/goods/"]',
        '[data-item-id]', '[data-product-id]',
    ];
    var result = {};
    for (var i = 0; i < selectors.length; i++) {
        try {
            var cnt = document.querySelectorAll(selectors[i]).length;
            if (cnt > 0) result[selectors[i]] = cnt;
        } catch(e) {}
    }
    return result;
}""")
print(f"\n[diag] Product DOM elements: {json.dumps(product_dom, indent=2)}")

# 4) 가격 패턴
price_info = page.evaluate("""() => {
    var body = document.body.innerText || '';
    var pricePattern = /[0-9,]+원/g;
    var prices = body.match(pricePattern);
    return {
        priceCount: prices ? prices.length : 0,
        samplePrices: prices ? prices.slice(0, 5) : [],
        bodyLen: body.length,
    };
}""")
print(f"\n[diag] Price info: {json.dumps(price_info, ensure_ascii=False)}")

# 5) API 요청 분석
print(f"\n[diag] Captured requests: {len(captured)}")
api_reqs = [r for r in captured if 'api' in r.get('url', '').lower()
            or 'ranking' in r.get('url', '').lower()
            or 'product' in r.get('url', '').lower()
            or 'goods' in r.get('url', '').lower()]
for req in api_reqs[:15]:
    url_short = req.get("url", "")[:120]
    status = req.get("status", "")
    body_len = len(req.get("body", "") or "")
    post_body_len = len(req.get("post_body", "") or "")
    print(f"  [{status}] body={body_len:>6} post={post_body_len:>4} {url_short}")

# 6) 상품 카드 분석 - 가격 요소 주변 탐색
card_analysis = page.evaluate("""() => {
    // 가격 패턴이 있는 요소 찾기
    var allEls = document.querySelectorAll('*');
    var priceEls = [];
    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        if (el.children.length > 0) continue;  // 리프 노드만
        var text = (el.textContent || '').trim();
        if (/^[0-9,]+원$/.test(text) || /^[0-9]{1,3}(,[0-9]{3})*$/.test(text)) {
            priceEls.push(el);
        }
    }

    if (priceEls.length === 0) return {priceEls: 0};

    // 가격 요소의 부모 클래스 패턴 분석
    var parentClasses = {};
    for (var i = 0; i < priceEls.length; i++) {
        var parent = priceEls[i].parentElement;
        for (var d = 0; d < 5 && parent; d++) {
            var cls = parent.className || '';
            if (typeof cls !== 'string') cls = cls.toString();
            var classes = cls.split(/\\s+/).filter(function(c) { return c.length > 2; });
            for (var j = 0; j < classes.length; j++) {
                var key = d + ':' + classes[j];
                parentClasses[key] = (parentClasses[key] || 0) + 1;
            }
            parent = parent.parentElement;
        }
    }

    // 최다 출현 클래스 (카드 후보)
    var sorted = Object.keys(parentClasses).sort(function(a, b) {
        return parentClasses[b] - parentClasses[a];
    });

    return {
        priceEls: priceEls.length,
        topClasses: sorted.slice(0, 10).map(function(k) {
            return {cls: k, count: parentClasses[k]};
        }),
    };
}""")
print(f"\n[diag] Card analysis:")
print(f"  Price elements: {card_analysis.get('priceEls', 0)}")
for tc in card_analysis.get('topClasses', []):
    print(f"  {tc['cls']}: {tc['count']}")

print(f"\n[diag] Final URL: {page.url}")
bm.close()
print("[diag] Done")
