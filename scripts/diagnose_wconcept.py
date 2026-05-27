"""W Concept 진단 - 0 products 원인 분석"""
import sys
import json
sys.path.insert(0, "D:\\crawling")

from core.browser import BrowserManager
from core.network_interceptor import NetworkInterceptor

bm = BrowserManager()
interceptor = NetworkInterceptor()
page = bm.create()
interceptor.start(page)

url = "https://www.wconcept.co.kr/Women"
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

# 2) DOM 상품 확인
product_dom = page.evaluate("""() => {
    var selectors = [
        '.product-item', '.product_item', '[class*="product"]',
        '[class*="Product"]', '[class*="item-card"]',
        '[class*="ItemCard"]', '[class*="goods"]',
        'a[href*="/Product/"]', 'a[href*="/product/"]',
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

# 3) 가격 패턴
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

# 4) 캡처된 API 요청
print(f"\n[diag] Captured API requests: {len(captured)}")
api_reqs = [r for r in captured if 'api' in r.get('url', '').lower() or 'product' in r.get('url', '').lower()]
for req in api_reqs[:15]:
    url_short = req.get("url", "")[:120]
    status = req.get("status", "")
    body_len = len(req.get("body", "") or "")
    print(f"  [{status}] body={body_len:>6} {url_short}")
    if body_len > 0 and body_len < 500:
        try:
            body_json = json.loads(req["body"])
            print(f"    -> {json.dumps(body_json, ensure_ascii=False)[:200]}")
        except:
            pass

# 5) 첫 상품 요소 분석 (있다면)
if product_dom:
    best_sel = max(product_dom.items(), key=lambda x: x[1])
    print(f"\n[diag] Best product selector: {best_sel[0]} ({best_sel[1]} elements)")
    sample = page.evaluate("""(sel) => {
        var els = document.querySelectorAll(sel);
        var samples = [];
        for (var i = 0; i < Math.min(3, els.length); i++) {
            var el = els[i];
            samples.push({
                tag: el.tagName,
                cls: (el.className || '').toString().substring(0, 100),
                text: (el.textContent || '').trim().substring(0, 150),
                href: el.getAttribute('href') || '',
                childCount: el.querySelectorAll('*').length,
            });
        }
        return samples;
    }""", best_sel[0])
    for s in sample:
        print(f"  <{s['tag']} class='{s['cls'][:60]}'>")
        try:
            print(f"    text: {s['text'][:100]}")
        except:
            print(f"    text: (encoding issue)")
        print(f"    href: {s['href'][:80]}")

print(f"\n[diag] Final URL: {page.url}")
bm.close()
print("[diag] Done")
